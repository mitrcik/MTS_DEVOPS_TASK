#!/usr/bin/env bash
# Приёмочные сценарии на работающем стенде (после make up). Каждый сценарий — реальное
# выполнение с кодом возврата, временем и ссылкой на отчёт. Итог: .local/e2e/<run>/summary.md
#   make test-e2e                   все сценарии
#   E2E_ONLY="release rollback"     только выбранные
#   E2E_REBUILD=0                   без финального make down → make up
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env
PY="$(venv_python)"
BGCTL=("${PY}" "${ROOT_DIR}/scripts/bgctl.py")
RUN="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${LOCAL_DIR}/e2e/${RUN}"
mkdir -p "${OUT}"
chmod 700 "${OUT}"
SUMMARY="${OUT}/summary.tsv"
: > "${SUMMARY}"
FAILED=0

want() { [[ -z "${E2E_ONLY:-}" || " ${E2E_ONLY} " == *" $1 "* ]]; }

# scenario <id> <ожидание> <команда...>: код 0 = сценарий выполнен как ожидалось
scenario() {
  local id="$1" expect="$2"; shift 2
  want "${id}" || return 0
  log "━━━━ сценарий ${id}: ${expect}"
  local t0 rc=0
  t0=$(date +%s)
  "$@" > "${OUT}/${id}.log" 2>&1 || rc=$?
  local dt=$(( $(date +%s) - t0 ))
  local report
  report="$(ls -t "${LOCAL_DIR}/reports/"*.md 2>/dev/null | head -1 || true)"
  if [[ ${rc} -eq 0 ]]; then ok "${id}: OK (${dt} с)"; else err "${id}: FAIL rc=${rc} (${dt} с) — ${OUT}/${id}.log"; FAILED=$((FAILED + 1)); fi
  printf '%s\t%s\t%s\t%s\t%s\n' "${id}" "${expect}" "$([[ ${rc} -eq 0 ]] && echo passed || echo failed)" "${dt}" \
    "$(basename "${report:-—}")" >> "${SUMMARY}"
}

# --- вспомогательные проверки -------------------------------------------------
idempotent_up() {
  local before after
  before="$(state_fingerprint)"
  make -C "${ROOT_DIR}" up
  after="$(state_fingerprint)"
  echo "до:    ${before}"; echo "после: ${after}"
  [[ "${before}" == "${after}" ]]
}
state_fingerprint() {
  # ключ, зашифрованный источник и активный релиз не должны меняться от повторного make up
  printf '%s|%s|%s' \
    "$(sha256sum "${AGE_KEY_FILE}" | cut -c1-16)" \
    "$(sha256sum "${LOCAL_DIR}/secrets/app-secrets.sops.yaml" | cut -c1-16)" \
    "$("${BGCTL[@]}" active | "${PY}" -c 'import json,sys; a=json.load(sys.stdin)["active"]; print(a["release_id"], a["digest"][:19])')"
}
still_active() {
  "${BGCTL[@]}" active --match-version "$1" && "${BGCTL[@]}" verify
}
rotation_chain() {
  local old="${OUT}/.old-token"
  "${BGCTL[@]}" token-probe --save-current "${old}"
  "${BGCTL[@]}" rotate-secret
  "${BGCTL[@]}" token-probe --expect-revoked "${old}"
  "${ROOT_DIR}/scripts/release.sh" --version v3-faulty-after-rotation --fault errors-behind-ingress --expect rolled_back
  # после возврата на прежний слот отозванный токен по-прежнему не принимается
  local rc=0
  "${BGCTL[@]}" token-probe --expect-revoked "${old}" || rc=$?
  rm -f "${old}"
  return ${rc}
}
concurrent_release() {
  local K=("${LOCAL_DIR}/bin/kubectl" --kubeconfig "${DEPLOY_KUBECONFIG}" -n mts-app)
  "${ROOT_DIR}/scripts/release.sh" --version v4 --expect promoted > "${OUT}/concurrent-main.log" 2>&1 &
  local main=$!
  # ждём, пока основной релиз дойдёт до этапа под блокировкой
  for _ in $(seq 1 600); do "${K[@]}" get lease mts-api-change-lock >/dev/null 2>&1 && break; sleep 1; done
  "${K[@]}" get lease mts-api-change-lock -o jsonpath='{.spec.holderIdentity}{"\n"}'
  local rc_rot=0 rc_rel=0
  "${BGCTL[@]}" rotate-secret || rc_rot=$?
  CI_STAGES="build scan push" "${ROOT_DIR}/scripts/release.sh" --version v4-competing || rc_rel=$?
  echo "конкурирующая ротация: rc=${rc_rot} (ожидается 10), конкурирующий релиз: rc=${rc_rel} (ожидается 10)"
  wait "${main}"; local rc_main=$?
  tail -5 "${OUT}/concurrent-main.log"
  echo "основной релиз: rc=${rc_main} (ожидается 0)"
  [[ ${rc_rot} -eq 10 && ${rc_rel} -eq 10 && ${rc_main} -eq 0 ]]
}
interrupted_release() {
  # Контроллер получает SIGTERM уже после переключения трафика (фаза observing).
  # Ожидание: блокировка освобождена, фаза сохранена; bgctl recover возвращает трафик
  # на последний подтверждённый релиз.
  local K=("${LOCAL_DIR}/bin/kubectl" --kubeconfig "${DEPLOY_KUBECONFIG}" -n mts-app)
  local before
  before="$("${BGCTL[@]}" active | "${PY}" -c 'import json,sys; print(json.load(sys.stdin)["active"]["release_id"])')"
  CI_STAGES="build scan push" "${ROOT_DIR}/scripts/release.sh" --version v6-interrupted > "${OUT}/interrupted-main.log" 2>&1 &
  local main=$! phase="" pid=""
  for _ in $(seq 1 600); do
    phase="$("${K[@]}" get configmap mts-api-release-state -o jsonpath='{.data.state\.json}' 2>/dev/null \
             | "${PY}" -c 'import json,sys; print(json.load(sys.stdin).get("phase",""))' 2>/dev/null || true)"
    [[ "${phase}" == "observing" ]] && break
    sleep 1
  done
  # процесс контроллера — дочерний у release.sh этого сценария (не ищем по всей системе)
  pid="$(pgrep -P "${main}" -f 'bgctl.py release' | head -1 || true)"
  echo "фаза перед прерыванием: ${phase}; активный слот: $("${K[@]}" get svc mts-api-active -o jsonpath='{.spec.selector.slot}'); pid=${pid}"
  [[ "${phase}" == "observing" && -n "${pid}" ]] || return 1
  kill -TERM "${pid}"
  wait "${main}" || true
  echo "после SIGTERM: фаза=$("${K[@]}" get configmap mts-api-release-state -o jsonpath='{.data.state\.json}' \
        | "${PY}" -c 'import json,sys; print(json.load(sys.stdin)["phase"])'), блокировка: $("${K[@]}" get lease mts-api-change-lock >/dev/null 2>&1 && echo занята || echo свободна)"
  "${BGCTL[@]}" recover
  local after
  after="$("${BGCTL[@]}" active | "${PY}" -c 'import json,sys; d=json.load(sys.stdin); print(d["active"]["release_id"], d["live_slot"], d["active"]["slot"])')"
  echo "последний подтверждённый релиз до: ${before}; после восстановления: ${after}"
  [[ "${after%% *}" == "${before}" ]] && "${BGCTL[@]}" active >/dev/null && "${BGCTL[@]}" verify
}
down_and_up() {
  make -C "${ROOT_DIR}" down
  [[ -z "$(docker ps -aq --filter "label=k3d.cluster=${CLUSTER_NAME}")" ]]
  make -C "${ROOT_DIR}" up
}

