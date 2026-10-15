#!/usr/bin/env python3
"""bgctl — управление стендом: релизы blue-green, секреты, проверки.

Одна реализация используется локально (Makefile/Ansible), в GitHub Actions и
на удалённом стенде (через SSH forced command) — логика конвейера не расходится.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pylib import secrets as sec
from pylib.common import Config, fail, log, ok, warn
from pylib.httpprobe import request
from pylib.kube import Kube


def cmd_secrets_init(cfg: Config, _: argparse.Namespace) -> int:
    created = sec.ensure_age_key(cfg)
    log(f"age-ключ: {cfg.age_key_file} ({'создан' if created else 'уже есть, не изменён'})")
    result = sec.init_source(cfg)
    ok(f"зашифрованный источник секретов {cfg.sops_source.name}: {result}")
    return 0


def cmd_secrets_apply(cfg: Config, args: argparse.Namespace) -> int:
    kube = Kube(cfg.admin_kubeconfig, cfg.namespace)
    data = sec.read_source(cfg)
    fps = sec.apply_api_secret(cfg, kube, data)
    ok(f"Secret {sec.API_SECRET}: применены хеши токенов (отпечатки {fps})")
    if args.grafana:
        sec.apply_grafana_secret(cfg, kube, data)
        ok(f"Secret {sec.GRAFANA_SECRET} применён в {cfg.monitoring_namespace}")
    return 0


def cmd_deploy_credentials(cfg: Config, args: argparse.Namespace) -> int:
    """Выпускает ограниченный kubeconfig релизной учётной записи (TokenRequest, срок ограничен)."""
    admin = Kube(cfg.admin_kubeconfig, cfg.namespace)
    view = json.loads(admin.kubectl("config", "view", "--raw", "--minify", "-o", "json").stdout)
    cluster = view["clusters"][0]["cluster"]
    token = admin.kubectl("create", "token", "release-controller", f"--duration={args.duration}").stdout.strip()
    kubeconfig = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": cfg.cluster,
                "cluster": {
                    "server": cluster["server"],
                    "certificate-authority-data": cluster["certificate-authority-data"],
                },
            }
        ],
        "users": [{"name": "release-controller", "user": {"token": token}}],
        "contexts": [
            {
                "name": "deploy",
                "context": {"cluster": cfg.cluster, "user": "release-controller", "namespace": cfg.namespace},
            }
        ],
        "current-context": "deploy",
    }
    path = cfg.deploy_kubeconfig
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(kubeconfig, fh)
    os.chmod(path, 0o600)
    deploy = Kube(path, cfg.namespace)
    allowed = deploy.kubectl("auth", "can-i", "patch", "deployments", check=False).stdout.strip()
    denied = deploy.kubectl("auth", "can-i", "get", "secrets", namespace="kube-system", check=False).stdout.strip()
    if allowed != "yes" or denied != "no":
        fail(f"RBAC релизной учётной записи не соответствует ожиданию: mts-app={allowed}, kube-system={denied}")
        return 1
    ok(
        f"deploy kubeconfig: {path} (ServiceAccount release-controller, "
        f"namespace {cfg.namespace}, срок {args.duration})"
    )
    return 0


def cmd_wait_observability(cfg: Config, args: argparse.Namespace) -> int:
    deadline = time.time() + args.timeout
    checks = {
        "prometheus": ("prometheus.localhost", "/-/ready"),
        "alertmanager": ("alertmanager.localhost", "/-/ready"),
        "grafana": ("grafana.localhost", "/api/health"),
    }
    pending = dict(checks)
    while pending and time.time() < deadline:
        for name, (host, path) in list(pending.items()):
            if request("GET", cfg.ingress_url + path, headers={"Host": host}).status == 200:
                ok(f"{name} готов (http://{host}:{cfg.get('INGRESS_PORT', '8080')}{path})")
                pending.pop(name)
        if pending:
            time.sleep(3)
    if pending:
        fail(f"не дождались готовности: {sorted(pending)} за {args.timeout} с")
        return 1
    return 0


def cmd_release(cfg: Config, args: argparse.Namespace) -> int:
    from pylib.release import EXIT, Artifact, ReleaseController

    artifact = Artifact.from_provenance(Path(args.provenance))
    allowed = cfg.get("ALLOWED_IMAGE_REPOSITORY")
    if allowed and artifact.repo != allowed:
        fail(f"образ {artifact.repo} не из разрешённого репозитория {allowed}")
        return 1
    decision = ReleaseController(cfg, artifact).run()
    if args.expect:
        if decision == args.expect:
            ok(f"сценарий завершился ожидаемым решением: {decision}")
            return 0
        fail(f"ожидалось решение {args.expect}, получено {decision}")
        return 1
    return EXIT.get(decision, 1)


def cmd_rotate(cfg: Config, _: argparse.Namespace) -> int:
    from pylib.rotation import rotate

    return rotate(cfg)


def cmd_token_probe(cfg: Config, args: argparse.Namespace) -> int:
    from pylib.rotation import check_revoked, save_current_token

    if args.save_current:
        save_current_token(cfg, args.save_current)
        ok(f"действующий токен сохранён в {args.save_current} (0600) для проверки отзыва")
        return 0
    return check_revoked(cfg, args.expect_revoked)


def cmd_demo_alert(cfg: Config, args: argparse.Namespace) -> int:
    from pylib.alertdemo import run_demo

    return run_demo(cfg, timeout=args.timeout)


def cmd_verify(cfg: Config, _: argparse.Namespace) -> int:
    from pylib.verify import verify

    return verify(cfg)


def cmd_verify_security(cfg: Config, _: argparse.Namespace) -> int:
    from pylib.verify import verify_security

    return verify_security(cfg)


def cmd_status(cfg: Config, _: argparse.Namespace) -> int:
    from pylib.verify import status

    return status(cfg)


def cmd_active(cfg: Config, args: argparse.Namespace) -> int:
    """Последний подтверждённый релиз; код 0 только если он совпадает с условиями и обслуживает трафик."""
    from pylib.state import StateStore, live_active_slot

    kube = Kube(cfg.deploy_kubeconfig, cfg.namespace)
    active = StateStore(kube).load().get("active") or {}
    live = live_active_slot(kube)
    print(json.dumps({"live_slot": live, "active": active}, ensure_ascii=False))
    matches = (
        bool(active)
        and active.get("healthy", False)
        and active.get("slot") == live
        and (not args.match_version or active.get("version") == args.match_version)
        and (not args.match_git_sha or active.get("git_sha") == args.match_git_sha)
    )
    return 0 if matches else 1


def cmd_credentials(cfg: Config, _: argparse.Namespace) -> int:
    data = sec.read_source(cfg)
    warn("ниже учебные учётные данные — не вставляйте их в общие логи и тикеты")
    port = cfg.get("INGRESS_PORT", "8080")
    print(f"Grafana:   http://grafana.localhost:{port}  (пользователь admin)")
    print(f"  пароль:  {data['grafana_admin_password']}")
    print(f"API token: {data['api_tokens']['current']}")
    print(
        f"  пример:  curl -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' "
        f'-d \'{{"tariff_id":"basic","minutes":320,"sms":55,"data_gb":"11.5"}}\' '
        f"{cfg.ingress_url}/api/v1/quotes"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bgctl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("secrets-init", help="создать age-ключ и зашифрованный источник (идемпотентно)")
    p = sub.add_parser("secrets-apply", help="расшифровать в память и применить Secret (bootstrap)")
    p.add_argument("--grafana", action="store_true")
    p = sub.add_parser("deploy-credentials", help="выпустить ограниченный kubeconfig релизов")
    p.add_argument("--duration", default="168h")
    p = sub.add_parser("wait-observability", help="дождаться Prometheus/Alertmanager/Grafana")
    p.add_argument("--timeout", type=float, default=300)
    p = sub.add_parser("release", help="blue-green релиз проверенного digest")
    p.add_argument("--provenance", required=True, help="JSON из scripts/ci.sh (digest + Trivy)")
    p.add_argument(
        "--expect",
        choices=["promoted", "rejected", "rolled_back", "noop"],
        help="для сценариев: код 0, если решение совпало с ожидаемым",
    )
    sub.add_parser("rotate-secret", help="ротация API-токена с перекрытием")
    p = sub.add_parser("token-probe", help="приёмочная проверка отзыва токена (e2e)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--save-current", metavar="FILE")
    g.add_argument("--expect-revoked", metavar="FILE")
    p = sub.add_parser("demo-alert", help="сбой → firing → восстановление → resolved")
    p.add_argument("--timeout", type=float, default=240)
    sub.add_parser("verify", help="проверка работающего стенда")
    sub.add_parser("verify-security", help="проверки безопасности (admin kubeconfig)")
    sub.add_parser("status", help="слоты, версия, история")
    p = sub.add_parser("active", help="последний подтверждённый релиз (JSON)")
    p.add_argument("--match-version")
    p.add_argument("--match-git-sha")
    sub.add_parser("credentials", help="показать учебные учётные данные (только по запросу)")
    args = parser.parse_args(argv)
    handler = globals()["cmd_" + args.command.replace("-", "_").replace("rotate_secret", "rotate")]
    cfg = Config()
    try:
        return handler(cfg, args)
    except sec.SecretsError as exc:
        fail(str(exc))
        return 1
    except KeyboardInterrupt:
        fail("прервано пользователем; состояние фазы сохранено, следующий запуск восстановит стенд")
        return 130


if __name__ == "__main__":
    sys.exit(main())
