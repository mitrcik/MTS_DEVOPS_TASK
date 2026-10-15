"""Проверка работающего стенда (`make verify`) и мер безопасности (`make verify-security`)."""

from __future__ import annotations

import base64
import json
import secrets as pysecrets
import time

from . import secrets as sec
from .common import Config, fail, ok, run, warn
from .httpprobe import QUOTE_EXPECTED_TOTAL, QUOTE_PAYLOAD, request
from .kube import Kube, pod_ready
from .lock import LOCK_NAME
from .prom import Alertmanager, Prometheus, PromUnavailable
from .state import StateStore, deployed_slot_info, live_active_slot, other_slot, slot_release

EXPECTED_ALERTS = {
    "MtsApiSyntheticProbeFailing",
    "MtsApiSyntheticProbeAbsent",
    "MtsApiHighErrorRate",
    "MtsApiHighLatencyP95",
    "MtsApiTargetDown",
}
DASHBOARD_UID = "mts-api-overview"


class Checklist:
    def __init__(self) -> None:
        self.items: list[tuple[str, bool, str]] = []

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.items.append((name, passed, detail))
        (ok if passed else fail)(f"{name}{': ' + detail if detail else ''}")

    @property
    def failed(self) -> int:
        return sum(1 for _, passed, _ in self.items if not passed)


def verify(cfg: Config, wait_targets: float = 90) -> int:
    kube = Kube(cfg.deploy_kubeconfig, cfg.namespace)
    c = Checklist()
    base = cfg.ingress_url
    state = StateStore(kube).load()
    live = live_active_slot(kube)
    active = state.get("active") or {}
    c.add(
        "активный слот определён",
        live is not None and live == active.get("slot"),
        f"Service → {live}, состояние → {active.get('slot')} ({active.get('release_id')})",
    )

    # --- пользовательский путь
    v = request("GET", base + "/version")
    c.add(
        "GET /version через ingress",
        v.status == 200 and v.json().get("release_id") == active.get("release_id"),
        f"HTTP {v.status}, release {v.json().get('release_id')}, версия {v.json().get('version')}",
    )
    c.add("GET /healthz через ingress", request("GET", base + "/healthz").status == 200)
    t = request("GET", base + "/api/v1/tariffs")
    c.add("GET /api/v1/tariffs", t.status == 200 and t.json().get("count", 0) >= 1, f"HTTP {t.status}")
    token = sec.current_token(cfg)
    q = request("POST", base + "/api/v1/quotes", headers={"Authorization": f"Bearer {token}"}, payload=QUOTE_PAYLOAD)
    c.add(
        "POST /api/v1/quotes с токеном из SOPS",
        q.status == 200 and q.json().get("total") == QUOTE_EXPECTED_TOTAL,
        f"HTTP {q.status}",
    )
    c.add(
        "POST /api/v1/quotes без токена → 401",
        request("POST", base + "/api/v1/quotes", payload=QUOTE_PAYLOAD).status == 401,
    )

    # --- наблюдаемость
    prom = Prometheus(base)
    try:
        c.add("Prometheus ready", prom.ready())
        missing = EXPECTED_ALERTS - prom.rule_names()
        c.add(
            "правила алертов загружены",
            not missing,
            f"нет: {sorted(missing)}" if missing else f"{len(EXPECTED_ALERTS)} алертов",
        )
        deadline = time.time() + wait_targets
        while True:
            targets = prom.targets()
            jobs: dict[str, list[str]] = {}
            for tgt in targets:
                jobs.setdefault(tgt["labels"].get("job", "?"), []).append(tgt["health"])
            api_pods = [
                tgt for tgt in targets if tgt["labels"].get("job") == "mts-api" and tgt["labels"].get("slot") == live
            ]
            healthy = (
                all(all(h == "up" for h in hs) for hs in jobs.values())
                and {"mts-api", "blackbox-api", "kubelet-cadvisor", "prometheus", "traefik"} <= jobs.keys()
                and api_pods
                and all(tg["health"] == "up" for tg in api_pods)
            )
            if healthy or time.time() > deadline:
                break
            time.sleep(5)
        c.add(
            "scrape targets up", bool(healthy), json.dumps({j: f"{hs.count('up')}/{len(hs)}" for j, hs in jobs.items()})
        )
        probe = prom.scalar('min(probe_success{job="blackbox-api"})')
        c.add("синтетическая проба бизнес-метода", probe == 1, f"probe_success={probe}")
        active_alerts = [a["labels"]["alertname"] for a in prom.alerts() if a["state"] == "firing"]
        if active_alerts:
            warn(f"активные алерты: {active_alerts}")
        c.add("Alertmanager ready", Alertmanager(base).ready())
    except PromUnavailable as exc:
        c.add("Prometheus API", False, str(exc))

    g = request("GET", base + "/api/health", headers={"Host": "grafana.localhost"})
    c.add("Grafana /api/health", g.status == 200, f"HTTP {g.status}")
    pw = sec.read_source(cfg)["grafana_admin_password"]
    basic = base64.b64encode(f"admin:{pw}".encode()).decode()
    auth = {"Host": "grafana.localhost", "Authorization": f"Basic {basic}"}
    d = request("GET", base + f"/api/dashboards/uid/{DASHBOARD_UID}", headers=auth)
    c.add(
        "дашборд Grafana provisioned",
        d.status == 200,
        f"HTTP {d.status}, панелей: {len(d.json().get('dashboard', {}).get('panels', []))}",
    )
    ds = request("GET", base + "/api/datasources/uid/prometheus/health", headers=auth)
    c.add("datasource Prometheus в Grafana", ds.status == 200 and ds.json().get("status") == "OK", f"HTTP {ds.status}")

    print()
    print(f"verify: {len(c.items) - c.failed}/{len(c.items)} проверок пройдено")
    return 1 if c.failed else 0


