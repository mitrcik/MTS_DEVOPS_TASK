#!/usr/bin/env bash
# Короткий итог после make up: адреса стенда, активная версия и следующие шаги.
#   scripts/summary.sh [секунды]   — время make up, если передано
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env

PY="$(venv_python)"
base="http://${BIND_ADDRESS}:${INGRESS_PORT}"
active="$("${PY}" "${ROOT_DIR}/scripts/bgctl.py" active 2>/dev/null \
  | "${PY}" -c 'import json, sys
d = json.load(sys.stdin); a = d["active"]
print("%s в слоте %s (релиз %s)" % (a["version"], d["live_slot"], a["release_id"]))' 2>/dev/null)" \
  || active="нет подтверждённого релиза — подробности: make status"
took=""
[[ -n "${1:-}" ]] && took=" за ${1} с"

line="════════════════════════════════════════════════════════════════════════"
cat >&2 <<EOF

${_c_grn}${line}${_c_off}
${_c_grn} Стенд готов${took}.${_c_off} Все адреса открываются только на этом компьютере (127.0.0.1).

   API:           ${base}/api/v1/tariffs
   Grafana:       http://grafana.localhost:${INGRESS_PORT}   (логин admin, пароль: make credentials)
   Prometheus:    http://prometheus.localhost:${INGRESS_PORT}
   Alertmanager:  http://alertmanager.localhost:${INGRESS_PORT}

   Пользователей обслуживает: ${active}

 Что дальше:  make verify            — проверка стенда (14 проверок)
              make release VERSION=v2 — выпуск новой версии без простоя
              make demo-failure       — неудачная версия и автоматический откат
              make demo-alert         — алерт: сбой → firing → восстановление → resolved
              make status             — слоты, версии и история решений
${_c_grn}${line}${_c_off}
EOF
