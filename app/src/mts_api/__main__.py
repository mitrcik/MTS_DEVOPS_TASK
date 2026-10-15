"""Точка входа контейнера: ``python -m mts_api``."""

from __future__ import annotations

import uvicorn

from .main import create_app
from .observability import configure_logging
from .settings import Settings


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104 - внутри pod; наружу публикует только Service/Ingress
        port=8000,
        access_log=False,
        log_config=None,
        server_header=False,
        proxy_headers=False,
        timeout_graceful_shutdown=10,
    )


if __name__ == "__main__":
    main()
