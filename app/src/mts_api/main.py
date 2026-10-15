"""HTTP-интерфейс сервиса."""

from __future__ import annotations

import logging
import re
import time
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict, Field

from .auth import TokenStore, bearer_token
from .observability import (
    APP_READY,
    BUILD_INFO,
    HTTP_LATENCY,
    HTTP_REQUESTS,
    QUOTE_OUTCOMES,
    UNMATCHED_ROUTE,
    method_label,
)
from .settings import Settings
from .tariffs import CATALOG, UnknownTariffError, calculate_quote, get_tariff

log = logging.getLogger("mts_api")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Служебные маршруты логируются на уровне DEBUG, чтобы пробы kubelet не засоряли логи.
_QUIET_ROUTES = frozenset({"/healthz", "/readyz", "/metrics"})


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tariff_id: str = Field(pattern=r"^[a-z0-9-]{1,32}$")
    minutes: int = Field(ge=0, le=100_000)
    sms: int = Field(ge=0, le=100_000)
    data_gb: Decimal = Field(ge=0, le=10_000, max_digits=7, decimal_places=2)
    roaming_days: int = Field(default=0, ge=0, le=31)


def create_app(settings: Settings, token_store: TokenStore | None = None) -> FastAPI:
    tokens = token_store or TokenStore(settings.token_hashes_file)
    app = FastAPI(
        title="MTS DevOps demo: tariff API",
        version=settings.version,
        description="Синтетический каталог тарифов и расчёт стоимости. Данные условные.",
    )
    app.state.settings = settings
    app.state.tokens = tokens

    BUILD_INFO.labels(
        version=settings.version,
        git_sha=settings.git_sha,
        slot=settings.slot,
        release_id=settings.release_id,
        fault_mode=settings.fault_mode,
    ).set(1)
    APP_READY.set(0)

    @app.middleware("http")
    async def observe(request: Request, call_next):
        started = time.perf_counter()
        incoming_id = request.headers.get("x-request-id", "")
        request_id = incoming_id if _REQUEST_ID.match(incoming_id) else uuid.uuid4().hex
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            # Какой релиз/слот обслужил запрос: нужно для измерения переключения трафика.
            response.headers["X-Release-Id"] = settings.release_id
            response.headers["X-Slot"] = settings.slot
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = getattr(request.scope.get("route"), "path", UNMATCHED_ROUTE)
            method = method_label(request.method)
            HTTP_REQUESTS.labels(method=method, route=route, status=str(status)).inc()
            HTTP_LATENCY.labels(method=method, route=route).observe(elapsed)
            log.log(
                logging.DEBUG if route in _QUIET_ROUTES else logging.INFO,
                "request",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "method": method,
                        "route": route,
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 2),
                        "slot": settings.slot,
                        "version": settings.version,
                    }
                },
            )

    @app.get("/")
    def index() -> dict[str, str]:
        return {
            "service": "mts-tariff-api",
            "version": settings.version,
            "docs": "/docs",
            "note": "Демонстрационные синтетические данные, не тарифы МТС.",
        }

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        reasons = []
        if settings.fault_mode == "not-ready":
            reasons.append("fault_mode=not-ready")
        if not tokens.configured():
            reasons.append("api token hashes are not mounted")
        APP_READY.set(0 if reasons else 1)
        if reasons:
            return JSONResponse({"status": "not-ready", "reasons": reasons}, status_code=503)
        return JSONResponse({"status": "ready"})

    @app.get("/version")
    def version() -> dict[str, str]:
        return {
            "version": settings.version,
            "git_sha": settings.git_sha,
            "build_time": settings.build_time,
            "release_id": settings.release_id,
            "slot": settings.slot,
            "fault_mode": settings.fault_mode,
        }

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/api/v1/tariffs")
    def list_tariffs() -> dict[str, object]:
        return {"items": [t.as_dict() for t in CATALOG.values()], "count": len(CATALOG)}

    @app.get("/api/v1/tariffs/{tariff_id}")
    def tariff_details(tariff_id: str) -> JSONResponse:
        try:
            return JSONResponse(get_tariff(tariff_id).as_dict())
        except UnknownTariffError:
            return JSONResponse({"detail": "tariff not found"}, status_code=404)

    @app.post("/api/v1/quotes")
    def create_quote(
        body: QuoteRequest,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        if not tokens.verify(bearer_token(authorization)):
            QUOTE_OUTCOMES.labels(outcome="unauthorized").inc()
            return JSONResponse(
                {"detail": "missing or invalid API token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if settings.fault_mode == "errors-behind-ingress" and "x-forwarded-for" in request.headers:
            # Учебный дефект: проявляется только на пользовательском пути через ingress.
            QUOTE_OUTCOMES.labels(outcome="error").inc()
            log.error(
                "simulated defect: quote failed",
                extra={"fields": {"fault": "errors-behind-ingress"}},
            )
            return JSONResponse({"detail": "internal error"}, status_code=500)
        try:
            tariff = get_tariff(body.tariff_id)
        except UnknownTariffError:
            QUOTE_OUTCOMES.labels(outcome="unknown_tariff").inc()
            return JSONResponse({"detail": "tariff not found"}, status_code=404)
        quote = calculate_quote(
            tariff,
            minutes=body.minutes,
            sms=body.sms,
            data_gb=body.data_gb,
            roaming_days=body.roaming_days,
        )
        QUOTE_OUTCOMES.labels(outcome="ok").inc()
        return JSONResponse(quote)

    log.info(
        "application configured",
        extra={
            "fields": {
                "version": settings.version,
                "git_sha": settings.git_sha,
                "slot": settings.slot,
                "release_id": settings.release_id,
                "fault_mode": settings.fault_mode,
            }
        },
    )
    if settings.fault_mode != "none":
        log.warning(
            "DEMO FAULT MODE ENABLED", extra={"fields": {"fault_mode": settings.fault_mode}}
        )
    return app
