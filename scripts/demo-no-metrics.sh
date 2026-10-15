#!/usr/bin/env bash
# Сценарий «нет достоверных метрик»: Prometheus временно остановлен (права администратора
# стенда), затем выполняется обычный релиз. Gate обязан отказать (fail closed), а не
# объявить релиз здоровым. Prometheus восстанавливается в любом случае.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env
KUBECTL=("${LOCAL_DIR}/bin/kubectl" --kubeconfig "${ADMIN_KUBECONFIG}" -n monitoring)
PY="$(venv_python)"

restore() {
  log "восстанавливаю Prometheus"
  "${KUBECTL[@]}" scale deployment prometheus --replicas=1 >/dev/null
  "${KUBECTL[@]}" rollout status deployment/prometheus --timeout=180s >/dev/null
  "${PY}" "${ROOT_DIR}/scripts/bgctl.py" wait-observability --timeout 180
}
trap restore EXIT

log "останавливаю Prometheus (имитация недоступной наблюдаемости)"
"${KUBECTL[@]}" scale deployment prometheus --replicas=0 >/dev/null
"${KUBECTL[@]}" wait --for=delete pod -l app.kubernetes.io/name=prometheus --timeout=120s >/dev/null 2>&1 || true

"${ROOT_DIR}/scripts/release.sh" --version "${VERSION:-v3-nometrics}" --expect rejected
