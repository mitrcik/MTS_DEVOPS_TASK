#!/usr/bin/env bash
# Создаёт .local/venv с закреплёнными (по хешам) Ansible и линтерами. Идемпотентен:
# повторная установка выполняется только при изменении lock-файла.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env

LOCK="${ROOT_DIR}/infra/tooling/requirements.lock"
VENV="${LOCAL_DIR}/venv"
STAMP="${VENV}/.lock.sha256"

want="$(sha256sum "${LOCK}" | cut -d' ' -f1)"
if [[ -x "${VENV}/bin/python" && -f "${STAMP}" && "$(cat "${STAMP}")" == "${want}" ]]; then
  ok "venv актуален: ${VENV}"
  exit 0
fi

mkdir -p "${LOCAL_DIR}"
if [[ ! -x "${VENV}/bin/python" ]]; then
  PY_BIN="$(find_python)" \
    || die "нужен Python >= 3.12 с модулем venv: make prereqs (Ubuntu 22.04 — python3.12 из PPA deadsnakes) или PYTHON=/путь в .env"
  log "создаю ${VENV} (${PY_BIN})"
  "${PY_BIN}" -m venv "${VENV}" \
    || die "${PY_BIN} -m venv не работает: make prereqs (или sudo apt-get install -y python3-venv)"
fi

pip_args=(install --quiet --disable-pip-version-check --require-hashes --no-deps --only-binary=:all: -r "${LOCK}")
if [[ -n "${EXTRA_CA_BUNDLE:-}" ]]; then
  pip_args+=(--cert "${EXTRA_CA_BUNDLE}")
fi
log "устанавливаю закреплённые пакеты (ansible-core, yamllint, ruff)"
"${VENV}/bin/python" -m pip "${pip_args[@]}"
printf '%s' "${want}" > "${STAMP}"
ok "venv готов: $("${VENV}/bin/ansible-playbook" --version | head -1)"
