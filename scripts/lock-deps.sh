#!/usr/bin/env bash
# Пересборка lock-файлов Python с хешами. Отсечка по дате публикации (EXCLUDE_NEWER)
# воспроизводит правило выбора версий из docs/decisions.md. Требуется uv (pip install uv).
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
require_cmd uv
EXCLUDE_NEWER="${EXCLUDE_NEWER:-2026-10-01T00:00:00Z}"
common=(--generate-hashes --no-header --exclude-newer "${EXCLUDE_NEWER}" -q)

cd "${ROOT_DIR}/app"
uv pip compile requirements.in -o requirements.lock --python-version 3.13 \
  --python-platform x86_64-manylinux_2_28 "${common[@]}"
uv pip compile requirements-dev.in -o requirements-dev.lock --python-version 3.13 \
  --python-platform x86_64-manylinux_2_28 "${common[@]}"
cd "${ROOT_DIR}/infra/tooling"
uv pip compile requirements.in -o requirements.lock --python-version 3.12 "${common[@]}"
ok "lock-файлы обновлены (отсечка ${EXCLUDE_NEWER})"