def verify_security(cfg: Config) -> int:
    """Глубокие проверки с правами администратора (bootstrap-kubeconfig)."""
    admin = Kube(cfg.admin_kubeconfig, cfg.namespace)
    deploy = Kube(cfg.deploy_kubeconfig, cfg.namespace)
    c = Checklist()

    ns = admin.get_json("namespace", cfg.namespace) or {}
    labels = ns.get("metadata", {}).get("labels", {})
    c.add(
        "Pod Security Admission restricted для mts-app",
        labels.get("pod-security.kubernetes.io/enforce") == "restricted",
    )

    pods = [
        p
        for p in (admin.get_json("pods", "-l", "app.kubernetes.io/name=mts-api") or {}).get("items", [])
        if pod_ready(p)
    ]
    c.add("есть готовые pod приложения", bool(pods), f"{len(pods)}")
    if pods:
        pod = pods[0]
        name = pod["metadata"]["name"]
        spec = pod["spec"]
        ctr = spec["containers"][0]
        sc = ctr.get("securityContext", {})
        c.add("automountServiceAccountToken=false", spec.get("automountServiceAccountToken") is False)
        c.add(
            "securityContext контейнера",
            sc.get("readOnlyRootFilesystem") is True
            and sc.get("allowPrivilegeEscalation") is False
            and sc.get("capabilities", {}).get("drop") == ["ALL"],
            json.dumps(sc, ensure_ascii=False),
        )
        uid = admin.kubectl("exec", name, "--", "id", "-u", check=False).stdout.strip()
        c.add("процесс работает не от root", uid == "10001", f"uid={uid}")
        ro = admin.kubectl("exec", name, "--", "sh", "-c", "touch /app/probe 2>&1", check=False)
        c.add("корневая ФС только для чтения", ro.returncode != 0, ro.stdout.strip()[:80])
        caps = admin.kubectl("exec", name, "--", "sh", "-c", "grep CapEff /proc/1/status", check=False).stdout
        c.add("эффективные capabilities пусты", caps.strip().endswith("0000000000000000"), caps.strip())
        sa_mount = admin.kubectl(
            "exec",
            name,
            "--",
            "sh",
            "-c",
            "test -e /var/run/secrets/kubernetes.io/serviceaccount/token && echo yes || echo no",
            check=False,
        ).stdout.strip()
        c.add("токен ServiceAccount не смонтирован", sa_mount == "no")
        egress = admin.kubectl(
            "exec",
            name,
            "--",
            "python",
            "-c",
            "import socket,sys\n"
            "socket.getaddrinfo('kubernetes.default.svc.cluster.local', 443)\n"
            "s=socket.socket(); s.settimeout(3)\n"
            "try:\n s.connect(('kubernetes.default.svc.cluster.local', 443)); print('connected')\n"
            "except OSError as e:\n print('blocked', type(e).__name__)\n",
            check=False,
            timeout=30,
        )
        c.add(
            "NetworkPolicy: DNS разрешён, прочий egress запрещён",
            egress.returncode == 0 and egress.stdout.strip().startswith("blocked"),
            (egress.stdout or egress.stderr).strip()[:120],
        )

    # NetworkPolicy ingress: pod из постороннего namespace не должен достучаться до приложения
    probe_ns = f"np-probe-{pysecrets.token_hex(3)}"
    busybox = cfg.get("BUSYBOX_IMAGE", "docker.io/library/busybox:1.37")
    try:
        admin.kubectl("create", "namespace", probe_ns, namespace="default")
        admin.kubectl(
            "label", "namespace", probe_ns, "pod-security.kubernetes.io/enforce=restricted", namespace="default"
        )
        overrides = json.dumps(
            {
                "spec": {
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 65534,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "probe",
                            "image": busybox,
                            "command": ["sleep", "300"],
                            "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                        }
                    ],
                }
            }
        )
        admin.kubectl(
            "run", "probe", "--image", busybox, "--restart=Never", f"--overrides={overrides}", namespace=probe_ns
        )
        admin.kubectl("wait", "--for=condition=Ready", "pod/probe", "--timeout=90s", namespace=probe_ns, timeout=120)
        direct = admin.kubectl(
            "exec",
            "probe",
            "--",
            "wget",
            "-q",
            "-T",
            "4",
            "-O",
            "-",
            f"http://mts-api-active.{cfg.namespace}.svc/healthz",
            namespace=probe_ns,
            check=False,
            timeout=30,
        )
        via_ingress = admin.kubectl(
            "exec",
            "probe",
            "--",
            "wget",
            "-q",
            "-T",
            "4",
            "-O",
            "-",
            "http://traefik.kube-system.svc/healthz",
            namespace=probe_ns,
            check=False,
            timeout=30,
        )
        c.add(
            "NetworkPolicy: прямой доступ к pod из чужого namespace запрещён",
            direct.returncode != 0,
            (direct.stderr or direct.stdout).strip()[:100],
        )
        c.add(
            "тот же pod через ingress-контроллер получает ответ (сеть исправна)",
            via_ingress.returncode == 0,
            via_ingress.stdout.strip()[:60],
        )
    finally:
        admin.kubectl("delete", "namespace", probe_ns, "--wait=false", namespace="default", check=False)

    # RBAC релизной учётной записи
    def can(*args: str) -> str:
        return deploy.kubectl("auth", "can-i", *args, check=False).stdout.strip()

    c.add("deploy SA: может обновлять Deployment в mts-app", can("update", "deployments") == "yes")
    c.add(
        "deploy SA: не читает Secret в kube-system",
        deploy.kubectl("auth", "can-i", "get", "secrets", namespace="kube-system", check=False).stdout.strip() == "no",
    )
    c.add(
        "deploy SA: не управляет узлами/кластером",
        can("get", "nodes") == "no" and can("create", "clusterroles") == "no",
    )
    c.add("deploy SA: нет exec в pod", can("create", "pods/exec") == "no")

    # Secrets at rest (k3s secrets-encryption) — локальный профиль k3d
    node = f"k3d-{cfg.cluster}-server-0"
    status = run(["docker", "exec", node, "k3s", "secrets-encrypt", "status"], check=False).stdout
    c.add(
        "k3s secrets-encryption включён",
        "Encryption Status: Enabled" in status,
        status.strip().splitlines()[0] if status.strip() else "нет данных",
    )
    # хеш токена (не секрет) не должен встречаться в базе kine открытым текстом
    hashes = base64.b64decode(
        (admin.get_json("secret", sec.API_SECRET) or {}).get("data", {}).get("token-hashes", "")
    ).decode()
    first_hash = hashes.split()[0] if hashes.split() else ""
    if first_hash:
        raw = run(
            [
                "docker",
                "exec",
                node,
                "sh",
                "-c",
                f"grep -a -c '{first_hash}' /var/lib/rancher/k3s/server/db/state.db || true",
            ],
            check=False,
        ).stdout.strip()
        enc = run(
            [
                "docker",
                "exec",
                node,
                "sh",
                "-c",
                "grep -a -c 'k8s:enc:aescbc:v1:' /var/lib/rancher/k3s/server/db/state.db || true",
            ],
            check=False,
        ).stdout.strip()
        c.add(
            "Secret в базе kine зашифрован",
            raw == "0" and enc not in ("", "0"),
            f"открытых вхождений хеша: {raw}, зашифрованных записей: {enc}",
        )

    print()
    print(f"verify-security: {len(c.items) - c.failed}/{len(c.items)} проверок пройдено")
    return 1 if c.failed else 0


