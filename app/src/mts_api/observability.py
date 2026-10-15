"""Метрики Prometheus и структурированные JSON-логи.

Метки ограничены: маршрут берётся из шаблона FastAPI (``/api/v1/tariffs/{tariff_id}``),
а не из фактического URL, метод — из фиксированного набора. Это исключает
неограниченную кардинальность временных рядов.
"""

from __future__ import annotations

import json
import logging
import sys
import time

from prometheus_client import Counter, Gauge, Histogram

KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
UNMATCHED_ROUTE = "<unmatched>"

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests processed, by route template and status code.",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, by route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
QUOTE_OUTCOMES = Counter(
    "quote_requests_total",
    "Quote calculation outcomes.",
    ["outcome"],
)
APP_READY = Gauge("app_ready", "1 if this instance reports ready on /readyz, else 0.")
BUILD_INFO = Gauge(
    "app_build_info",
    "Build and release metadata of this instance (value is always 1).",
    ["version", "git_sha", "slot", "release_id", "fault_mode"],
)


def method_label(method: str) -> str:
    return method if method in KNOWN_METHODS else "OTHER"


class JsonFormatter(logging.Formatter):
    """Одна JSON-строка на событие. Заголовки и тела запросов не логируются."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