# --- сценарии (порядок важен: каждый опирается на состояние после предыдущего) ----
scenario verify         "чистый стенд: API через ingress, Grafana, Prometheus targets"  "${BGCTL[@]}" verify
scenario idempotent-up  "повторный make up не меняет ключ, секреты и активный релиз"     idempotent_up
scenario release        "релиз v2: неактивный слот → проверки → переключение → promoted" \
  "${ROOT_DIR}/scripts/release.sh" --version v2 --expect promoted
scenario not-ready      "кандидат не Ready → rejected до переключения"                  \
  "${ROOT_DIR}/scripts/release.sh" --version v3-notready --fault not-ready --expect rejected
scenario not-ready-safe "после отклонения пользователи по-прежнему на v2"               still_active v2
scenario rollback       "дефект после переключения → автоматический возврат трафика"     \
  "${ROOT_DIR}/scripts/release.sh" --version v3-faulty --fault errors-behind-ingress --expect rolled_back
scenario rollback-safe  "после возврата пользователи на v2, бизнес-методы работают"     still_active v2
scenario interrupted    "SIGTERM контроллеру после переключения → recover возвращает трафик" interrupted_release
scenario no-metrics     "Prometheus недоступен → gate не даёт ложного успеха"           \
  env VERSION=v3-nometrics "${ROOT_DIR}/scripts/demo-no-metrics.sh"
scenario alert          "реальный сбой → firing → восстановление → resolved"            "${BGCTL[@]}" demo-alert
scenario rotation-chain "ротация → неудачный релиз → откат: новый токен работает, старый отклонён" rotation_chain
scenario concurrency    "конкурирующие ротация и релиз блокируются общей блокировкой"   concurrent_release
scenario security       "non-root, RO FS, NetworkPolicy, RBAC, шифрование Secret"       "${BGCTL[@]}" verify-security
if [[ "${E2E_REBUILD:-1}" == "1" ]]; then
  scenario down-up      "make down удаляет только стенд; повторный make up воспроизводим" down_and_up
  scenario verify-again "проверка после пересоздания"                                     "${BGCTL[@]}" verify
fi

{
  echo "# Приёмочные сценарии ${RUN}"
  echo
  echo "Хост: $(. /etc/os-release && echo "${PRETTY_NAME}"), $(uname -m), $(nproc) vCPU, $(free -g | awk '/Mem/{print $2}') ГБ RAM; Docker $(docker version --format '{{.Server.Version}}')"
  echo
  echo "| сценарий | ожидание | результат | время, с | последний отчёт |"
  echo "|---|---|---|---|---|"
  while IFS=$'\t' read -r id expect res dt rep; do echo "| ${id} | ${expect} | **${res}** | ${dt} | ${rep} |"; done < "${SUMMARY}"
} > "${OUT}/summary.md"
cat "${OUT}/summary.md"
(( FAILED == 0 )) || die "сценариев с ошибкой: ${FAILED} (логи: ${OUT})"
ok "все сценарии пройдены; отчёт ${OUT}/summary.md"