def status(cfg: Config) -> int:
    kube = Kube(cfg.deploy_kubeconfig, cfg.namespace)
    state = StateStore(kube).load()
    live = live_active_slot(kube)
    print(f"Стенд {cfg.cluster}: пользовательский адрес {cfg.ingress_url}/")
    print(f"  активный слот (Service mts-api-active): {live or '—'}")
    for slot in ("blue", "green"):
        info = deployed_slot_info(kube, slot)
        role = "ACTIVE " if slot == live else "standby"
        if info:
            print(
                f"  [{role}] {slot:5} версия={info['version']:<10} release={info['release_id']:<28} "
                f"ready={info['ready_replicas']}/{info['replicas']} digest={info['digest'][:19]}…"
            )
        else:
            print(f"  [{role}] {slot:5} не развёрнут")
    active = state.get("active") or {}
    print(
        f"  последний подтверждённый здоровый релиз: {active.get('release_id', '—')} "
        f"({active.get('version', '—')}, {active.get('digest', '')[:19]}…)"
    )
    print(f"  фаза: {state.get('phase')}; блокировка: {'занята' if kube.get_json('lease', LOCK_NAME) else 'свободна'}")
    rot = state.get("secret_rotation") or {}
    if rot:
        print(f"  последняя ротация токена: {rot.get('rotated_at')} (отпечаток {rot.get('token_fingerprint')})")
    print("  последние решения:")
    for item in (state.get("history") or [])[-8:]:
        print(
            f"    {item.get('at')}  {item.get('decision'):<14} {item.get('release_id')}  {item.get('reason', '')[:90]}"
        )
    standby = state.get("standby") or {}
    if live and standby.get("slot") == other_slot(live):
        if standby.get("healthy"):
            print(
                f"  резервный слот {standby['slot']}: подтверждённый ранее релиз {standby.get('release_id')} "
                f"— пригоден для ручного возврата ({slot_release(standby['slot'])})"
            )
        else:
            print(
                f"  резервный слот {standby['slot']}: релиз {standby.get('release_id')} НЕ прошёл проверки "
                "— не использовать для ручного возврата; следующий релиз перезапишет слот"
            )
    return 0
