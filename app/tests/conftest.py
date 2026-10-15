from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mts_api.auth import TokenStore, token_hash
from mts_api.main import create_app
from mts_api.settings import Settings

VALID_TOKEN = "mts_demo_test_token_valid_0123456789abcdef"


def make_settings(tmp_path: Path, **overrides: str) -> Settings:
    values = {
        "version": "v-test",
        "git_sha": "0123456789ab",
        "build_time": "2026-10-15T00:00:00Z",
        "release_id": "r-test",
        "slot": "blue",
        "fault_mode": "none",
        "token_hashes_file": str(tmp_path / "token-hashes"),
        "log_level": "DEBUG",
    }
    values.update(overrides)
    return Settings(**values)


def write_hashes(path: Path, *tokens: str) -> None:
    # Новый файл с новым inode — как при атомарной замене symlink ..data kubelet'ом.
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(token_hash(t) + "\n" for t in tokens), encoding="utf-8")
    tmp.replace(path)


@pytest.fixture
def token_file(tmp_path: Path) -> Path:
    path = tmp_path / "token-hashes"
    write_hashes(path, VALID_TOKEN)
    return path


@pytest.fixture
def client(tmp_path: Path, token_file: Path) -> TestClient:
    settings = make_settings(tmp_path)
    return TestClient(create_app(settings, TokenStore(str(token_file))))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}
