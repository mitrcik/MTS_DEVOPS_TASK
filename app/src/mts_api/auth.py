"""Проверка учебного API-токена.

В Kubernetes Secret хранится не сам токен, а SHA-256 его значения (по одной
строке на действующий токен). Файл монтируется в pod как volume; kubelet
обновляет его при изменении Secret, поэтому оба blue-green слота одинаково
видят результат ротации без перезапуска. Хеш без «соли» допустим, потому что
токен — 256-битная случайная строка, а не пароль человека.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenStore:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._signature: tuple[int, int, int] | None = None
        self._hashes: frozenset[str] = frozenset()

    def _reload_if_changed(self) -> None:
        try:
            st = os.stat(self._path)  # следует по symlink ..data, который меняет kubelet
        except FileNotFoundError:
            with self._lock:
                self._signature, self._hashes = None, frozenset()
            return
        signature = (st.st_ino, st.st_mtime_ns, st.st_size)
        if signature == self._signature:
            return
        with open(self._path, encoding="utf-8") as fh:
            candidates = {line.strip().lower() for line in fh}
        hashes = frozenset(h for h in candidates if _HEX64.match(h))
        with self._lock:
            self._signature, self._hashes = signature, hashes

    def configured(self) -> bool:
        self._reload_if_changed()
        return bool(self._hashes)

    def active_count(self) -> int:
        self._reload_if_changed()
        return len(self._hashes)

    def verify(self, token: str) -> bool:
        if not token:
            return False
        self._reload_if_changed()
        presented = token_hash(token)
        matched = False
        for known in self._hashes:  # сравниваем со всеми, без раннего выхода
            matched |= hmac.compare_digest(known, presented)
        return matched


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()
