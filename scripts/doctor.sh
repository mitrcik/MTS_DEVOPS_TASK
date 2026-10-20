#!/usr/bin/env bash
# Диагностика предпосылок хоста. Ничего не меняет в системе.
#   scripts/doctor.sh           — отчёт (код 1 при обязательной неисправности)
#   scripts/doctor.sh --quiet   — только предупреждения и ошибки (используется make up)
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env

QUIET=false
[[ "${1:-}" == "--quiet" ]] && QUIET=true
FAILS=0
WARNS=0
pass()  { $QUIET || ok "$*"; }
fail()  { err "$*"; FAILS=$((FAILS + 1)); }
warns() { warn "$*"; WARNS=$((WARNS + 1)); }

# --- ОС и архитектура -------------------------------------------------------
os_id="unknown"; os_ver="unknown"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  os_id="$(. /etc/os-release && echo "${ID}")"; os_ver="$(. /etc/os-release && echo "${VERSION_ID}")"
fi
case "${os_id} ${os_ver}" in
  "ubuntu 22.04"|"ubuntu 24.04"|"ubuntu 26.04") pass "ОС: Ubuntu ${os_ver} (поддерживаемый профиль)" ;;
  *) warns "ОС ${os_id} ${os_ver}: проверялись Ubuntu 22.04, 24.04, 26.04 LTS" ;;
esac
arch="$(uname -m)"
case "${arch}" in
  x86_64|aarch64) pass "архитектура: ${arch}" ;;
  *) fail "архитектура ${arch}: закреплённые инструменты (infra/tools/tools.yml) есть для x86_64 и aarch64" ;;
esac

# --- Команды ----------------------------------------------------------------
for c in git make curl tar sha256sum python3 docker; do
  if command -v "${c}" >/dev/null 2>&1; then pass "команда ${c}: $(command -v "${c}")"
  else fail "нет команды ${c} — на Ubuntu выполните: make prereqs (или scripts/install-prereqs.sh)"; fi
done
if command -v git >/dev/null 2>&1; then
  if git -C "${ROOT_DIR}" rev-parse --git-dir >/dev/null 2>&1; then
    pass "git-клон проекта читается ($(git -C "${ROOT_DIR}" rev-parse --short=12 HEAD))"
  else
    fail "git не читает ${ROOT_DIR}: это не git clone (архив?) или make запущен не владельцем каталога (sudo → «dubious ownership»); запускайте make без sudo от владельца клона"
  fi
fi
if [[ -x "${LOCAL_DIR}/venv/bin/python" ]]; then
  pass "Python в .local/venv: $("${LOCAL_DIR}/venv/bin/python" -c 'import platform; print(platform.python_version())')"
elif py="$(find_python)"; then
  pass "Python для .local/venv: ${py} ($("${py}" -c 'import platform; print(platform.python_version())'))"
elif command -v python3 >/dev/null 2>&1 \
  && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  fail "у python3 нет модуля venv/ensurepip: make prereqs (или sudo apt-get install -y python3-venv)"
else
  fail "нужен Python >= 3.12 с venv: make prereqs (Ubuntu 22.04 — python3.12 из PPA deadsnakes) или PYTHON=/путь в .env"
fi

# --- Docker -----------------------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  if [[ "$(readlink -f "$(command -v docker)")" == /snap/* ]]; then
    warns "Docker из snap: строгая изоляция snap мешает монтированию файлов проекта в узел k3d; рекомендуется docker.io из Ubuntu (sudo snap remove docker && make prereqs)"
  fi
  if info="$(docker info --format '{{.ServerVersion}}|{{.CgroupVersion}}|{{.NCPU}}|{{.MemTotal}}' 2>&1)"; then
    IFS='|' read -r dver cgv ncpu mem <<<"${info}"
    pass "Docker Engine ${dver} доступен текущему пользователю (это привилегированный доступ к хосту)"
    major="${dver%%.*}"
    [[ "${major}" =~ ^[0-9]+$ && "${major}" -ge 24 ]] || fail "нужен Docker Engine >= 24 (BuildKit secrets), найден ${dver}"
    if bx="$(docker buildx version 2>/dev/null)"; then
      pass "BuildKit/buildx: $(cut -d" " -f2 <<<"${bx}")"
    else
      fail "нет плагина buildx (нужен BuildKit для RUN --mount): sudo apt-get install -y docker-buildx или Docker CE"
    fi
    if [[ "${cgv}" == "1" ]]; then
      warns "cgroup v1: kubelet >= 1.35 по умолчанию отказывается работать; будет добавлен kubelet-флаг fail-cgroupv1=false (Ubuntu 22.04+ по умолчанию на cgroup v2)"
    else
      pass "cgroup v${cgv}"
    fi
    mem_mib=$(( mem / 1024 / 1024 ))
    mem_gb=$(( (mem + 536870912) / 1073741824 ))  # округление: ВМ «8 ГБ» видит ≈ 7,7 ГиБ
    if (( ncpu < 2 )); then fail "CPU для Docker: ${ncpu} (минимум 2, цель проекта 4)"
    elif (( ncpu < 4 )); then warns "CPU для Docker: ${ncpu} (цель проекта 4 vCPU; будет медленнее)"
    else pass "CPU для Docker: ${ncpu}"; fi
    if (( mem_mib < 3584 )); then fail "RAM для Docker: ${mem_gb} ГБ (минимум 4, цель 8)"
    elif (( mem_mib < 7168 )); then warns "RAM для Docker: ${mem_gb} ГБ (цель проекта 8 ГБ)"
    else pass "RAM для Docker: ${mem_gb} ГБ"; fi
  else
    if grep -qi 'permission denied' <<<"${info}"; then
      fail "нет доступа к Docker: добавьте пользователя в группу docker (sudo usermod -aG docker \$USER, затем перелогиньтесь). Это эквивалент root-доступа."
    else
      fail "Docker daemon недоступен (sudo systemctl start docker): ${info%%$'\n'*}"
    fi
  fi
