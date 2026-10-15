"""HTTP-пробы и генератор пользовательского трафика (stdlib)."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

QUOTE_PAYLOAD = {"tariff_id": "basic", "minutes": 320, "sms": 55, "data_gb": "11.5", "roaming_days": 2}
QUOTE_EXPECTED_TOTAL = "935.00"  # контрольный ответ (см. app/tests/test_tariffs.py)


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str]
    latency: float
    error: str | None = None

    def json(self) -> dict:
        try:
            return json.loads(self.body or b"{}")
        except ValueError:
            return {}


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
    timeout: float = 5.0,
) -> Response:
    data = None
    hdrs = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in hdrs.items():
        req.add_header(key, value)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback без прокси
    started = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read()
            return Response(resp.status, body, dict(resp.headers), time.perf_counter() - started)
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return Response(exc.code, body, dict(exc.headers or {}), time.perf_counter() - started)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        return Response(0, b"", {}, time.perf_counter() - started, error=type(exc).__name__)


@dataclass
class Sample:
    wall: float
    op: str
    status: int
    expected: int
    latency: float
    release_id: str
    slot: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == self.expected


@dataclass
class Operation:
    name: str
    method: str
    path: str
    expected: int
    payload: dict | None = None
    auth: bool = False


USER_MIX = (
    Operation("list_tariffs", "GET", "/api/v1/tariffs", 200),
    Operation("get_tariff", "GET", "/api/v1/tariffs/smart", 200),
    Operation("create_quote", "POST", "/api/v1/quotes", 200, QUOTE_PAYLOAD, auth=True),
)


@dataclass
class LoadGenerator:
    """Постоянный поток бизнес-запросов через пользовательский ingress.

    Каждый ответ несёт заголовки X-Release-Id/X-Slot, поэтому видно, какой релиз
    обслужил каждый запрос (в том числе в момент переключения и отката).
    """

    base_url: str
    token: str
    rps: float
    workers: int = 4
    host_header: str | None = None
    samples: list[Sample] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._counter = 0

    def _next_op(self) -> Operation:
        with self._lock:
            self._counter += 1
            return USER_MIX[self._counter % len(USER_MIX)]

    def _worker(self, index: int) -> None:
        interval = self.workers / self.rps
        next_at = time.monotonic() + index * (interval / self.workers)
        while not self._stop.is_set():
            delay = next_at - time.monotonic()
            if delay > 0 and self._stop.wait(delay):
                break
            next_at += interval
            op = self._next_op()
            headers = {}
            if self.host_header:
                headers["Host"] = self.host_header
            if op.auth:
                headers["Authorization"] = f"Bearer {self.token}"
            resp = request(op.method, self.base_url + op.path, headers=headers, payload=op.payload)
            sample = Sample(
                wall=time.time(),
                op=op.name,
                status=resp.status,
                expected=op.expected,
                latency=resp.latency,
                release_id=resp.headers.get("X-Release-Id", ""),
                slot=resp.headers.get("X-Slot", ""),
                error=resp.error,
            )
            with self._lock:
                self.samples.append(sample)

    def start(self) -> LoadGenerator:
        for i in range(self.workers):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            t.start()
            self._threads.append(t)
        return self

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=10)

    def snapshot(self, since: float = 0.0, until: float | None = None) -> list[Sample]:
        with self._lock:
            return [s for s in self.samples if s.wall >= since and (until is None or s.wall <= until)]
