#!/usr/bin/env bash
# Полный путь релиза: стадии CI (scripts/ci.sh) → blue-green релиз проверенного digest.
#   scripts/release.sh --version v2 [--fault MODE] [--expect DECISION] [--if-needed]
# --if-needed  ничего не делать, если эта версия этого коммита уже активна и здорова
# CI_STAGES    переопределить набор стадий (по умолчанию все; пропуск фиксируется в provenance)
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env

version="" fault="none" expect="" if_needed=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) version="$2"; shift 2 ;;
    --fault) fault="$2"; shift 2 ;;
    --expect) expect="$2"; shift 2 ;;
    --if-needed) if_needed=true; shift ;;
    *) die "неизвестный аргумент $1" ;;
  esac
done
[[ -n "${version}" ]] || die "укажите версию: make release VERSION=v2"
PY="$(venv_python)"
BGCTL=("${PY}" "${ROOT_DIR}/scripts/bgctl.py")

if ${if_needed}; then
  sha="$(git_sha)"; [[ "$(git_dirty)" == "true" ]] && sha="${sha}-dirty"
  if "${BGCTL[@]}" active --match-version "${version}" --match-git-sha "${sha}" >/dev/null 2>&1; then
    ok "версия ${version} (${sha}) уже активна и здорова — пересборка и релиз не нужны"
    exit 0
  fi
fi

read -r -a stages <<< "${CI_STAGES:-all}"
log "конвейер: стадии ${stages[*]}, версия ${version}, неисправность ${fault}"
prov="$(VERSION="${version}" FAULT="${fault}" "${ROOT_DIR}/scripts/ci.sh" "${stages[@]}" | tail -1)"
[[ -f "${prov}" ]] || die "CI не вернул provenance (стадия push не выполнена?)"
args=(release --provenance "${prov}")
[[ -n "${expect}" ]] && args+=(--expect "${expect}")
"${BGCTL[@]}" "${args[@]}"