fi

# --- Диск -------------------------------------------------------------------
free_gb=$(( $(df -Pk "${ROOT_DIR}" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
if (( free_gb >= 2 )); then pass "свободно в каталоге проекта: ${free_gb} ГБ"
else fail "мало места в каталоге проекта: ${free_gb} ГБ (нужно >= 2)"; fi
docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
if [[ -d "${docker_root}" ]]; then
  dfree_gb=$(( $(df -Pk "${docker_root}" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
  if (( dfree_gb >= 10 )); then pass "свободно для Docker (${docker_root}): ${dfree_gb} ГБ"
  elif (( dfree_gb >= 6 )); then warns "для Docker свободно ${dfree_gb} ГБ (рекомендуется >= 10)"
  else fail "для Docker свободно ${dfree_gb} ГБ (нужно >= 6)"; fi
else
  warns "каталог данных Docker ${docker_root} не виден отсюда (удалённый daemon или контейнер) — место не проверено"
fi

# --- Лимиты inotify (частая причина «too many open files» в k3s-in-docker) ----
inst="$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo 0)"
if (( inst < 512 )); then
  warns "fs.inotify.max_user_instances=${inst}; при ошибках «too many open files»: sudo sysctl -w fs.inotify.max_user_instances=512"
else
  pass "fs.inotify.max_user_instances=${inst}"
fi

# --- Существующие объекты и порты --------------------------------------------
own_cluster=false
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if [[ -n "$(docker ps -aq --filter "label=k3d.cluster=${CLUSTER_NAME}")" ]]; then
    own_cluster=true
    pass "k3d-кластер '${CLUSTER_NAME}' уже существует — повторный запуск будет идемпотентным"
  fi
  reg_id="$(docker ps -aq --filter "name=^${REGISTRY_NAME}$")"
  if [[ -n "${reg_id}" ]] && ! docker inspect -f '{{ index .Config.Labels "k3d.cluster" }}' "${reg_id}" | grep -qx "${CLUSTER_NAME}"; then
    fail "контейнер '${REGISTRY_NAME}' существует, но не принадлежит кластеру '${CLUSTER_NAME}' — смените CLUSTER_NAME в .env"
  fi
fi
for port in "${INGRESS_PORT}" "${API_PORT}" "${REGISTRY_PORT}"; do
  if python3 - "${BIND_ADDRESS}" "${port}" <<'PY'
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind((sys.argv[1], int(sys.argv[2])))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
  then
    pass "порт ${BIND_ADDRESS}:${port} свободен"
  elif $own_cluster; then
    pass "порт ${BIND_ADDRESS}:${port} занят стендом '${CLUSTER_NAME}'"
  else
    fail "порт ${BIND_ADDRESS}:${port} занят другим процессом (измените порт в .env)"
  fi
done

# --- Сетевой доступ к источникам загрузок -----------------------------------
check_url() {
  local name="$1" url="$2" code rc=0
  # -L: загрузки GitHub Releases отдаются с другого хоста (release-assets.githubusercontent.com);
  # недоступная цель перенаправления — ошибка curl, поэтому учитывается и его код завершения
  code="$(curl -sS -L -o /dev/null -w '%{http_code}' --max-time 15 -I "${url}" 2>/dev/null)" || rc=$?
  if [[ ${rc} -eq 0 && "${code}" =~ ^(2|401|403|405) ]]; then pass "есть доступ: ${name}"
  else warns "нет доступа: ${name} (${url}, HTTP ${code:-000}, curl ${rc})"; fi
}
if [[ ! -x "${LOCAL_DIR}/bin/helm" || ! -x "${LOCAL_DIR}/bin/trivy" ]]; then
  check_url "dl.k8s.io (kubectl)" "https://dl.k8s.io/release/stable.txt"
  check_url "get.helm.sh (helm)" "https://get.helm.sh/helm-v4.3.0-linux-amd64.tar.gz.sha256sum"
  check_url "GitHub Releases (k3d, sops, trivy, age)" "https://github.com/k3d-io/k3d/releases/download/v5.9.0/checksums.txt"
fi
check_url "PyPI (ansible-core, app deps)" "https://pypi.org/simple/ansible-core/"
if [[ -n "${DOCKERHUB_MIRROR:-}" ]]; then
  check_url "зеркало Docker Hub ${DOCKERHUB_MIRROR}" "${DOCKERHUB_MIRROR%/}/v2/"
else
  check_url "Docker Hub (k3s, python, prometheus, grafana)" "https://registry-1.docker.io/v2/"
fi
check_url "ghcr.io (служебный образ k3d-tools)" "https://ghcr.io/v2/"
check_url "mirror.gcr.io (база уязвимостей Trivy)" "https://mirror.gcr.io/v2/"

echo >&2
if (( FAILS > 0 )); then
  err "doctor: ошибок ${FAILS}, предупреждений ${WARNS}. Исправьте ошибки и повторите (docs/troubleshooting.md)."
  exit 1
fi
ok "doctor: обязательные проверки пройдены (предупреждений: ${WARNS})"
