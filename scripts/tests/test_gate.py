"""Unit-тесты правил gate и определения момента переключения (без кластера)."""

from __future__ import annotations

import math
import time
import unittest

from pylib.gate import (
    MetricsSnapshot,
    Thresholds,
    evaluate_http,
    evaluate_metrics,
    fail_fast,
    percentile,
    summarize_http,
)
from pylib.httpprobe import Sample
from pylib.release import ReleaseController

T = Thresholds(min_http_requests=50, min_metric_requests=30, max_error_ratio=0.02, max_p95_seconds=0.5)
PODS = {"mts-api-green-a", "mts-api-green-b"}


def samples(n: int, *, failed: int = 0, latency: float = 0.01, release: str = "r2", t0: float = 0.0):
    out = []
    for i in range(n):
        status = 500 if i < failed else 200
        out.append(Sample(t0 + i * 0.1, "create_quote", status, 200, latency, release, "green"))
    return out


def good_snapshot(**overrides) -> MetricsSnapshot:
    snap = MetricsSnapshot(
        available=True,
        requests=200.0,
        errors=0.0,
        p95_seconds=0.02,
        build_info_pods=2,
        targets=[{"pod": p, "up": 1.0, "age_seconds": 3.0} for p in sorted(PODS)],
    )
    for key, value in overrides.items():
        setattr(snap, key, value)
    return snap


class HttpGateTest(unittest.TestCase):
    def test_healthy_window_passes(self) -> None:
        res = evaluate_http(summarize_http(samples(100), "r2"), T)
        self.assertTrue(res.passed, res.reasons)

    def test_zero_traffic_is_not_success(self) -> None:
        res = evaluate_http(summarize_http([], "r2"), T)
        self.assertFalse(res.passed)
        self.assertTrue(any("мало" in r for r in res.reasons))

    def test_error_ratio_above_threshold_fails(self) -> None:
        res = evaluate_http(summarize_http(samples(100, failed=5), "r2"), T)
        self.assertFalse(res.passed)

    def test_unexpected_4xx_counts_as_failure(self) -> None:
        s = samples(100)
        s[0] = Sample(0, "create_quote", 401, 200, 0.01, "r2", "green")  # токен не принят
        s[1] = Sample(0, "create_quote", 401, 200, 0.01, "r2", "green")
        s[2] = Sample(0, "create_quote", 401, 200, 0.01, "r2", "green")
        self.assertFalse(evaluate_http(summarize_http(s, "r2"), T).passed)

    def test_old_release_still_serving_fails(self) -> None:
        mixed = samples(60, release="r2") + samples(40, release="r1")
        res = evaluate_http(summarize_http(mixed, "r2"), T)
        self.assertFalse(res.passed)
        self.assertTrue(any("кандидат обслужил" in r for r in res.reasons))

    def test_slow_responses_fail(self) -> None:
        self.assertFalse(evaluate_http(summarize_http(samples(100, latency=0.9), "r2"), T).passed)

    def test_fail_fast_needs_minimum_samples(self) -> None:
        self.assertIsNone(fail_fast(samples(10, failed=10), T))
        self.assertIsNotNone(fail_fast(samples(30, failed=10), T))
        self.assertIsNone(fail_fast(samples(30), T))

    def test_percentile(self) -> None:
        self.assertIsNone(percentile([], 0.95))
        self.assertEqual(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.95), 10)


class MetricsGateTest(unittest.TestCase):
    def test_good_metrics_pass(self) -> None:
        res = evaluate_metrics(good_snapshot(), PODS, T)
        self.assertTrue(res.passed, res.reasons)

    def test_prometheus_unavailable_fails_closed(self) -> None:
        res = evaluate_metrics(MetricsSnapshot(available=False, error="connection refused"), PODS, T)
        self.assertFalse(res.passed)

    def test_empty_vector_or_nan_is_not_success(self) -> None:
        self.assertFalse(evaluate_metrics(good_snapshot(requests=None), PODS, T).passed)
        self.assertFalse(evaluate_metrics(good_snapshot(requests=math.nan), PODS, T).passed)
        self.assertFalse(evaluate_metrics(good_snapshot(p95_seconds=math.nan), PODS, T).passed)

    def test_insufficient_metric_traffic_fails(self) -> None:
        self.assertFalse(evaluate_metrics(good_snapshot(requests=5.0), PODS, T).passed)

    def test_stale_or_missing_series_fail(self) -> None:
        stale = [{"pod": p, "up": 1.0, "age_seconds": 120.0} for p in sorted(PODS)]
        self.assertFalse(evaluate_metrics(good_snapshot(targets=stale), PODS, T).passed)
        one = [{"pod": "mts-api-green-a", "up": 1.0, "age_seconds": 2.0}]
        self.assertFalse(evaluate_metrics(good_snapshot(targets=one), PODS, T).passed)
        down = [{"pod": p, "up": 0.0, "age_seconds": 2.0} for p in sorted(PODS)]
        self.assertFalse(evaluate_metrics(good_snapshot(targets=down), PODS, T).passed)

    def test_error_ratio_from_metrics(self) -> None:
        self.assertFalse(evaluate_metrics(good_snapshot(errors=20.0), PODS, T).passed)
        # нет ни одной 5xx-серии (пустой вектор) при достаточном трафике — это 0 ошибок
        self.assertTrue(evaluate_metrics(good_snapshot(errors=None), PODS, T).passed)

    def test_build_info_of_other_release_fails(self) -> None:
        self.assertFalse(evaluate_metrics(good_snapshot(build_info_pods=0), PODS, T).passed)


class FakeLoad:
    def __init__(self, items: list[Sample]) -> None:
        self.items = items

    def snapshot(self, since: float = 0.0, until: float | None = None) -> list[Sample]:
        return [s for s in self.items if s.wall >= since]


class CutoverTest(unittest.TestCase):
    def test_cutover_is_start_of_stable_streak(self) -> None:
        now = time.time()
        seq = (
            [Sample(now + i, "x", 200, 200, 0.01, "old", "blue") for i in range(3)]
            + [Sample(now + 3, "x", 200, 200, 0.01, "new", "green")]
            + [Sample(now + 4, "x", 200, 200, 0.01, "old", "blue")]
            + [Sample(now + 5 + i, "x", 200, 200, 0.01, "new", "green") for i in range(6)]
        )
        at = ReleaseController._wait_cutover(FakeLoad(seq), "new", since=now, timeout=1)
        self.assertEqual(at, now + 5)

    def test_no_cutover_returns_none(self) -> None:
        now = time.time()
        seq = [Sample(now + i, "x", 200, 200, 0.01, "old", "blue") for i in range(10)]
        self.assertIsNone(ReleaseController._wait_cutover(FakeLoad(seq), "new", since=now, timeout=0.6))


if __name__ == "__main__":
    unittest.main()
