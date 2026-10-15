"""Конфигурация, запуск команд, журналирование."""

from __future__ import annotations

import datetime as dt
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local"

_COLOR = sys.stderr.isatty()


def _paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def log(msg: str) -> None:
    print(f"{_paint('2', utcnow().strftime('[%H:%M:%S]'))} {msg}", file=sys.stderr, flush=True)


def ok(msg: str) -> None:
    print(f"{_paint('32', '[ OK ]')} {msg}", file=sys.stderr, flush=True)


def warn(msg: str) -> None:
    print(f"{_paint('33', '[WARN]')} {msg}", file=sys.stderr, flush=True)


def fail(msg: str) -> None:
    print(f"{_paint('31', '[FAIL]')} {msg}", file=sys.stderr, flush=True)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def iso(ts: dt.datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_iso(value: str) -> dt.datetime:
    value = value.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(value)


_ENV_LINE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = _ENV_LINE.match(raw)
        if m:
            val = m.group(2)
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
                val = val[1:-1]
            values[m.group(1)] = val
    return values


def load_env() -> dict[str, str]:
    """versions.env < .env (или .env.example) < переменные окружения процесса."""
    env = read_env_file(ROOT / "versions.env")
    local = ROOT / ".env"
    env.update(read_env_file(local if local.exists() else ROOT / ".env.example"))
    for key, value in os.environ.items():
        if key in env or key.isupper():
            env[key] = value
    return env


@dataclass
class Config:
    env: dict[str, str] = field(default_factory=load_env)

    def get(self, key: str, default: str = "") -> str:
        value = self.env.get(key, "")
        return value if value != "" else default

    def num(self, key: str, default: float) -> float:
        try:
            return float(self.get(key, str(default)))
        except ValueError as exc:
            raise SystemExit(f"{key} должен быть числом") from exc

    # --- имена и адреса ---
    @property
    def cluster(self) -> str:
        return self.get("CLUSTER_NAME", "mts-devops")

    @property
    def namespace(self) -> str:
        return "mts-app"

    @property
    def monitoring_namespace(self) -> str:
        return "monitoring"

    @property
    def bind(self) -> str:
        return self.get("BIND_ADDRESS", "127.0.0.1")

    @property
    def ingress_url(self) -> str:
        return self.get("INGRESS_URL", f"http://{self.bind}:{self.get('INGRESS_PORT', '8080')}")

    @property
    def registry_push(self) -> str:
        return f"localhost:{self.get('REGISTRY_PORT', '5001')}"

    # --- пути ---
    @property
    def admin_kubeconfig(self) -> Path:
        return LOCAL / "kube" / "admin.kubeconfig"

    @property
    def deploy_kubeconfig(self) -> Path:
        return Path(self.get("DEPLOY_KUBECONFIG", str(LOCAL / "kube" / "deploy.kubeconfig")))

    @property
    def age_key_file(self) -> Path:
        default = Path.home() / ".config" / "mts-devops" / self.cluster / "age.key"
        return Path(self.get("AGE_KEY_FILE", str(default))).expanduser()

    @property
    def sops_source(self) -> Path:
        return LOCAL / "secrets" / "app-secrets.sops.yaml"

    @property
    def reports_dir(self) -> Path:
        return LOCAL / "reports"

    @property
    def bin_dir(self) -> Path:
        return LOCAL / "bin"


class CmdError(RuntimeError):
    def __init__(self, cmd: list[str], code: int, stdout: str, stderr: str) -> None:
        self.cmd, self.code, self.stdout, self.stderr = cmd, code, stdout, stderr
        tail = (stderr or stdout).strip().splitlines()[-6:]
        super().__init__(f"{' '.join(cmd[:4])}… exit {code}: " + " | ".join(tail))


def tool(name: str) -> str:
    local = LOCAL / "bin" / name
    return str(local) if local.exists() else name


def run(
    cmd: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 120,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = None
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    try:
        proc = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=full_env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CmdError(cmd, 124, "", f"timeout after {timeout}s") from exc
    if check and proc.returncode != 0:
        raise CmdError(cmd, proc.returncode, proc.stdout, proc.stderr)
    return proc


def hostname() -> str:
    return socket.gethostname()
