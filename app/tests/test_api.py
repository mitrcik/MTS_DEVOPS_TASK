from __future__ import annotations

import logging
from pathlib import Path

import pytest
from conftest import VALID_TOKEN, make_settings, write_hashes
from fastapi.testclient import TestClient

from mts_api.auth import TokenStore
from mts_api.main import create_app
from mts_api.settings import Settings

QUOTE = {"tariff_id": "basic", "minutes": 320, "sms": 55, "data_gb": "11.5", "roaming_days": 2}


def test_health_and_ready(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_not_ready_without_token_hashes(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, token_hashes_file=str(tmp_path / "missing"))
    client = TestClient(create_app(settings))
    response = client.get("/readyz")
    assert response.status_code == 503
    assert "api token hashes are not mounted" in response.json()["reasons"]
    # liveness не зависит от готовности: kubelet не должен перезапускать процесс
    assert client.get("/healthz").status_code == 200


def test_fault_not_ready_mode(tmp_path: Path, token_file: Path) -> None:
    settings = make_settings(tmp_path, fault_mode="not-ready")
    client = TestClient(create_app(settings, TokenStore(str(token_file))))
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200


def test_version_reports_build_and_release(client: TestClient) -> None:
    body = client.get("/version").json()
    assert body == {
        "version": "v-test",
        "git_sha": "0123456789ab",
        "build_time": "2026-10-15T00:00:00Z",
        "release_id": "r-test",
        "slot": "blue",
        "fault_mode": "none",
    }


def test_list_and_get_tariffs(client: TestClient) -> None:
    listing = client.get("/api/v1/tariffs").json()
    assert listing["count"] == len(listing["items"]) >= 3
    smart = client.get("/api/v1/tariffs/smart")
    assert smart.status_code == 200
    assert smart.json()["monthly_fee"] == "650.00"
    assert client.get("/api/v1/tariffs/nope").status_code == 404


def test_quote_requires_token(client: TestClient) -> None:
    assert client.post("/api/v1/quotes", json=QUOTE).status_code == 401
    wrong = client.post("/api/v1/quotes", json=QUOTE, headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 401
    basic = client.post("/api/v1/quotes", json=QUOTE, headers={"Authorization": "Basic abc"})
    assert basic.status_code == 401


def test_quote_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/quotes", json=QUOTE, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == "935.00"
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Release-Id"] == "r-test"
    assert response.headers["X-Slot"] == "blue"


@pytest.mark.parametrize(
    "patch",
    [
        {"minutes": -1},
        {"sms": 100_001},
        {"data_gb": "1.234"},
        {"roaming_days": 32},
        {"tariff_id": "BAD ID"},
        {"unexpected": 1},
    ],
)
def test_quote_validation(client: TestClient, auth_headers: dict[str, str], patch: dict) -> None:
    response = client.post("/api/v1/quotes", json={**QUOTE, **patch}, headers=auth_headers)
    assert response.status_code == 422


def test_quote_unknown_tariff(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/quotes", json={**QUOTE, "tariff_id": "missing"}, headers=auth_headers
    )
    assert response.status_code == 404


def test_errors_behind_ingress_fault_is_deterministic(
    tmp_path: Path, token_file: Path, auth_headers: dict[str, str]
) -> None:
    settings = make_settings(tmp_path, fault_mode="errors-behind-ingress")
    client = TestClient(create_app(settings, TokenStore(str(token_file))))
    # Прямой путь (preview через port-forward) работает и экземпляр Ready.
    assert client.get("/readyz").status_code == 200
    for _ in range(5):
        assert client.post("/api/v1/quotes", json=QUOTE, headers=auth_headers).status_code == 200
    # Через ingress (Traefik добавляет X-Forwarded-For) каждый запрос даёт 500.
    behind_proxy = {**auth_headers, "X-Forwarded-For": "10.0.0.1"}
    for _ in range(5):
        assert client.post("/api/v1/quotes", json=QUOTE, headers=behind_proxy).status_code == 500
    # Каталог не затронут — дефект ограничен методом расчёта.
    assert client.get("/api/v1/tariffs", headers={"X-Forwarded-For": "10.0.0.1"}).status_code == 200


def test_token_rotation_is_picked_up_without_restart(
    tmp_path: Path, token_file: Path, auth_headers: dict[str, str]
) -> None:
    client = TestClient(create_app(make_settings(tmp_path), TokenStore(str(token_file))))
    new_token = "mts_demo_test_token_rotated_fedcba9876543210"
    new_headers = {"Authorization": f"Bearer {new_token}"}

    # Фаза перекрытия: действуют оба токена.
    write_hashes(token_file, new_token, VALID_TOKEN)
    assert client.post("/api/v1/quotes", json=QUOTE, headers=auth_headers).status_code == 200
    assert client.post("/api/v1/quotes", json=QUOTE, headers=new_headers).status_code == 200

    # Отзыв старого токена.
    write_hashes(token_file, new_token)
    assert client.post("/api/v1/quotes", json=QUOTE, headers=auth_headers).status_code == 401
    assert client.post("/api/v1/quotes", json=QUOTE, headers=new_headers).status_code == 200


def test_metrics_use_route_templates(client: TestClient) -> None:
    for tariff_id in ("basic", "smart", "nope-1", "nope-2"):
        client.get(f"/api/v1/tariffs/{tariff_id}")
    client.get("/no/such/path/123")
    text = client.get("/metrics").text
    assert 'route="/api/v1/tariffs/{tariff_id}"' in text
    assert "nope-1" not in text
    assert 'route="<unmatched>"' in text
    assert "/no/such/path/123" not in text
    assert "app_build_info{" in text
    assert "http_request_duration_seconds_bucket{" in text


def test_logs_never_contain_token(
    client: TestClient, auth_headers: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        client.post("/api/v1/quotes", json=QUOTE, headers=auth_headers)
        client.post("/api/v1/quotes", json=QUOTE, headers={"Authorization": "Bearer leaked-guess"})
    rendered = "\n".join(f"{r.getMessage()} {getattr(r, 'fields', '')}" for r in caplog.records)
    assert VALID_TOKEN not in rendered
    assert "leaked-guess" not in rendered
    assert '"route": "/api/v1/quotes"' in rendered or "'route': '/api/v1/quotes'" in rendered


def test_invalid_fault_mode_fails_fast() -> None:
    with pytest.raises(ValueError):
        Settings.from_env({"APP_FAULT_MODE": "random-chaos"})
