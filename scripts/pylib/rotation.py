"""Ротация учебного API-токена с перекрытием (overlap), под общей блокировкой стенда.

Фазы:
  1. overlap: в SOPS-источнике current=новый, previous=старый; Secret содержит оба хеша.
     Ждём, пока КАЖДЫЙ pod ОБОИХ слотов примет новый токен.
  2. revoke: previous удаляется; Secret содержит только новый хеш.
     Ждём, пока каждый pod обоих слотов отвергнет старый токен и примет новый.
  3. проверка через пользовательский ingress: новый → 200, старый → 401.
Оба слота читают один Secret как файл, поэтому возврат трафика на любой слот
не возвращает отозванный токен.
"""

from __future__ import annotations

import time

from . import secrets as sec
from .common import Config, fail, iso, log, ok, utcnow
from .httpprobe import QUOTE_PAYLOAD, request
from .kube import Kube, pod_ready
from .lock import LockBusy, StandLock
from .report import Report
from .state import StateStore


def _ready_pods(kube: Kube) -> list[str]:
    data = kube.get_json("pods", "-l", "app.kubernetes.io/name=mts-api") or {}
    return sorted(p["metadata"]["name"] for p in data.get("items", []) if pod_ready(p))


def _nudge(kube: Kube, pods: list[str], marker: str) -> None:
    """Изменение аннотации pod заставляет kubelet сразу пересинхронизировать volume Secret."""
    for pod in pods:
        kube.kubectl("annotate", "pod", pod, f"mts-devops/secret-sync={marker}", "--overwrite", check=False)


def _statuses(kube: Kube, pod: str, tokens: dict[str, str]) -> dict[str, int]:
    """Один port-forward на pod: коды ответа метода расчёта для каждого токена."""
    with kube.port_forward(f"pod/{pod}") as port:
        return {
            name: request(
                "POST",
                f"http://127.0.0.1:{port}/api/v1/quotes",
                headers={"Authorization": f"Bearer {tok}"},
                payload=QUOTE_PAYLOAD,
            ).status
            for name, tok in tokens.items()
        }


def _wait_pods(kube: Kube, pods: list[str], expect: dict[str, tuple[str, int]], timeout: float) -> dict:
    """expect: {имя: (токен, ожидаемый HTTP-код)}. Ждёт сходимости во всех pod."""
    tokens = {name: tok for name, (tok, _) in expect.items()}
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = {pod: _statuses(kube, pod, tokens) for pod in pods}
        if all(last[p][name] == code for p in pods for name, (_, code) in expect.items()):
            return {"converged": True, "statuses": last}
        time.sleep(3)
    return {"converged": False, "statuses": last}


def save_current_token(cfg: Config, path: str) -> None:
    """Для приёмочного сценария: сохранить действующий токен (0600), чтобы после ротации
    проверить его отзыв. Значение не печатается."""
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(sec.current_token(cfg))


def check_revoked(cfg: Config, old_token_path: str) -> int:
    """Отозванный токен отвергается, действующий принимается: через ingress и в каждом pod обоих слотов."""
    kube = Kube(cfg.deploy_kubeconfig, cfg.namespace)
    with open(old_token_path, encoding="utf-8") as fh:
        old = fh.read().strip()
    new = sec.current_token(cfg)
    if old == new:
        fail("сохранённый токен совпадает с действующим — ротации не было")
        return 1
    url = cfg.ingress_url + "/api/v1/quotes"
    results = {
        "ingress": {
            "current": request("POST", url, headers={"Authorization": f"Bearer {new}"}, payload=QUOTE_PAYLOAD).status,
            "revoked": request("POST", url, headers={"Authorization": f"Bearer {old}"}, payload=QUOTE_PAYLOAD).status,
        }
    }
    for pod in _ready_pods(kube):
        st = _statuses(kube, pod, {"current": new, "revoked": old})
        results[pod] = st
    good = all(r["current"] == 200 and r["revoked"] == 401 for r in results.values())
    for name, r in results.items():
        (ok if r["current"] == 200 and r["revoked"] == 401 else fail)(
            f"{name}: действующий токен → {r['current']}, отозванный → {r['revoked']}"
        )
    return 0 if good else 1


