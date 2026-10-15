#!/usr/bin/env bash
# SSH forced command пользователя деплоя на удалённом Ubuntu-стенде (docs/remote-cd.md).
# В ~deploy/.ssh/authorized_keys:
#   restrict,command="/opt/mts-devops/scripts/remote/deploy-gate.sh" ssh-ed25519 AAAA… github-actions
# Разрешены только две операции; произвольные команды, shell, port-forwarding запрещены (restrict).
#   ssh deploy@host status
#   ssh deploy@host release < provenance.json     # JSON из job image того же workflow
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${ROOT_DIR}/.local/venv/bin/python"
BGCTL=("${PY}" "${ROOT_DIR}/scripts/bgctl.py")

case "${SSH_ORIGINAL_COMMAND:-}" in
  status)
    exec "${BGCTL[@]}" status
    ;;
  release)
    workdir="$(mktemp -d)"
    trap 'rm -rf "${workdir}"' EXIT
    # не больше 64 КиБ: provenance — небольшой JSON; структуру и digest проверяет bgctl
    head -c 65536 > "${workdir}/provenance.json"
    "${BGCTL[@]}" release --provenance "${workdir}/provenance.json"
    ;;
  *)
    echo "deploy-gate: разрешены только 'status' и 'release'" >&2
    exit 64
    ;;
esac
