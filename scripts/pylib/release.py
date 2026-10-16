"""Release controller: blue-green с проверкой кандидата и автоматическим возвратом трафика.

Алгоритм (docs/architecture.md, раздел «Релиз»):
  1. общая блокировка стенда (Lease в кластере);
  2. фактический активный слот = селектор Service mts-api-active; восстановление
     после прерванной операции;
  3. новый digest — только в неактивный слот (helm --wait --rollback-on-failure);
  4. preview-проверки каждого pod кандидата напрямую (port-forward), до переключения;
  5. проверка, что Prometheus видит и скрейпит кандидата (иначе — отказ, fail closed);
  6. переключение Service через единственного владельца — релиз mts-api-traffic;
  7. post-deploy окно: поток бизнес-запросов через реальный ingress + metrics gate;
  8. promoted, либо возврат трафика на прежний здоровый слот и проверка восстановления.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import secrets as sec
from .common import ROOT, CmdError, Config, fail, iso, log, ok, run, tool, utcnow, warn
from .gate import (
    GateResult,
    MetricsSnapshot,
    Thresholds,
    evaluate_http,
    evaluate_metrics,
    fail_fast,
    summarize_http,
)
from .httpprobe import QUOTE_EXPECTED_TOTAL, QUOTE_PAYLOAD, LoadGenerator, request
from .kube import Kube, pod_image_digest, pod_ready
from .lock import LockBusy, StandLock
from .prom import Prometheus, PromUnavailable
from .report import Report
from .state import (
    TRAFFIC_RELEASE,
    StateStore,
    deployed_slot_info,
    live_active_slot,
    other_slot,
    slot_release,
)

EXIT = {
    "promoted": 0,
    "noop": 0,
    "rejected": 2,
    "rolled_back": 3,
    "failed": 4,
    "rollback_failed": 5,
    "blocked": 10,
    "error": 1,
}

IMAGE_RE = re.compile(r"^(?P<repo>[a-z0-9][a-z0-9._/:-]*[a-z0-9])@(?P<digest>sha256:[0-9a-f]{64})$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}(-dirty)?$")


@dataclass
class Artifact:
    image: str
    repo: str
    digest: str
    version: str
    git_sha: str
    provenance: dict

    @classmethod
    def from_provenance(cls, path: Path) -> Artifact:
        prov = json.loads(path.read_text(encoding="utf-8"))
        image = prov["image"]["ref"]
        m = IMAGE_RE.match(image)
        if not m:
            raise SystemExit(f"provenance: ссылка на образ должна быть по digest, получено {image!r}")
        version, git_sha = prov["version"], prov["git_sha"]
        if not VERSION_RE.match(version) or not SHA_RE.match(git_sha):
            raise SystemExit("provenance: некорректные version/git_sha")
        trivy = prov.get("trivy", {})
        if trivy.get("result") != "passed" or prov["image"].get("digest") != m.group("digest"):
            raise SystemExit(
                "релиз разрешён только для digest, прошедшего Trivy-политику в этом же pipeline "
                f"(trivy.result={trivy.get('result')!r})"
            )
        return cls(image, m.group("repo"), m.group("digest"), version, git_sha, prov)

    def as_dict(self) -> dict:
        return {
            "image": self.image,
            "digest": self.digest,
            "version": self.version,
            "git_sha": self.git_sha,
            "provenance": {
                "stages": self.provenance.get("stages"),
                "trivy": self.provenance.get("trivy"),
                "built_at": self.provenance.get("build_time"),
                "base_image": self.provenance.get("base_image"),
                "local_image_id": self.provenance.get("image", {}).get("local_id"),
            },
        }


def tool_versions(kube: Kube) -> dict:
    def first(cmd: list[str]) -> str:
        try:
            return run(cmd, timeout=15, check=False).stdout.strip().splitlines()[0]
        except (IndexError, OSError):
            return "unknown"

    return {
        "kubectl": first([tool("kubectl"), "version", "--client"]).replace("Client Version: ", ""),
        "helm": first([tool("helm"), "version", "--short"]),
        "k3s_server": kube.server_version(),
    }


class ReleaseController:
    def __init__(self, cfg: Config, artifact: Artifact | None) -> None:
        self.cfg = cfg
        self.art = artifact
        self.kube = Kube(cfg.deploy_kubeconfig, cfg.namespace)
        self.store = StateStore(self.kube)
        self.prom = Prometheus(cfg.ingress_url)
        self.t = Thresholds(
            min_http_requests=int(cfg.num("MIN_HTTP_REQUESTS", 120)),
            min_metric_requests=int(cfg.num("MIN_METRIC_REQUESTS", 60)),
            max_error_ratio=cfg.num("MAX_ERROR_RATIO", 0.02),
            max_p95_seconds=cfg.num("MAX_P95_SECONDS", 0.5),
        )
        self.window = cfg.num("POST_DEPLOY_WINDOW_SECONDS", 30)
        self.rps = cfg.num("LOAD_RPS", 8)
        self.deploy_timeout = int(cfg.num("DEPLOY_TIMEOUT_SECONDS", 120))
        self.scrape_wait = cfg.num("SCRAPE_WAIT_SECONDS", 12)
        stamp = f"{utcnow():%Y%m%dt%H%M%S}z"
        if artifact is None:  # режим восстановления без нового артефакта
            self.release_id = f"recover-{stamp}"
            self.report = Report("recovery", self.release_id, cfg.reports_dir)
        else:
            self.release_id = f"{artifact.version}-{stamp}".lower()
            self.report = Report("release", self.release_id, cfg.reports_dir)
        self.lock: StandLock | None = None
        self.token = ""
        self._t0 = time.time()
        self._marks: dict[str, float] = {}

    def _mark(self, name: str, **fields) -> None:
        self._marks[name] = round(time.time() - self._t0, 1)
        self.report.event(name, **fields)

    # ------------------------------------------------------------------ public
    def recover(self) -> str:
        """Только восстановление: под блокировкой вернуть трафик на последний подтверждённый
        релиз, если предыдущая операция прервана, и снять зависшие Helm-релизы."""
        try:
            with StandLock(self.kube, self.release_id, wait_seconds=self.cfg.num("LOCK_WAIT_SECONDS", 0)) as lock:
                self.lock = lock
                state = self.store.load()
                live = live_active_slot(self.kube)
                phase = state.get("phase") or "idle"
                self.report.set(
                    "before",
                    {"phase": phase, "live_slot": live, "last_healthy": (state.get("active") or {}).get("release_id")},
                )
                if live:
                    self._unstick_helm(slot_release(other_slot(live)))
                if phase == "idle":
                    ok("прерванных операций нет — стенд в согласованном состоянии")
                    return self._finish("nothing_to_recover", None)
                live = self._recover_if_interrupted(state, live)
                self.report.set("after", {"live_slot": live})
                return self._finish("recovered", f"прервана операция в фазе {phase}")
        except LockBusy as exc:
            fail(str(exc))
            return self._finish("blocked", str(exc))

    def run(self) -> str:
        self.report.set("artifact", self.art.as_dict())
        self.report.set("thresholds", self.t.__dict__ | {"window_seconds": self.window, "rps": self.rps})
        try:
            with StandLock(
                self.kube, f"release/{self.release_id}", wait_seconds=self.cfg.num("LOCK_WAIT_SECONDS", 0)
            ) as lock:
                self.lock = lock
                self.report.set("lock", lock.info())
                return self._run_locked()
        except LockBusy as exc:
            fail(str(exc))
            return self._finish("blocked", str(exc))
        except Exception as exc:
            fail(f"релиз прерван ошибкой: {exc}")
            self.report.event("error", error=str(exc)[:500])
            self._finish("error", str(exc)[:500])
            raise

    # ------------------------------------------------------------- main flow
    def _run_locked(self) -> str:
        state = self.store.load()
        live = live_active_slot(self.kube)
        live = self._recover_if_interrupted(state, live)

        prev_slot = live
        prev_info = deployed_slot_info(self.kube, prev_slot) if prev_slot else None
        cand = other_slot(prev_slot) if prev_slot else "blue"
        self.report.set("tools", tool_versions(self.kube))
        self.report.set(
            "slots",
            {
                "previous": prev_info,
                "candidate": {
                    "slot": cand,
                    "digest": self.art.digest,
                    "version": self.art.version,
                    "release_id": self.release_id,
                },
            },
        )
        active = state.get("active") or {}
        if active.get("digest") == self.art.digest and active.get("slot") == live and active.get("healthy", True):
            ok(f"digest уже активен в слоте {live} (релиз {active.get('release_id')}) — изменений нет")
            self.report.event("noop", active_release=active.get("release_id"))
            return self._finish("noop", "этот digest уже обслуживает пользователей")
        if prev_slot is None:
            warn("первое развёртывание: предыдущего здорового слота нет, возврат трафика невозможен")

        self.token = sec.current_token(self.cfg)
        state.update(
            phase="deploying",
            operation=self.release_id,
            previous_slot=prev_slot,
            candidate={
                "slot": cand,
                "digest": self.art.digest,
                "version": self.art.version,
                "release_id": self.release_id,
            },
        )
        self.store.save(state)

        # 3. развёртывание в неактивный слот
        self._mark("deploy_started", slot=cand)
        good, detail = self._deploy_candidate(cand)
        self.report.check("candidate_ready", "passed" if good else "failed", **detail)
        if not good:
            return self._reject(state, cand, "candidate_not_ready", detail.get("summary"))
        self._mark("candidate_ready")
        self.lock.check()

        # 4. preview каждого pod кандидата напрямую
        good, detail, pods = self._preview(cand)
        self.report.check("preview", "passed" if good else "failed", **detail)
        if not good:
            return self._reject(state, cand, "preview_failed", detail.get("summary"))
        self._mark("preview_passed", probes=len(detail.get("probes", [])))

        # 5. наблюдаемость обязана видеть кандидата до переключения
        good, detail = self._metrics_precheck(cand, pods)
        self.report.check("metrics_precheck", "passed" if good else "failed", **detail)
        if not good:
            return self._reject(state, cand, "metrics_unavailable", detail.get("summary"))
        self._mark("metrics_precheck_passed")
        self.lock.check()

        # 6-7. переключение и post-deploy окно под пользовательской нагрузкой
        load = LoadGenerator(self.cfg.ingress_url, self.token, self.rps).start()
        try:
            time.sleep(2)  # трафик идёт и до переключения: видно поведение в момент switch
            state["phase"] = "switching"
            self.store.save(state)
            switch_started = time.time()
            self._switch(cand)
            self.report.set("switched_at", iso(utcnow()))
            self._mark("traffic_switched", to=cand, previous=prev_slot)
            state["phase"] = "observing"
            self.store.save(state)

            cutover = self._wait_cutover(load, self.release_id, since=switch_started)
            if cutover is None:
                http_res = GateResult(
                    False,
                    ["пользовательский ingress не начал отдавать кандидата за 20 с"],
                    summarize_http(load.snapshot(since=switch_started), self.release_id),
                )
                metrics_res = GateResult(False, ["не оценивалось"], {})
            else:
                self._mark("cutover_observed", seconds_after_switch=round(cutover - switch_started, 2))
                http_res = self._observe_window(load, cutover)
                # при провале HTTP-gate метрики не ждём: сначала возврат трафика, доказательства — после
                metrics_res = (
                    self._metrics_gate(cand, pods, cutover)
                    if http_res.passed
                    else GateResult(False, ["не оценивалось: HTTP-gate уже провален"], {})
                )
            switch_window = load.snapshot(since=switch_started - 2, until=(cutover or time.time()) + 2)
            self.report.check(
                "switch_impact",
                "measured",
                requests=len(switch_window),
                failed=sum(1 for s in switch_window if not s.ok and s.release_id != self.release_id),
                note=(
                    "первое развёртывание: до переключения маршрута к API не было"
                    if prev_slot is None
                    else "ошибки прежнего релиза в окне ±2 с вокруг переключения (ошибки кандидата учитывает gate)"
                ),
            )
            self.report.check("post_deploy_http", "passed" if http_res.passed else "failed", **http_res.as_dict())
            self.report.check("metrics_gate", "passed" if metrics_res.passed else "failed", **metrics_res.as_dict())

            if http_res.passed and metrics_res.passed:
                return self._promote(state, cand, prev_info)
            reasons = http_res.reasons if not http_res.passed else metrics_res.reasons
            return self._handle_failure(state, load, cand, prev_slot, prev_info, "; ".join(reasons), pods, cutover)
        finally:
            load.stop()

    # ------------------------------------------------------------ recovery
    def _recover_if_interrupted(self, state: dict, live: str | None) -> str | None:
        phase = state.get("phase") or "idle"
        if phase == "idle":
            return live
        warn(f"обнаружена прерванная операция {state.get('operation')} в фазе {phase}")
        self.report.event("recovering_interrupted_operation", phase=phase, operation=state.get("operation"))
        # Возврат — на слот, обслуживавший пользователей до прерванной операции (previous_slot);
        # state.active — запасной вариант для состояния, записанного до появления previous_slot.
        target = state.get("previous_slot") or (state.get("active") or {}).get("slot")
        switched = False
        if target and live != target:
            self._switch(target)
            live, switched = target, True
        target_info = deployed_slot_info(self.kube, target) if target else None
        if target_info:
            # восстановление подтверждается на пользовательском пути, а не только селектором Service
            release_id = target_info.get("release_id", "")
            seen = self._await_ingress_release(release_id)
            self.report.event(
                "traffic_restored_to_previous" if switched else "traffic_confirmed_on_previous",
                slot=target,
                release_id=release_id,
                ingress_confirmed=seen,
            )
            if not seen:
                raise RuntimeError(f"ingress не начал отдавать релиз {release_id} слота {target} за 30 с")
            ok(f"трафик на слоте {target}; ingress отдаёт {release_id}")
        # кандидат прерванной операции не прошёл проверки — резервный слот непригоден для возврата
        cand = (state.get("candidate") or {}).get("slot")
        if cand and cand != live:
            prev_standby = state.get("standby") or {}
            actual = deployed_slot_info(self.kube, cand)
            if not (actual and actual.get("release_id") == prev_standby.get("release_id")):
                state["standby"] = {**(actual or {"slot": cand}), "healthy": False}
        state["history"].append(
            {"release_id": state.get("operation"), "decision": "interrupted", "phase": phase, "at": iso(utcnow())}
        )
        state.update(phase="idle", operation=None, candidate=None)
        self.store.save(state)
        return live

    def _await_ingress_release(self, release_id: str, timeout: float = 30, streak: int = 5) -> bool:
        """Ждать, пока пользовательский ingress streak раз подряд отдаст указанный release id."""
        deadline = time.time() + timeout
        count = 0
        while time.time() < deadline:
            resp = request("GET", self.cfg.ingress_url + "/version", timeout=3)
            count = count + 1 if resp.status == 200 and resp.json().get("release_id") == release_id else 0
            if count >= streak:
                return True
            time.sleep(0.3)
        return False

    # ------------------------------------------------------------- phases
    def _deploy_candidate(self, cand: str) -> tuple[bool, dict]:
        log(f"разворачиваю {self.art.image} в слот {cand} (helm --wait, таймаут {self.deploy_timeout}s)")
        self._unstick_helm(slot_release(cand))
        started = time.time()
        args = [
            "upgrade",
            "--install",
            slot_release(cand),
            str(ROOT / "charts" / "app"),
            "--wait",
            "--rollback-on-failure",
            "--timeout",
            f"{self.deploy_timeout}s",
            "--history-max",
            "5",
            "--set-string",
            f"slot={cand}",
            "--set-string",
            f"image.repository={self.art.repo}",
            "--set-string",
            f"image.digest={self.art.digest}",
            "--set-string",
            f"release.id={self.release_id}",
            "--set-string",
            f"release.version={self.art.version}",
            "--set-string",
            f"release.gitSha={self.art.git_sha}",
        ]
        try:
            self.kube.helm(*args, timeout=self.deploy_timeout + 90)
        except CmdError as exc:
            diag = self._pod_diagnostics(cand)
            fail(f"кандидат не стал готовым: {exc}")
            return False, {
                "duration_s": round(time.time() - started, 1),
                "summary": "helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии",
                "helm_error": str(exc)[-400:],
                "pods": diag,
            }
        ok(f"слот {cand} готов за {time.time() - started:.1f} с")
        return True, {"duration_s": round(time.time() - started, 1)}

    def _pod_diagnostics(self, cand: str) -> list[dict]:
        data = self.kube.get_json("pods", "-l", f"app.kubernetes.io/name=mts-api,slot={cand}") or {}
        out = []
        for pod in data.get("items", []):
            st = pod.get("status", {})
            cs = (st.get("containerStatuses") or [{}])[0]
            out.append(
                {
                    "pod": pod["metadata"]["name"],
                    "phase": st.get("phase"),
                    "ready": pod_ready(pod),
                    "restarts": cs.get("restartCount"),
                    "state": list((cs.get("state") or {}).keys()),
                }
            )
        return out

    def _candidate_pods(self, cand: str) -> list[str]:
        data = self.kube.get_json("pods", "-l", f"app.kubernetes.io/name=mts-api,slot={cand}") or {}
        return sorted(
            p["metadata"]["name"]
            for p in data.get("items", [])
            if pod_ready(p) and pod_image_digest(p) == self.art.digest
        )

    def _preview(self, cand: str) -> tuple[bool, dict, list[str]]:
        pods = self._candidate_pods(cand)
        if not pods:
            return False, {"summary": "нет готовых pod с ожидаемым digest"}, []
        probes = []
        auth = {"Authorization": f"Bearer {self.token}"}
        for pod in pods:
            with self.kube.port_forward(f"pod/{pod}") as port:
                base = f"http://127.0.0.1:{port}"
                ver = request("GET", base + "/version")
                quote = request("POST", base + "/api/v1/quotes", headers=auth, payload=QUOTE_PAYLOAD)
                metrics = request("GET", base + "/metrics")
                checks = [
                    ("healthz", request("GET", base + "/healthz").status == 200),
                    ("readyz", request("GET", base + "/readyz").status == 200),
                    (
                        "version_matches_release",
                        ver.status == 200
                        and ver.json().get("release_id") == self.release_id
                        and ver.json().get("version") == self.art.version
                        and ver.json().get("git_sha") == self.art.git_sha
                        and ver.json().get("slot") == cand,
                    ),
                    ("list_tariffs", request("GET", base + "/api/v1/tariffs").status == 200),
                    ("quote_known_answer", quote.status == 200 and quote.json().get("total") == QUOTE_EXPECTED_TOTAL),
                    (
                        "quote_without_token_401",
                        request("POST", base + "/api/v1/quotes", payload=QUOTE_PAYLOAD).status == 401,
                    ),
                    (
                        "quote_invalid_input_422",
                        request(
                            "POST", base + "/api/v1/quotes", headers=auth, payload={**QUOTE_PAYLOAD, "minutes": -5}
                        ).status
                        == 422,
                    ),
                    (
                        "metrics_expose_release",
                        metrics.status == 200 and f'release_id="{self.release_id}"' in metrics.body.decode(),
                    ),
                ]
            for name, passed in checks:
                probes.append({"pod": pod, "probe": name, "passed": passed})
        failed = [p for p in probes if not p["passed"]]
        summary = f"{len(probes) - len(failed)}/{len(probes)} проверок прошли" + (
            f"; провал: {[f['probe'] + '@' + f['pod'] for f in failed]}" if failed else ""
        )
        (ok if not failed else fail)(f"preview {cand}: {summary}")
        return not failed, {"summary": summary, "pods": pods, "probes": probes}, pods

    def _metrics_precheck(self, cand: str, pods: list[str]) -> tuple[bool, dict]:
        deadline = time.time() + 60
        try:
            if not self.prom.ready():
                return False, {"summary": "Prometheus недоступен — релиз без наблюдаемости запрещён"}
            while time.time() < deadline:
                ups = {m.get("pod"): v for m, v in self.prom.query(f'up{{job="mts-api",slot="{cand}"}}')}
                if pods and all(ups.get(p) == 1 for p in pods):
                    ok(f"Prometheus скрейпит все pod кандидата: {pods}")
                    return True, {"summary": "кандидат виден в Prometheus", "targets": ups}
                time.sleep(3)
        except PromUnavailable as exc:
            return False, {"summary": f"Prometheus недоступен: {exc}"}
        return False, {"summary": "Prometheus не начал скрейпить pod кандидата за 60 с"}

    def _unstick_helm(self, release: str) -> None:
        """Снять «зависшее» состояние Helm (pending-*) после прерванного процесса.

        Вызывается только под общей блокировкой стенда, поэтому pending-статус гарантированно
        оставлен мёртвым процессом, а не идущей операцией. Применяется к неактивному слоту и к
        релизу маршрутизации — релиз активного слота контроллер никогда не обновляет.
        """
        proc = self.kube.helm("history", release, "-o", "json", "--max", "20", check=False)
        if proc.returncode != 0:
            return  # релиза ещё нет
        history = json.loads(proc.stdout or "[]")
        if not history or not str(history[-1].get("status", "")).startswith("pending"):
            return
        stuck = history[-1]
        good = [h for h in history if h.get("status") in ("deployed", "superseded")]
        if good:
            target = good[-1]["revision"]
            self.kube.helm("rollback", release, str(target), "--wait", "--timeout", "120s", timeout=180)
        else:
            self.kube.helm("uninstall", release, "--wait", "--timeout", "120s", timeout=180)
            target = None
        warn(
            f"Helm-релиз {release} был в состоянии {stuck['status']} (прерванный процесс); "
            f"{'откат к ревизии ' + str(target) if target else 'удалён'}"
        )
        self.report.event("helm_release_unstuck", release=release, status=stuck["status"], rollback_to=target)

    def _switch(self, slot: str) -> None:
        log(f"переключаю стабильный Service mts-api-active на слот {slot}")
        self._unstick_helm(TRAFFIC_RELEASE)
        self.kube.helm(
            "upgrade",
            "--install",
            TRAFFIC_RELEASE,
            str(ROOT / "charts" / "traffic"),
            "--wait",
            "--timeout",
            "60s",
            "--history-max",
            "10",
            "--set-string",
            f"activeSlot={slot}",
            "--set-string",
            f"releaseId={self.release_id}",
            timeout=120,
        )
        actual = live_active_slot(self.kube)
        if actual != slot:
            raise RuntimeError(f"после переключения селектор указывает на {actual}, ожидался {slot}")

    @staticmethod
    def _wait_cutover(
        load: LoadGenerator, release_id: str, since: float, timeout: float = 20, streak: int = 5
    ) -> float | None:
        """Момент, с которого ingress стабильно (streak ответов подряд) отдаёт нужный релиз."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            samples = [s for s in load.snapshot(since=since) if s.release_id]
            run_start, count = None, 0
            for s in samples:
                if s.release_id == release_id:
                    run_start = run_start if count else s.wall
                    count += 1
                else:
                    run_start, count = None, 0
            if count >= streak and run_start is not None:
                return run_start
            time.sleep(0.5)
        return None

    def _observe_window(self, load: LoadGenerator, cutover: float) -> GateResult:
        log(f"post-deploy окно {self.window:.0f} с: ~{self.rps:.0f} бизнес-запросов/с через ingress")
        end = cutover + self.window
        reason = None
        while time.time() < end:
            self.lock.check()
            time.sleep(2)
            reason = fail_fast(load.snapshot(since=cutover), self.t)
            if reason:
                fail(f"ранняя остановка окна: {reason}")
                self.report.event("fail_fast", reason=reason)
                break
        summary = summarize_http(load.snapshot(since=cutover), self.release_id)
        summary["window_seconds_observed"] = round(min(time.time(), end) - cutover, 1)
        if reason:
            return GateResult(False, [reason], summary)
        res = evaluate_http(summary, self.t)
        (ok if res.passed else fail)(
            f"HTTP gate: {summary['requests']} запросов, ошибок {summary['failed']}, p95 {summary['p95_seconds']} с"
        )
        return res

    def _metrics_gate(self, cand: str, pods: list[str], start: float, wait: bool = True) -> GateResult:
        if wait:
            time.sleep(self.scrape_wait)  # последние запросы окна должны попасть в scrape
        at = time.time()
        rng = max(10, int(at - start) + 1)
        sel = f'job="mts-api",slot="{cand}",route=~"/api/v1/.*"'
        try:
            snap = MetricsSnapshot(
                available=True,
                requests=self.prom.scalar(f"sum(increase(http_requests_total{{{sel}}}[{rng}s]))", at),
                errors=self.prom.scalar(
                    f'sum(increase(http_requests_total{{{sel},status=~"5.."}}[{rng}s])) or vector(0)', at
                ),
                p95_seconds=self.prom.scalar(
                    "histogram_quantile(0.95, sum by (le) "
                    f"(increase(http_request_duration_seconds_bucket{{{sel}}}[{rng}s])))",
                    at,
                ),
                build_info_pods=int(
                    self.prom.scalar(
                        f'count(app_build_info{{job="mts-api",slot="{cand}",release_id="{self.release_id}"}})', at
                    )
                    or 0
                ),
            )
            ups = {m.get("pod"): v for m, v in self.prom.query(f'up{{job="mts-api",slot="{cand}"}}', at)}
            ages = {
                m.get("pod"): v
                for m, v in self.prom.query(f'time() - timestamp(up{{job="mts-api",slot="{cand}"}})', at)
            }
            snap.targets = [{"pod": p, "up": ups[p], "age_seconds": round(ages.get(p, float("nan")), 1)} for p in ups]
        except PromUnavailable as exc:
            snap = MetricsSnapshot(available=False, error=str(exc))
        res = evaluate_metrics(snap, set(pods), self.t)
        res.details["range_seconds"] = rng
        (ok if res.passed else fail)(f"metrics gate: {'пройден' if res.passed else res.reasons}")
        return res

    # ------------------------------------------------------------ decisions
    def _promote(self, state: dict, cand: str, prev_info: dict | None) -> str:
        self.lock.check()
        prev_active = state.get("active") or {}
        # прежний слот пригоден для ручного возврата, только если в нём действительно
        # подтверждённый релиз (а не, например, неудачный первый релиз)
        prev_confirmed = bool(
            prev_info
            and prev_active.get("healthy", True)
            and prev_info.get("release_id") == prev_active.get("release_id")
        )
        state["active"] = {
            "slot": cand,
            "image": self.art.image,
            "digest": self.art.digest,
            "version": self.art.version,
            "git_sha": self.art.git_sha,
            "release_id": self.release_id,
            "promoted_at": iso(utcnow()),
            "healthy": True,
        }
        state["standby"] = {**prev_info, "healthy": prev_confirmed} if prev_info else None
        self._close(state, "promoted", None)
        ok(f"релиз {self.release_id} продвинут: слот {cand} обслуживает пользователей")
        return self._finish("promoted", None)

    def _reject(self, state: dict, cand: str, reason: str, detail: str | None) -> str:
        prev_standby = state.get("standby") or {}
        actual = deployed_slot_info(self.kube, cand)
        if actual and actual.get("release_id") == prev_standby.get("release_id"):
            state["standby"] = prev_standby  # Helm вернул слот к прежней ревизии
        else:
            state["standby"] = {**actual, "healthy": False} if actual else None
        self._close(state, "rejected", reason)
        fail(f"релиз {self.release_id} отклонён до переключения ({reason}); пользователи не затронуты")
        return self._finish("rejected", f"{reason}: {detail}")

    def _handle_failure(
        self,
        state: dict,
        load: LoadGenerator,
        cand: str,
        prev_slot: str | None,
        prev_info: dict | None,
        reasons: str,
        pods: list[str] | None = None,
        cutover: float | None = None,
    ) -> str:
        if not prev_slot or not prev_info:
            state["active"] = {
                "slot": cand,
                "digest": self.art.digest,
                "version": self.art.version,
                "release_id": self.release_id,
                "healthy": False,
            }
            self._close(state, "failed", reasons)
            fail("post-deploy проверка не пройдена, но предыдущего здорового слота нет — возврат невозможен")
            self.report.set("rollback", {"performed": False, "reason": "нет предыдущего здорового релиза"})
            return self._finish("failed", reasons)

        warn(f"деградация после переключения: {reasons}. Возвращаю трафик на {prev_slot}")
        state["phase"] = "rolling_back"
        self.store.save(state)
        rb_started = time.time()
        self._switch(prev_slot)
        self._mark("traffic_rolled_back", to=prev_slot)
        back = self._wait_cutover(load, prev_info.get("release_id", ""), since=rb_started)
        verification: dict = {"cutback_observed": back is not None}
        recovered = False
        if back is not None:
            self._mark("cutback_observed", seconds_after_rollback=round(back - rb_started, 2))
            time.sleep(10)
            rec = summarize_http(load.snapshot(since=back), prev_info.get("release_id"))
            verification.update(rec)
            recovered = rec["requests"] >= 20 and rec["failed"] == 0 and (rec.get("candidate_share") or 0) >= 0.99
        # Доказательства из Prometheus снимаются уже после возврата трафика (не задерживают его):
        # видны ли ошибки кандидата в метриках, независимо от собственных HTTP-проб контроллера.
        if pods and cutover:
            evidence = self._metrics_gate(cand, pods, cutover, wait=False)
            self.report.check(
                "metrics_evidence_after_rollback",
                "recorded",
                note="метрики кандидата за окно наблюдения; на решение не влияют",
                **evidence.details,
            )
        self.report.set(
            "rollback",
            {
                "performed": True,
                "target_slot": prev_slot,
                "target_release": prev_info.get("release_id"),
                "seconds_to_cutback": round(back - rb_started, 2) if back else None,
                "recovery_verified": recovered,
                "verification": verification,
            },
        )
        state["standby"] = {**(deployed_slot_info(self.kube, cand) or {"slot": cand}), "healthy": False}
        if recovered:
            self._close(state, "rolled_back", reasons)
            ok(f"восстановление подтверждено: ingress снова отдаёт {prev_info.get('release_id')} без ошибок")
            return self._finish("rolled_back", reasons)
        self._close(state, "rollback_failed", reasons)
        fail("трафик возвращён, но проверка восстановления не пройдена — требуется вмешательство (docs/runbooks.md)")
        return self._finish("rollback_failed", reasons)

    def _close(self, state: dict, decision: str, reason: str | None) -> None:
        state["history"].append(
            {
                "release_id": self.release_id,
                "decision": decision,
                "reason": (reason or "")[:300],
                "version": self.art.version,
                "digest": self.art.digest,
                "slot": (state.get("candidate") or {}).get("slot"),
                "at": iso(utcnow()),
            }
        )
        state.update(phase="idle", operation=None, candidate=None)
        self.store.save(state)

    def _finish(self, decision: str, reason: str | None) -> str:
        self._marks["total"] = round(time.time() - self._t0, 1)
        self.report.set("durations", {"seconds_from_start": self._marks})
        json_path, md_path = self.report.finish(decision, reason)
        log(f"отчёт: {md_path.relative_to(ROOT)} ({json_path.name})")
        return decision