def rotate(cfg: Config) -> int:
    kube = Kube(cfg.deploy_kubeconfig, cfg.namespace)
    rid = f"{utcnow():%Y%m%dt%H%M%S}z"
    report = Report("rotation", rid, cfg.reports_dir)
    report.set("strategy", "overlap: новый и старый токен действуют одновременно до подтверждения во всех pod")
    try:
        with StandLock(kube, f"rotate-secret/{rid}", wait_seconds=cfg.num("LOCK_WAIT_SECONDS", 0)) as lock:
            report.set("lock", lock.info())
            data = sec.read_source(cfg)
            old = data["api_tokens"]["current"]
            new = sec.new_token()
            fp_old, fp_new = sec.token_fingerprint(old), sec.token_fingerprint(new)
            report.set("tokens", {"old_fingerprint": fp_old, "new_fingerprint": fp_new})
            pods = _ready_pods(kube)
            report.set("pods", pods)
            log(f"ротация токена {fp_old} → {fp_new}; pod обоих слотов: {pods}")

            # фаза 1: перекрытие
            data["api_tokens"] = {"current": new, "previous": old}
            data["rotated_at"] = iso(utcnow())
            sec.write_source(cfg, data)
            sec.apply_api_secret(cfg, kube, data)
            report.event("overlap_applied")
            _nudge(kube, pods, f"{rid}-overlap")
            res = _wait_pods(kube, pods, {"new": (new, 200), "old": (old, 200)}, timeout=150)
            report.check("overlap_all_pods_accept_new", "passed" if res["converged"] else "failed", **res)
            if not res["converged"]:
                raise RuntimeError("не все pod приняли новый токен за 150 с (оставлено перекрытие — безопасно)")
            lock.check()

            # фаза 2: отзыв старого токена
            data["api_tokens"] = {"current": new, "previous": ""}
            sec.write_source(cfg, data)
            sec.apply_api_secret(cfg, kube, data)
            report.event("old_token_revoked")
            _nudge(kube, pods, f"{rid}-revoke")
            res = _wait_pods(kube, pods, {"new": (new, 200), "old": (old, 401)}, timeout=150)
            report.check("revoke_all_pods", "passed" if res["converged"] else "failed", **res)
            if not res["converged"]:
                raise RuntimeError("старый токен ещё принимается некоторыми pod")

            # фаза 3: пользовательский путь
            url = cfg.ingress_url + "/api/v1/quotes"
            via_new = request("POST", url, headers={"Authorization": f"Bearer {new}"}, payload=QUOTE_PAYLOAD)
            via_old = request("POST", url, headers={"Authorization": f"Bearer {old}"}, payload=QUOTE_PAYLOAD)
            passed = via_new.status == 200 and via_old.status == 401
            report.check(
                "ingress",
                "passed" if passed else "failed",
                new_token_status=via_new.status,
                old_token_status=via_old.status,
            )
            if not passed:
                raise RuntimeError("проверка через ingress не пройдена")

            store = StateStore(kube)
            state = store.load()
            state["secret_rotation"] = {"rotated_at": data["rotated_at"], "token_fingerprint": fp_new, "report": rid}
            store.save(state)
            ok(f"ротация завершена: новый токен {fp_new} работает во всех pod, старый {fp_old} отклоняется")
            report.finish("rotated", None)
            return 0
    except LockBusy as exc:
        fail(str(exc))
        report.finish("blocked", str(exc))
        return 10
    except Exception as exc:  # noqa: BLE001 - любой сбой фиксируется в отчёте ротации
        fail(f"ротация не завершена: {exc}")
        report.finish("failed", str(exc)[:400])
        return 1
