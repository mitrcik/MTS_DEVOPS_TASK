# shellcheck shell=bash
# Общие функции bash-скриптов проекта. Подключение: source "$(dirname "$0")/lib.sh"
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${ROOT_DIR}/.local"
export ROOT_DIR LOCAL_DIR

# Сначала закреплённые версии, затем локальные настройки (.env или шаблон по умолчанию).
load_env() {
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/versions.env"
  if [[ -f "${ROOT_DIR}/.env" ]]; then
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
  else
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env.example"
  fi
  set +a
  CLUSTER_NAME="${CLUSTER_NAME:-mts-devops}"
  BIND_ADDRESS="${BIND_ADDRESS:-127.0.0.1}"
  INGRESS_PORT="${INGRESS_PORT:-8080}"
  API_PORT="${API_PORT:-6550}"
  REGISTRY_PORT="${REGISTRY_PORT:-5001}"
  REGISTRY_NAME="${CLUSTER_NAME}-registry"
  AGE_KEY_FILE="${AGE_KEY_FILE:-${HOME}/.config/mts-devops/${CLUSTER_NAME}/age.key}"
  ADMIN_KUBECONFIG="${LOCAL_DIR}/kube/admin.kubeconfig"
  DEPLOY_KUBECONFIG="${LOCAL_DIR}/kube/deploy.kubeconfig"
  export CLUSTER_NAME BIND_ADDRESS INGRESS_PORT API_PORT REGISTRY_PORT REGISTRY_NAME \
    AGE_KEY_FILE ADMIN_KUBECONFIG DEPLOY_KUBECONFIG
  export PATH="${LOCAL_DIR}/bin:${PATH}"
}

if [[ -t 2 ]]; then
  _c_red=$'\033[31m'; _c_grn=$'\033[32m'; _c_yel=$'\033[33m'; _c_dim=$'\033[2m'; _c_off=$'\033[0m'
else
  _c_red=""; _c_grn=""; _c_yel=""; _c_dim=""; _c_off=""
fi

log()  { printf '%s[%s]%s %s\n' "${_c_dim}" "$(date -u +%H:%M:%S)" "${_c_off}" "$*" >&2; }
ok()   { printf '%s[ OK ]%s %s\n' "${_c_grn}" "${_c_off}" "$*" >&2; }
warn() { printf '%s[WARN]%s %s\n' "${_c_yel}" "${_c_off}" "$*" >&2; }
err()  { printf '%s[FAIL]%s %s\n' "${_c_red}" "${_c_off}" "$*" >&2; }
die()  { err "$*"; exit 1; }

require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "${cmd}" >/dev/null 2>&1 || die "команда '${cmd}' не найдена (см. README → «Предпосылки» или выполните make up)"
  done
}

git_sha() {
  git -C "${ROOT_DIR}" rev-parse --short=12 HEAD 2>/dev/null || echo "nogit000000"
}

git_dirty() {
  if git -C "${ROOT_DIR}" diff --quiet HEAD -- 2>/dev/null; then echo false; else echo true; fi
}

# Интерпретатор для .local/venv: Python >= 3.12 с модулями venv и ensurepip. Порядок: $PYTHON
# (из .env), python3, затем python3.14/3.13/3.12 (Ubuntu 22.04: python3.12 из PPA deadsnakes).
find_python() {
  local c
  for c in ${PYTHON:-} python3 python3.14 python3.13 python3.12; do
    command -v "${c}" >/dev/null 2>&1 || continue
    if "${c}" -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
      >/dev/null 2>&1; then
      command -v "${c}"
      return 0
    fi
  done
  return 1
}

venv_python() {
  local py="${LOCAL_DIR}/venv/bin/python"
  [[ -x "${py}" ]] || die "нет ${py}; выполните make venv (или make up)"
  printf '%s' "${py}"
}
