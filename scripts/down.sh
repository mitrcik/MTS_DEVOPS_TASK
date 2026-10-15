#!/usr/bin/env bash
# Удаляет только ресурсы этого проекта: k3d-кластер CLUSTER_NAME, его registry и сеть,
# локальные kubeconfig и образы проекта. Чужие контейнеры/кластеры не затрагиваются.
#   make down                          — секреты (SOPS-источник и age-ключ) сохраняются
#   make down PURGE=1 CONFIRM=yes      — дополнительно удалить секреты, ключ, отчёты и артефакты
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env

K3D="${LOCAL_DIR}/bin/k3d"
if [[ -x "${K3D}" ]] && "${K3D}" cluster get "${CLUSTER_NAME}" >/dev/null 2>&1; then
  log "удаляю k3d-кластер ${CLUSTER_NAME} (вместе с registry ${REGISTRY_NAME})"
  "${K3D}" cluster delete "${CLUSTER_NAME}"
else
  log "k3d-кластер ${CLUSTER_NAME} не найден"
fi

leftovers="$(docker ps -aq --filter "label=k3d.cluster=${CLUSTER_NAME}")"
if [[ -n "${leftovers}" ]]; then
  warn "остались контейнеры кластера: ${leftovers//$'\n'/ } — удаляю"
  # shellcheck disable=SC2086
  docker rm -f ${leftovers} >/dev/null
fi
docker network rm "k3d-${CLUSTER_NAME}" >/dev/null 2>&1 || true

rm -f "${ADMIN_KUBECONFIG}" "${DEPLOY_KUBECONFIG}" "${LOCAL_DIR}/k3d/cluster.yaml"

images="$(docker images --format '{{.Repository}}:{{.Tag}}' \
  | grep -E "^(localhost:${REGISTRY_PORT}/mts-api|mts-api-test):" || true)"
if [[ -n "${images}" ]]; then
  # shellcheck disable=SC2086
  docker rmi ${images} >/dev/null 2>&1 || true
  log "удалены локальные образы проекта ($(wc -l <<<"${images}"))"
fi

if [[ "${PURGE:-0}" == "1" ]]; then
  [[ "${CONFIRM:-}" == "yes" ]] || die "PURGE=1 удаляет age-ключ и зашифрованные секреты без возможности восстановления; повторите с CONFIRM=yes"
  rm -rf "${LOCAL_DIR}/secrets" "${LOCAL_DIR}/reports" "${LOCAL_DIR}/artifacts"
  rm -f "${AGE_KEY_FILE}"
  rmdir "$(dirname "${AGE_KEY_FILE}")" 2>/dev/null || true
  ok "секреты, age-ключ (${AGE_KEY_FILE}), отчёты и артефакты удалены"
else
  log "сохранены: ${LOCAL_DIR}/secrets (SOPS) и ключ ${AGE_KEY_FILE} — следующий make up переиспользует их"
fi

remaining="$(docker ps -aq --filter "label=k3d.cluster=${CLUSTER_NAME}")"
[[ -z "${remaining}" ]] || die "после удаления остались контейнеры кластера: ${remaining}"
ok "ресурсы стенда ${CLUSTER_NAME} удалены"
