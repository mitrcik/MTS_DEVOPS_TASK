"""Учебные секреты: генерация → SOPS/age → Kubernetes Secret.

Путь данных:
  1. значения генерируются в памяти (secrets.token_urlsafe);
  2. шифруются sops (age) из stdin в .local/secrets/app-secrets.sops.yaml
     (атомарная запись, права 0600; plaintext на диск не попадает);
  3. при применении в кластер расшифровываются в память и передаются в
     `kubectl apply --server-side -f -` через stdin.
  В Secret api-auth лежат только SHA-256 токенов; сами токены — только в SOPS-файле.

Закрытый age-ключ хранится вне каталога проекта (~/.config/mts-devops/<cluster>/age.key, 0600).
"""

from __future__ import annotations

import base64
import json
import os
import secrets as pysecrets
import tempfile
from pathlib import Path

from .auth_hash import token_hash
from .common import Config, iso, run, tool, utcnow
from .kube import Kube

API_SECRET = "api-auth"
GRAFANA_SECRET = "grafana-admin"
FIELD_MANAGER = "mts-devops-secrets"


class SecretsError(RuntimeError):
    pass


def _sops(cfg: Config, *args: str, input_text: str | None = None) -> str:
    env = {"SOPS_AGE_KEY_FILE": str(cfg.age_key_file)}
    proc = run(
        [tool("sops"), "--disable-version-check", *args], input_text=input_text, env=env, check=False, timeout=60
    )
    if proc.returncode != 0:
        # stderr sops не содержит значений секретов, но обрезаем на всякий случай
        raise SecretsError(f"sops {args[0]}: {proc.stderr.strip().splitlines()[-1:]}")
    return proc.stdout


def age_recipient(cfg: Config) -> str:
    if not cfg.age_key_file.exists():
        raise SecretsError(f"нет age-ключа {cfg.age_key_file}; выполните make up")
    return run([tool("age-keygen"), "-y", str(cfg.age_key_file)]).stdout.strip()


def ensure_age_key(cfg: Config) -> bool:
    """Создаёт ключ, если его нет. Существующий ключ никогда не перезаписывается."""
    key = cfg.age_key_file
    if key.exists():
        return False
    key.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(key.parent, 0o700)
    old = os.umask(0o077)
    try:
        run([tool("age-keygen"), "-o", str(key)])
    finally:
        os.umask(old)
    os.chmod(key, 0o600)
    return True


def read_source(cfg: Config) -> dict:
    if not cfg.sops_source.exists():
        raise SecretsError(f"нет зашифрованного источника {cfg.sops_source}; выполните make up")
    return json.loads(_sops(cfg, "decrypt", "--output-type", "json", str(cfg.sops_source)))


def write_source(cfg: Config, data: dict) -> None:
    encrypted = _sops(
        cfg,
        "encrypt",
        "--input-type",
        "json",
        "--output-type",
        "yaml",
        "--age",
        age_recipient(cfg),
        "--filename-override",
        cfg.sops_source.name,
        input_text=json.dumps(data),
    )
    target = cfg.sops_source
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".tmp-", suffix=".sops.yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(encrypted)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def new_token() -> str:
    return "mts_demo_" + pysecrets.token_urlsafe(32)


def init_source(cfg: Config) -> str:
    """Идемпотентно: существующий источник проверяется на расшифровку и не меняется."""
    ensure_age_key(cfg)
    if cfg.sops_source.exists():
        data = read_source(cfg)  # падает с понятной ошибкой, если ключ не подходит
        if not data.get("api_tokens", {}).get("current"):
            raise SecretsError("источник секретов повреждён: нет api_tokens.current")
        return "unchanged"
    now = iso(utcnow())
    write_source(
        cfg,
        {
            "api_tokens": {"current": new_token(), "previous": ""},
            "grafana_admin_password": pysecrets.token_urlsafe(24),
            "created_at": now,
            "rotated_at": now,
        },
    )
    return "created"


def token_fingerprint(token: str) -> str:
    return token_hash(token)[:12]


def api_secret_manifest(namespace: str, tokens: list[str]) -> str:
    hashes = "".join(token_hash(t) + "\n" for t in tokens if t)
    return json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": API_SECRET,
                "namespace": namespace,
                "labels": {"app.kubernetes.io/part-of": "mts-devops"},
            },
            "data": {"token-hashes": base64.b64encode(hashes.encode()).decode()},
        }
    )


def grafana_secret_manifest(namespace: str, password: str) -> str:
    return json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": GRAFANA_SECRET,
                "namespace": namespace,
                "labels": {"app.kubernetes.io/part-of": "mts-devops"},
            },
            "data": {
                "admin-user": base64.b64encode(b"admin").decode(),
                "admin-password": base64.b64encode(password.encode()).decode(),
            },
        }
    )


def _apply(kube: Kube, manifest: str, namespace: str) -> None:
    # server-side apply: значение не дублируется в аннотацию last-applied-configuration
    proc = kube.kubectl(
        "apply",
        "--server-side",
        f"--field-manager={FIELD_MANAGER}",
        "--force-conflicts",
        "-f",
        "-",
        input_text=manifest,
        namespace=namespace,
        check=False,
    )
    if proc.returncode != 0:
        raise SecretsError(f"kubectl apply Secret: {proc.stderr.strip()[:300]}")


def apply_api_secret(cfg: Config, kube: Kube, data: dict | None = None) -> list[str]:
    data = data or read_source(cfg)
    tokens = [data["api_tokens"]["current"], data["api_tokens"].get("previous", "")]
    active = [t for t in tokens if t]
    _apply(kube, api_secret_manifest(cfg.namespace, active), cfg.namespace)
    return [token_fingerprint(t) for t in active]


def apply_grafana_secret(cfg: Config, kube: Kube, data: dict | None = None) -> None:
    data = data or read_source(cfg)
    _apply(
        kube,
        grafana_secret_manifest(cfg.monitoring_namespace, data["grafana_admin_password"]),
        cfg.monitoring_namespace,
    )


def current_token(cfg: Config) -> str:
    return read_source(cfg)["api_tokens"]["current"]


def source_fingerprint(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else "absent"
