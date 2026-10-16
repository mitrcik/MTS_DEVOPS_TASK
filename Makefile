SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS += --no-print-directory
# см. scripts/lib.sh: локаль из SSH-сеанса может отсутствовать в ВМ, а Ansible её требует
export LC_ALL := C.UTF-8

# Версии (versions.env) и локальные настройки (.env) загружает scripts/lib.sh — единый
# разбор для bash, Ansible и Python; Makefile их не включает, чтобы не было двух синтаксисов.
VENV_PY  := .local/venv/bin/python
BGCTL    := $(VENV_PY) scripts/bgctl.py
PLAYBOOK := scripts/playbook.sh

.env:
	@cp .env.example .env && echo "создан .env из .env.example"

.PHONY: help
help: ## Список команд
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: prereqs
prereqs: ## Однократно на чистой Ubuntu 22.04/24.04/26.04: Docker+buildx, Python, git, make (через sudo)
	@scripts/install-prereqs.sh

.PHONY: venv
venv: ## Python venv с закреплёнными ansible-core/yamllint/ruff (по хешам)
	@scripts/bootstrap-venv.sh

.PHONY: up
up: .env venv ## Подготовка и запуск всего стенда (идемпотентно)
	@t0=$$(date +%s); $(PLAYBOOK) infra/ansible/up.yml; echo "make up: $$(( $$(date +%s) - t0 )) с"

.PHONY: doctor
doctor: ## Диагностика предпосылок хоста (ничего не меняет)
	@scripts/doctor.sh

.PHONY: tools
tools: venv ## Только закреплённые CLI-инструменты в .local/bin (с проверкой sha256)
	@$(PLAYBOOK) infra/ansible/tools.yml

.PHONY: ci
ci: tools ## Локальный прогон стадий CI: lint, test, validate, build, scan, push
	@scripts/ci.sh all

.PHONY: verify
verify: ## Проверка работающего стенда (API, токен, метрики, алерты, Grafana)
	@$(BGCTL) verify

.PHONY: verify-security
verify-security: ## Проверка мер безопасности (non-root, RO FS, NetworkPolicy, RBAC, шифрование Secret)
	@$(BGCTL) verify-security

.PHONY: release
release: ## Выпуск новой версии: make release VERSION=v2
	@test -n "$${VERSION:-}" || { echo "укажите VERSION, например: make release VERSION=v2"; exit 2; }
	@scripts/release.sh --version "$(VERSION)"

.PHONY: demo-failure
demo-failure: ## Релиз с дефектом после переключения → автоматический возврат трафика
	@scripts/release.sh --version "$${VERSION:-v3-faulty}" --fault errors-behind-ingress --expect rolled_back

.PHONY: demo-not-ready
demo-not-ready: ## Релиз кандидата, который не становится Ready → отклонение до переключения
	@scripts/release.sh --version "$${VERSION:-v3-notready}" --fault not-ready --expect rejected

.PHONY: demo-no-metrics
demo-no-metrics: ## Релиз при недоступном Prometheus → gate не даёт ложного успеха
	@scripts/demo-no-metrics.sh

.PHONY: demo-alert
demo-alert: ## Реальный сбой → алерт firing → восстановление → resolved
	@$(BGCTL) demo-alert

.PHONY: recover
recover: ## Восстановить стенд после прерванного релиза (вернуть трафик на подтверждённый релиз)
	@$(BGCTL) recover

.PHONY: rotate-secret
rotate-secret: ## Ротация учебного API-токена с перекрытием и проверкой обоих слотов
	@$(BGCTL) rotate-secret

.PHONY: status
status: ## Активный слот, версии, последние решения
	@$(BGCTL) status

.PHONY: credentials
credentials: ## Показать учебные пароль Grafana и API-токен (только по явному запросу)
	@$(BGCTL) credentials

.PHONY: test-e2e
test-e2e: ## Приёмочные сценарии на работающем стенде (долго, ~10-13 мин)
	@scripts/e2e.sh

.PHONY: down
down: ## Удалить кластер и registry проекта (секреты сохраняются; PURGE=1 CONFIRM=yes — удалить и их)
	@scripts/down.sh

.PHONY: lock
lock: ## Пересобрать lock-файлы Python (нужен uv; отсечка по дате публикации)
	@scripts/lock-deps.sh
