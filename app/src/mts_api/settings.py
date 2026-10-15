"""Конфигурация процесса из переменных окружения.

Сборочные значения (версия, SHA, время сборки, режим неисправности) зашиваются
в образ через ``ARG``/``ENV`` в Dockerfile. Значения релиза (слот, release id)
передаёт Helm-чарт слота.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

# Учебные режимы неисправности. По умолчанию "none".
#  - not-ready: экземпляр никогда не становится Ready (кандидат отклоняется до переключения);
#  - errors-behind-ingress: экземпляр Ready и проходит прямые проверки, но метод расчёта
#    возвращает 500 для запросов, пришедших через ingress (есть X-Forwarded-For).
#    Дефект детерминированно проявляется только после переключения пользовательского трафика.
FAULT_MODES = frozenset({"none", "not-ready", "errors-behind-ingress"})

DEFAULT_TOKEN_HASHES_FILE = "/var/run/secrets/mts-api/token-hashes"  # noqa: S105 - путь, не пароль


@dataclass(frozen=True)
class Settings:
    version: str
    git_sha: str
    build_time: str
    release_id: str
    slot: str
    fault_mode: str
    token_hashes_file: str
    log_level: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        fault_mode = env.get("APP_FAULT_MODE", "none").strip() or "none"
        if fault_mode not in FAULT_MODES:
            raise ValueError(f"APP_FAULT_MODE={fault_mode!r} is not one of {sorted(FAULT_MODES)}")
        return cls(
            version=env.get("APP_VERSION", "dev"),
            git_sha=env.get("GIT_SHA", "unknown"),
            build_time=env.get("BUILD_TIME", "unknown"),
            release_id=env.get("RELEASE_ID", "local"),
            slot=env.get("SLOT", "none"),
            fault_mode=fault_mode,
            token_hashes_file=env.get("TOKEN_HASHES_FILE", DEFAULT_TOKEN_HASHES_FILE),
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
        )
