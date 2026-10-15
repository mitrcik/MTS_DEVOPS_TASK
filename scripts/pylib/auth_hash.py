"""Хеш токена — тот же алгоритм, что в приложении (app/src/mts_api/auth.py)."""

from __future__ import annotations

import hashlib


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
