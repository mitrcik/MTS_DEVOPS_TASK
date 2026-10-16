#!/usr/bin/env bash
# Однократная подготовка чистой Ubuntu 22.04 / 24.04 / 26.04 LTS (x86_64 или aarch64) под make up:
#   - Docker Engine и плагин buildx из репозитория Ubuntu (пакеты docker.io, docker-buildx);
#     уже установленный Docker (в т.ч. Docker CE) не переустанавливается;
#   - git, make, curl, Python >= 3.12 с модулем venv (Ubuntu 22.04: python3.12 из PPA deadsnakes);
#   - лимиты inotify с запасом для k3s в Docker;
#   - пользователь, запустивший скрипт через sudo, — в группу docker.
# Идемпотентен. Запуск: make prereqs (или scripts/install-prereqs.sh; sudo спросит пароль).
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

if [[ ${EUID} -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || die "нужны права root (apt, sysctl), а sudo не найден"
  log "нужны права root для apt и sysctl — перезапуск через sudo"
  exec sudo --preserve-env=http_proxy,https_proxy,no_proxy,HTTP_PROXY,HTTPS_PROXY,NO_PROXY \
    bash "$0" "$@"
fi
TARGET_USER="${SUDO_USER:-}"

# --- ОС и архитектура -------------------------------------------------------
[[ -r /etc/os-release ]] || die "нет /etc/os-release — скрипт рассчитан на Ubuntu"
# shellcheck disable=SC1091
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] \
  || die "скрипт рассчитан на Ubuntu (найдено ${ID:-?} ${VERSION_ID:-?}). Вручную нужны: Docker >= 24 с buildx, Python >= 3.12 с venv, git, make, curl"
case "${VERSION_ID}" in
  22.04|24.04|26.04) ok "Ubuntu ${VERSION_ID} (${VERSION_CODENAME}), $(uname -m)" ;;
  *) warn "Ubuntu ${VERSION_ID} не проверялась (проверены 22.04, 24.04, 26.04) — продолжаю" ;;
esac
case "$(uname -m)" in
  x86_64|aarch64) ;;
  *) die "архитектура $(uname -m) не поддерживается: закреплённые инструменты есть для x86_64 и aarch64" ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt_install() { apt-get install -y -q --no-install-recommends "$@"; }

log "apt-get update"
apt-get update -q

pkgs=(ca-certificates curl git make tar coreutils procps)

# --- Python >= 3.12 с venv --------------------------------------------------
py_candidate="$(apt-cache policy python3 | awk '/Candidate:/ {print $2}')"
py_mm="$(sed -E 's/^([0-9]+\.[0-9]+).*/\1/' <<<"${py_candidate}")"
use_deadsnakes=false
if [[ "$(printf '%s\n' 3.12 "${py_mm}" | sort -V | head -1)" == "3.12" ]]; then
  pkgs+=(python3 python3-venv)
else
  # Ubuntu 22.04: системный Python 3.10, а ansible-core 2.21 требует >= 3.12
  use_deadsnakes=true
  pkgs+=(python3 gpg)
fi

# --- Docker Engine + buildx -------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  ok "Docker уже установлен ($(docker --version)) — не переустанавливаю"
  if ! docker buildx version >/dev/null 2>&1; then
    if dpkg -s docker-ce-cli >/dev/null 2>&1; then pkgs+=(docker-buildx-plugin); else pkgs+=(docker-buildx); fi
  fi
else
  pkgs+=(docker.io docker-buildx)
fi

log "устанавливаю пакеты: ${pkgs[*]}"
apt_install "${pkgs[@]}"

# PPA deadsnakes подключается с проверкой отпечатка ключа (сверен с Launchpad и keyserver.ubuntu.com)
DEADSNAKES_FPR="F23C5A6CF475977595C89F51BA6932366A755776"
if ${use_deadsnakes}; then
  log "Python ${py_mm} в Ubuntu ${VERSION_ID} старше нужного: python3.12 из PPA deadsnakes"
  keyring=/etc/apt/keyrings/deadsnakes.gpg
  install -m 0755 -d /etc/apt/keyrings
  tmp_key="$(mktemp)"
  curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&options=mr&search=0x${DEADSNAKES_FPR}" -o "${tmp_key}"
  got_fpr="$(gpg --show-keys --with-colons "${tmp_key}" 2>/dev/null | awk -F: '/^fpr:/ {print $10; exit}')"
  [[ "${got_fpr}" == "${DEADSNAKES_FPR}" ]] \
    || die "ключ PPA deadsnakes: ожидался отпечаток ${DEADSNAKES_FPR}, получен '${got_fpr}'"
  gpg --dearmor --yes -o "${keyring}" "${tmp_key}" && chmod 0644 "${keyring}" && rm -f "${tmp_key}"
  echo "deb [signed-by=${keyring}] https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu ${VERSION_CODENAME} main" \
    > /etc/apt/sources.list.d/deadsnakes.list
  apt-get update -q
  apt_install python3.12 python3.12-venv
fi

if [[ -d /run/systemd/system ]] && systemctl cat docker.service >/dev/null 2>&1; then
  systemctl enable --now docker.service >/dev/null 2>&1 || systemctl start docker.service
  ok "служба docker включена и запущена"
else
  warn "systemd не обнаружен (контейнер или WSL без systemd): Docker daemon нужно запустить самостоятельно"
fi

# --- Доступ к Docker без sudo ------------------------------------------------
relogin=false
if [[ -n "${TARGET_USER}" && "${TARGET_USER}" != "root" ]]; then
  getent group docker >/dev/null || groupadd docker
  if id -nG "${TARGET_USER}" | tr ' ' '\n' | grep -qx docker; then
    ok "пользователь ${TARGET_USER} уже в группе docker"
  else
    usermod -aG docker "${TARGET_USER}"
    relogin=true
    ok "пользователь ${TARGET_USER} добавлен в группу docker (это эквивалент root-доступа к хосту)"
  fi
fi

# --- inotify: k3s, Prometheus и Grafana в одном узле держат много наблюдателей ---
conf=/etc/sysctl.d/90-mts-devops-inotify.conf
cur_inst="$(cat /proc/sys/fs/inotify/max_user_instances)"
cur_watch="$(cat /proc/sys/fs/inotify/max_user_watches)"
if (( cur_inst < 512 || cur_watch < 524288 )); then
  printf 'fs.inotify.max_user_instances = %s\nfs.inotify.max_user_watches = %s\n' \
    "$(( cur_inst > 512 ? cur_inst : 512 ))" "$(( cur_watch > 524288 ? cur_watch : 524288 ))" > "${conf}"
  sysctl -q -p "${conf}" >/dev/null 2>&1 || true
  if (( $(cat /proc/sys/fs/inotify/max_user_instances) >= 512 )); then
    ok "лимиты inotify увеличены (${conf})"
  else
    warn "лимиты inotify записаны в ${conf}, но не применены сейчас (контейнер?) — применятся после перезагрузки"
  fi
else
  ok "лимиты inotify достаточны (${cur_inst}/${cur_watch})"
fi

# --- Итог -------------------------------------------------------------------
py="$(find_python)" || die "не найден Python >= 3.12 с модулем venv после установки"
ok "Python для .local/venv: ${py} ($("${py}" -c 'import platform; print(platform.python_version())'))"
ok "$(docker --version); buildx $(docker buildx version 2>/dev/null | cut -d' ' -f2)"
echo >&2
if ${relogin}; then
  warn "права группы docker вступят в силу в новом сеансе: перелогиньтесь (или выполните: newgrp docker)"
fi
ok "предпосылки готовы. Дальше: make doctor && make up"
