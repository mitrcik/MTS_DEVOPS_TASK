"""Правила post-deploy gate. Чистые функции — покрыты unit-тестами (scripts/tests).

Главный принцип: отсутствие данных — это не успех. Нет ответа Prometheus, пустой
вектор, NaN, нулевой или недостаточный трафик, устаревшие серии — всё это
провал проверки с явной причиной.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .httpprobe import Sample


@dataclass(frozen=True)
class Thresholds:
    min_http_requests: int = 120
    min_metric_requests: int = 60
    max_error_ratio: float = 0.02
    max_p95_seconds: float = 0.5
    max_staleness_seconds: float = 20.0
    min_candidate_share: float = 0.99
    fail_fast_min_samples: int = 20


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"passed": self.passed, "reasons": self.reasons, "details": self.details}


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[idx]


def summarize_http(samples: list[Sample], candidate_release: str | None = None) -> dict:
    total = len(samples)
    failed = [s for s in samples if not s.ok]
    by_release: dict[str, int] = {}
    for s in samples:
        by_release[s.release_id or "<none>"] = by_release.get(s.release_id or "<none>", 0) + 1
    p95 = percentile([s.latency for s in samples], 0.95)
    summary = {
        "requests": total,
        "failed": len(failed),
        "error_ratio": (len(failed) / total) if total else None,
        "p95_seconds": round(p95, 4) if p95 is not None else None,
        "served_by_release": by_release,
        "failures_by_status": {},
    }
    for s in failed:
        key = str(s.status) if s.status else (s.error or "error")
        summary["failures_by_status"][key] = summary["failures_by_status"].get(key, 0) + 1
    if candidate_release is not None:
        summary["candidate_share"] = (by_release.get(candidate_release, 0) / total) if total else None
    return summary


def fail_fast(samples: list[Sample], t: Thresholds) -> str | None:
    """Ранняя остановка окна при явной деградации (не ждём конца окна)."""
    if len(samples) < t.fail_fast_min_samples:
        return None
    failed = sum(1 for s in samples if not s.ok)
    ratio = failed / len(samples)
    if ratio > t.max_error_ratio:
        return f"доля неуспешных бизнес-запросов {ratio:.1%} > {t.max_error_ratio:.1%} на {len(samples)} запросах"
    return None


def evaluate_http(summary: dict, t: Thresholds) -> GateResult:
    reasons = []
    if summary["requests"] < t.min_http_requests:
        reasons.append(f"мало пользовательских запросов: {summary['requests']} < {t.min_http_requests}")
    ratio = summary["error_ratio"]
    if ratio is None or ratio > t.max_error_ratio:
        reasons.append(f"доля ошибок {ratio} > {t.max_error_ratio}")
    p95 = summary["p95_seconds"]
    if p95 is None or p95 > t.max_p95_seconds:
        reasons.append(f"p95 {p95} с > {t.max_p95_seconds} с")
    share = summary.get("candidate_share")
    if share is not None and share < t.min_candidate_share:
        reasons.append(f"кандидат обслужил только {share:.1%} запросов после переключения")
    return GateResult(not reasons, reasons, summary)


@dataclass
class MetricsSnapshot:
    available: bool
    error: str | None = None
    requests: float | None = None
    errors: float | None = None
    p95_seconds: float | None = None
    build_info_pods: int | None = None
    targets: list[dict] = field(default_factory=list)  # {"pod", "up", "age_seconds"}

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _bad(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def evaluate_metrics(snap: MetricsSnapshot, expected_pods: set[str], t: Thresholds) -> GateResult:
    if not snap.available:
        return GateResult(False, [f"метрики недоступны: {snap.error}"], snap.as_dict())
    reasons = []
    seen = {tgt["pod"]: tgt for tgt in snap.targets}
    for pod in sorted(expected_pods):
        tgt = seen.get(pod)
        if tgt is None:
            reasons.append(f"нет серии up для pod {pod}")
        elif tgt["up"] != 1:
            reasons.append(f"pod {pod}: up={tgt['up']}")
        elif _bad(tgt["age_seconds"]) or tgt["age_seconds"] > t.max_staleness_seconds:
            reasons.append(f"pod {pod}: последний scrape {tgt['age_seconds']} с назад (устарело)")
    if _bad(snap.requests):
        reasons.append("нет данных о запросах кандидата (пустой вектор/NaN)")
    elif snap.requests < t.min_metric_requests:
        reasons.append(f"в метриках мало запросов: {snap.requests:.0f} < {t.min_metric_requests}")
    else:
        errors = 0.0 if _bad(snap.errors) else snap.errors
        ratio = errors / snap.requests
        if ratio > t.max_error_ratio:
            reasons.append(f"доля 5xx по метрикам {ratio:.2%} > {t.max_error_ratio:.2%}")
    if _bad(snap.p95_seconds):
        reasons.append("нет данных histogram для p95")
    elif snap.p95_seconds > t.max_p95_seconds:
        reasons.append(f"p95 по метрикам {snap.p95_seconds:.3f} с > {t.max_p95_seconds} с")
    if snap.build_info_pods is not None and expected_pods and snap.build_info_pods < len(expected_pods):
        reasons.append(
            f"app_build_info с release_id кандидата видна у {snap.build_info_pods} из {len(expected_pods)} pod"
        )
    return GateResult(not reasons, reasons, snap.as_dict())
