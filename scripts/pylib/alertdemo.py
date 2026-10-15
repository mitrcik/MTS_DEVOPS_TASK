"""Воспроизводимый жизненный цикл алерта: реальный сбой → firing → восстановление → resolved.

Сбой: активный слот масштабируется до 0 реплик (пользовательский путь отдаёт 503).
Алерт MtsApiSyntheticProbeFailing строится на blackbox-пробе бизнес-метода через
ingress, поэтому срабатывает даже тогда, когда метрик самого приложения нет.
Операция выполняется под общей блокировкой стенда и всегда восстанавливает реплики.
"""

from __future__ import annotations

import time

from .common import Config, fail, iso, log, ok, utcnow
from .kube import Kube
from .lock import LockBusy, StandLock
from .prom import Alertmanager, Prometheus, PromUnavailable
from .report import Report
from .state import live_active_slot, slot_release

ALERT = "MtsApiSyntheticProbeFailing"


def _alert_state(prom: Prometheus) -> str | None:
    for alert in prom.alerts():
        if alert["labels"].get("alertname") == ALERT:
            return alert["state"]  # pending | firing
    return None


def run_demo(cfg: Config, timeout: float = 240) -> int:
    kube = Kube(cfg.deploy_kubeconfig, cfg.namespace)
    prom = Prometheus(cfg.ingress_url)
    am = Alertmanager(cfg.ingress_url)
    rid = f"{utcnow():%Y%m%dt%H%M%S}z"
    report = Report("alert-demo", rid, cfg.reports_dir)
    report.set("alert", ALERT)
    marks: dict[str, float] = {}
    try:
        with StandLock(kube, f"demo-alert/{rid}", wait_seconds=cfg.num("LOCK_WAIT_SECONDS", 0)) as lock:
            report.set("lock", lock.info())
            slot = live_active_slot(kube)
            if not slot:
                raise RuntimeError("нет активного слота")
            deploy = slot_release(slot)
            replicas = int(kube.get_json("deployment", deploy)["spec"]["replicas"])
            if _alert_state(prom):
                raise RuntimeError(f"{ALERT} уже активен — дождитесь resolved перед демонстрацией")
            try:
                log(f"сбой: масштабирую {deploy} до 0 реплик (было {replicas})")
                kube.kubectl("scale", "deployment", deploy, "--replicas=0")
                marks["fault_injected"] = time.time()
                report.event("fault_injected", deployment=deploy, replicas_before=replicas)
                deadline = time.time() + timeout
                while time.time() < deadline and "firing" not in marks:
                    lock.check()
                    st = _alert_state(prom)
                    if st == "pending" and "pending" not in marks:
                        marks["pending"] = time.time()
                        report.event("alert_pending")
                        log("алерт в состоянии pending")
                    if st == "firing":
                        marks["firing"] = time.time()
                        report.event("alert_firing")
                        ok(f"алерт {ALERT} в состоянии firing")
                    time.sleep(2)
                while time.time() < deadline and "alertmanager_received" not in marks and "firing" in marks:
                    received = am.alerts(ALERT)
                    if received:
                        marks["alertmanager_received"] = time.time()
                        receivers = sorted({r["name"] for a in received for r in a.get("receivers", [])})
                        report.event(
                            "alertmanager_received", receivers=receivers, severity=received[0]["labels"].get("severity")
                        )
                        ok(f"Alertmanager получил алерт, маршрут → {receivers}")
                    time.sleep(2)
            finally:
                log(f"восстановление: возвращаю {deploy} к {replicas} репликам")
                kube.kubectl("scale", "deployment", deploy, f"--replicas={replicas}")
                kube.kubectl("rollout", "status", f"deployment/{deploy}", "--timeout=120s", timeout=150)
                marks["restored"] = time.time()
                report.event("service_restored")
            deadline = time.time() + timeout
            while time.time() < deadline:
                if _alert_state(prom) is None and not am.alerts(ALERT):
                    marks["resolved"] = time.time()
                    report.event("alert_resolved")
                    ok(f"алерт {ALERT} resolved")
                    break
                time.sleep(3)
    except LockBusy as exc:
        fail(str(exc))
        report.finish("blocked", str(exc))
        return 10
    except (RuntimeError, PromUnavailable) as exc:
        fail(str(exc))
        report.finish("failed", str(exc))
        return 1

    t0 = marks.get("fault_injected", time.time())
    report.set("timeline_seconds_from_fault", {k: round(v - t0, 1) for k, v in marks.items()})
    report.set("notes", "длительности зависят от scrape 5s, evaluation 5s и for: 30s демо-профиля правил")
    complete = all(k in marks for k in ("firing", "alertmanager_received", "restored", "resolved"))
    report.finish(
        "firing_and_resolved" if complete else "incomplete", None if complete else f"наблюдаемые этапы: {sorted(marks)}"
    )
    log(f"хронология (с от начала сбоя): {report.data['timeline_seconds_from_fault']} [{iso(utcnow())}]")
    return 0 if complete else 1
