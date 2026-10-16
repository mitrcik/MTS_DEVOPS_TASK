#!/usr/bin/env bash
# Полный путь релиза: стадии CI (scripts/ci.sh) → blue-green релиз проверенного digest.
#   scripts/release.sh --version v2 [--fault MODE] [--expect DECISION] [--if-absent]
# --if-absent  (make up) ничего не делать, если на стенде уже есть здоровый активный релиз
#              любой версии: повторный make up не перевыпускает и не откатывает рабочую версию
# CI_STAGES    переопределить набор стадий (по умолчанию все; пропуск фиксируется в provenance)
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env

version="" fault="none" expect="" if_absent=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) version="$2"; shift 2 ;;
    --fault) fault="$2"; shift 2 ;;
    --expect) expect="$2"; shift 2 ;;
    --if-absent) if_absent=true; shift ;;
    *) die "неизвестный аргумент $1" ;;
  esac
done
[[ -n "${version}" ]] || die "укажите версию: make release VERSION=v2"
PY="$(venv_python)"
BGCTL=("${PY}" "${ROOT_DIR}/scripts/bgctl.py")

if ${if_absent}; then
  if active_json="$("${BGCTL[@]}" active 2>/dev/null)"; then
    ok "на стенде уже есть здоровый активный релиз — make up его не меняет: ${active_json:0:160}…"
    log "выпустить текущий код: make release VERSION=<версия>"
    exit 0
  fi
fi

read -r -a stages <<< "${CI_STAGES:-all}"
log "конвейер: стадии ${stages[*]}, версия ${version}, неисправность ${fault}"
prov="$(VERSION="${version}" FAULT="${fault}" "${ROOT_DIR}/scripts/ci.sh" "${stages[@]}" | tail -1)"
[[ -f "${prov}" ]] || die "CI не вернул provenance (стадия push не выполнена?)"
args=(release --provenance "${prov}")
[[ -n "${expect}" ]] && args+=(--expect "${expect}")
# ALLOWED_IMAGE_REPOSITORY ограничивает доставки извне (scripts/remote/deploy-gate.sh); здесь образ
# только что собран и просканирован локально, поэтому список разрешённых репозиториев не применяется
ALLOWED_IMAGE_REPOSITORY='' "${BGCTL[@]}" "${args[@]}"
