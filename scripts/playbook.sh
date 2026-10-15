#!/usr/bin/env bash
# Запуск Ansible-плейбука проекта с загруженными versions.env/.env и выделенным ansible.cfg.
#   scripts/playbook.sh infra/ansible/up.yml [доп. аргументы ansible-playbook]
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env
export ANSIBLE_CONFIG="${ROOT_DIR}/infra/ansible/ansible.cfg"
export PROJECT_DIR="${ROOT_DIR}"
[[ -x "${LOCAL_DIR}/venv/bin/ansible-playbook" ]] || die "нет Ansible в .local/venv; выполните make venv"
exec "${LOCAL_DIR}/venv/bin/ansible-playbook" "$@"
