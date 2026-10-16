"""Общая блокировка изменений стенда в самом кластере (coordination.k8s.io/v1 Lease).

Релизы, ротация секрета и демонстрация алерта берут одну и ту же блокировку,
поэтому не могут менять слоты одновременно — даже если запущены с разных машин.
Захват атомарен (create завершается AlreadyExists, если блокировка занята);
продление и перехват просроченной блокировки — через replace с resourceVersion
(оптимистическая конкуренция на стороне API-сервера).
"""

from __future__ import annotations

import json
import threading
import time

from .common import hostname, iso, log, parse_iso, utcnow, warn
from .kube import Kube

LOCK_NAME = "mts-api-change-lock"


class LockBusy(RuntimeError):
    pass


class LockLost(RuntimeError):
    pass


def _micro(ts) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class StandLock:
    def __init__(self, kube: Kube, purpose: str, ttl: int = 120, wait_seconds: float = 0) -> None:
        self.kube = kube
        self.purpose = purpose
        self.ttl = ttl
        self.wait_seconds = wait_seconds
        self.holder = f"{purpose}@{hostname()}#{int(time.time() * 1000) % 10**9}"
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None
        self.acquired_at = None

    def _body(self, resource_version: str | None = None, acquire_time: str | None = None) -> str:
        now = utcnow()
        meta: dict = {
            "name": LOCK_NAME,
            "namespace": self.kube.namespace,
            "labels": {"app.kubernetes.io/part-of": "mts-devops"},
            "annotations": {"mts-devops/purpose": self.purpose, "mts-devops/host": hostname()},
        }
        if resource_version:
            meta["resourceVersion"] = resource_version
        return json.dumps(
            {
                "apiVersion": "coordination.k8s.io/v1",
                "kind": "Lease",
                "metadata": meta,
                "spec": {
                    "holderIdentity": self.holder,
                    "leaseDurationSeconds": self.ttl,
                    "acquireTime": acquire_time or _micro(now),
                    "renewTime": _micro(now),
                },
            }
        )

    def describe_current(self) -> str:
        lease = self.kube.get_json("lease", LOCK_NAME)
        if not lease:
            return "блокировка свободна"
        spec = lease.get("spec", {})
        purpose = lease.get("metadata", {}).get("annotations", {}).get("mts-devops/purpose", "?")
        return (
            f"держатель={spec.get('holderIdentity')} цель={purpose} "
            f"с {spec.get('acquireTime')} продлена {spec.get('renewTime')}"
        )

    def _try_acquire(self) -> bool:
        proc = self.kube.kubectl("create", "-f", "-", input_text=self._body(), check=False)
        if proc.returncode == 0:
            return True
        if "AlreadyExists" not in proc.stderr and "already exists" not in proc.stderr:
            raise RuntimeError(f"не удалось создать Lease: {proc.stderr.strip()}")
        lease = self.kube.get_json("lease", LOCK_NAME)
        if lease is None:
            return False
        spec = lease.get("spec", {})
        renew = spec.get("renewTime")
        duration = int(spec.get("leaseDurationSeconds") or self.ttl)
        if renew and (utcnow() - parse_iso(renew)).total_seconds() > duration:
            warn(f"блокировка просрочена ({self.describe_current()}); перехватываю")
            rv = lease["metadata"]["resourceVersion"]
            taken = self.kube.kubectl("replace", "-f", "-", input_text=self._body(rv), check=False)
            return taken.returncode == 0
        return False

    def _renew_loop(self) -> None:
        # Временная ошибка API (таймаут, перезапуск сервера) — повтор на следующем тике. Если
        # продлить не удаётся дольше половины срока аренды, блокировка считается потерянной
        # (её могут перехватить по истечении ttl), и операция останавливается на lock.check().
        last_ok = time.monotonic()
        while not self._stop.wait(self.ttl / 3):
            try:
                lease = self.kube.get_json("lease", LOCK_NAME)
                if not lease or lease.get("spec", {}).get("holderIdentity") != self.holder:
                    self._lost.set()
                    return
                body = self._body(lease["metadata"]["resourceVersion"], lease["spec"].get("acquireTime"))
                if self.kube.kubectl("replace", "-f", "-", input_text=body, check=False).returncode == 0:
                    last_ok = time.monotonic()
                    continue
            except Exception as exc:  # noqa: BLE001 — любая ошибка продления обрабатывается одинаково
                warn(f"продление блокировки не удалось: {str(exc)[:200]}")
            if time.monotonic() - last_ok >= self.ttl / 2:
                self._lost.set()
                return

    def check(self) -> None:
        if self._lost.is_set():
            raise LockLost("блокировка стенда потеряна — операция прервана для безопасности")

    def __enter__(self) -> StandLock:
        deadline = time.monotonic() + self.wait_seconds
        while not self._try_acquire():
            if time.monotonic() >= deadline:
                raise LockBusy(
                    f"стенд занят другой операцией ({self.describe_current()}). "
                    "Дождитесь её завершения или задайте LOCK_WAIT_SECONDS."
                )
            time.sleep(2)
        self.acquired_at = utcnow()
        log(f"блокировка стенда получена: {self.holder}")
        self._thread = threading.Thread(target=self._renew_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        lease = self.kube.get_json("lease", LOCK_NAME)
        if lease and lease.get("spec", {}).get("holderIdentity") == self.holder:
            rv = lease["metadata"]["resourceVersion"]
            # удаление с предусловием resourceVersion: не снимем чужую блокировку
            body = json.dumps({"kind": "DeleteOptions", "apiVersion": "v1", "preconditions": {"resourceVersion": rv}})
            self.kube.kubectl(
                "delete",
                "--raw",
                f"/apis/coordination.k8s.io/v1/namespaces/{self.kube.namespace}/leases/{LOCK_NAME}",
                "-f",
                "-",
                input_text=body,
                check=False,
            )
            log("блокировка стенда освобождена")

    def info(self) -> dict:
        return {"holder": self.holder, "purpose": self.purpose, "acquired_at": iso(self.acquired_at)}
