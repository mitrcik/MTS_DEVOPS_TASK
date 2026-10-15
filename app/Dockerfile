# Образ демо-API. Стадии:
#   deps    — виртуальное окружение с зависимостями из lock-файла (pip --require-hashes);
#   test    — lint-независимые unit-тесты в той же версии Python, что и runtime;
#   runtime — минимальный образ: без pip, непривилегированный UID, read-only совместимый.
#
# Базовый образ задан минорной версией (3.13, Debian trixie) и собирается с --pull,
# чтобы получать патчи безопасности; фактический digest базы фиксируется
# в provenance сборки (scripts/ci.sh). Решение и компромисс: docs/decisions.md.
ARG PYTHON_IMAGE=docker.io/library/python:3.13-slim-trixie

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

FROM base AS deps
COPY requirements.lock /tmp/requirements.lock
# extra_ca — необязательный BuildKit secret с CA-бандлом корпоративного TLS-прокси
# (EXTRA_CA_BUNDLE в .env). Монтируется только на время RUN и не попадает в слои.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi \
 && python -m venv /opt/venv \
 && /opt/venv/bin/pip install --require-hashes --no-deps --only-binary=:all: -r /tmp/requirements.lock

FROM deps AS test
COPY requirements-dev.lock /tmp/requirements-dev.lock
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi \
 && /opt/venv/bin/pip install --require-hashes --no-deps --only-binary=:all: -r /tmp/requirements-dev.lock
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
COPY tests ./tests
ENV PATH=/opt/venv/bin:$PATH
CMD ["pytest"]

FROM base AS runtime
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ARG APP_FAULT_MODE=none
# pip/ensurepip не нужны во время работы: убираем их из базового интерпретатора и venv.
COPY --from=deps /opt/venv /opt/venv
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip \
           /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.13/ensurepip \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13 \
           /opt/venv/bin/pip /opt/venv/bin/pip3 /opt/venv/bin/pip3.13 \
 && find /opt/venv/lib -maxdepth 3 -name 'pip*' -prune -exec rm -rf {} +
COPY src/mts_api /app/mts_api
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME} \
    APP_FAULT_MODE=${APP_FAULT_MODE}
LABEL org.opencontainers.image.title="mts-api" \
      org.opencontainers.image.description="MTS DevOps case: demo tariff REST API" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_TIME}" \
      io.mts-devops.fault-mode="${APP_FAULT_MODE}"
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "mts_api"]
