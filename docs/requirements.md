# Матрица требований

Источники: **W** — Word «Конкурс кейсов DevOps 2.1», кейс 1; **ВКС** — расшифровка созвона
(таймкод `[мм:сс]`); **П** — инженерное решение этого проекта (не требование МТС).

Статусы: ✅ **проверено** (реальный запуск, доказательства в `docs/validation/`) ·
🟡 **реализовано, но не запущено** · 🔧 **требует внешней настройки** · ❌ **не реализовано**.

## Инфраструктура как код

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| W1: Terraform/Ansible | Ansible оркестрирует весь жизненный цикл стенда; Terraform не используется (обоснование D2) | `infra/ansible/` | `make up` | ✅ |
| W1: развернуть ВМ/инстанс (VirtualBox/KVM/облако), netplan, cloud-init | Узел кластера — контейнер k3d по разрешению ВКС [24:27] («k3d с одной нодой принимается»). Готовая ВМ с Ubuntu подготавливается одной командой `make prereqs` (`docs/vm-guide.md`); **автоматическое создание ВМ (Terraform/cloud-init/netplan) не реализовано** | `scripts/install-prereqs.sh`, `docs/vm-guide.md`, `docs/decisions.md` D1, D13, D16 | чистые ВМ GitHub: `make prereqs` → … → 15 сценариев на Ubuntu 22.04 x86_64 и 24.04 aarch64 (Docker CE предустановлен); пакеты Ubuntu 22.04/24.04/26.04 в контейнере (`docs/validation/compat.md`) | ✅ подготовка ВМ · ❌ создание ВМ (осознанная замена) |
| W1: кластер k3s/minikube/Managed | k3s v1.36.5 в k3d 5.9.0, версионированный шаблон | `infra/ansible/roles/cluster/templates/k3d-cluster.yaml.j2` | `make up`; `make status` | ✅ |
| W1: настройка сети | порты только на loopback, Traefik ingress, registry-зеркало в узле, NetworkPolicy | шаблон k3d, `charts/platform`, `charts/app` | `make verify-security` | ✅ |
| ВКС [02:26, 24:20]: Ansible, вызывающий helm upgrade, допустим | роли `platform`, `observability` | `infra/ansible/roles/*` | `make up` | ✅ |
| ВКС [02:58, 33:44]: свои чарты в репозитории, без приватных компонентов | 4 собственных чарта, сторонние Helm-репозитории не используются | `charts/`, `observability/` | `helm lint` в `scripts/ci.sh validate` | ✅ |
| ВКС [06:50, 29:47]: явные версии | `versions.env`, `infra/tools/tools.yml`, lock-файлы с хешами | README «Инструменты» | `make doctor`, `make tools` | ✅ |

## CI

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| W2: по push | GitHub Actions на push в любую ветку и PR | `.github/workflows/ci.yml` | прогоны Actions (`docs/validation/github-actions.md`) | ✅ |
| W2: линт | ruff (app, scripts), yamllint, shellcheck, поиск секретов | `scripts/ci.sh lint` | `make ci` | ✅ |
| W2: unit-тесты | pytest (26) в образе target=test; unittest gate (17) | `app/tests/`, `scripts/tests/` | `scripts/ci.sh test` | ✅ |
| П: проверка конфигурации | helm lint + JSON-схемы, promtool check/test, amtool, проверка дашборда и исключений Trivy | `scripts/ci.sh validate` | `scripts/ci.sh validate` | ✅ |
| W2: сборка Docker-образа | многостадийный Dockerfile, UID 10001, без pip | `app/Dockerfile` | `scripts/ci.sh build` | ✅ |
| W2: Trivy | vuln+secret, политика блокировки, версия и дата БД в отчёте | `scripts/ci.sh scan`, `scripts/cihelper.py` | `.local/artifacts/*/trivy-summary.json` | ✅ |
| W2: публикация в registry | локальный registry (жюри), GHCR (Actions, push) | `scripts/ci.sh push`, job `image` | Actions run: шаг «Публикация в GHCR» | ✅ |
| П: развёртывание по digest, тег = Git SHA, provenance | `provenance.json`, отказ без Trivy passed | `scripts/pylib/release.py` | отчёт релиза | ✅ |
| П: PR без секретов и публикации; права на уровне job; действия по SHA | `permissions: {}`; публикация `if: push` | `.github/workflows/ci.yml` | ревью workflow | ✅ (PR-событие не запускалось) |

## CD, blue-green, откат

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| W3: деплой через Helm | чарты слотов и маршрутизации, Helm 4.3.0 | `charts/` | `make release VERSION=v2` | ✅ |
| W3: blue-green через ingress | два слота + стабильный Service с одним владельцем, Traefik | `charts/app`, `charts/traffic` | сценарий `release` | ✅ |
| W3: автоматический откат неудачного релиза | (а) неготовый кандидат отклоняется до переключения, Helm откатывает слот; (б) деградация после переключения → возврат трафика и проверка восстановления | `scripts/pylib/release.py` | `make demo-not-ready`, `make demo-failure` | ✅ |
| П: нет метрик ≠ успех | fail closed, unit-тесты gate | `scripts/pylib/gate.py` | `make demo-no-metrics`; `scripts/tests` | ✅ |
| П: общая блокировка, конкурирующие операции | Lease в кластере | `scripts/pylib/lock.py` | сценарий `concurrency` | ✅ |
| П: прерывание и восстановление | фаза в ConfigMap, `make recover`, снятие зависших Helm-ревизий | `release.py` | сценарий `interrupted` | ✅ |
| П: отчёт о релизе | JSON + Markdown из фактического выполнения | `.local/reports/` | любой релиз | ✅ |
| П: CD на постоянный стенд по SSH | job `deploy` + forced command | `.github/workflows/ci.yml`, `scripts/remote/deploy-gate.sh`, `docs/remote-cd.md` | нужен хост и secrets | 🔧 не проверено |

## Безопасность

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| W4: секреты вне репозитория (SOPS/Sealed Secrets/Vault) | SOPS + age; ключ вне проекта; plaintext не на диске | `scripts/pylib/secrets.py` | `make verify-security`; `scripts/ci.sh lint` | ✅ |
| W4: описан процесс ротации | ротация с перекрытием, оба слота, под блокировкой | `docs/security.md`, `scripts/pylib/rotation.py` | `make rotate-secret`; сценарий `rotation-chain` | ✅ |
| ВКС [10:55, 40:02]: меры описаны и проверяемы | раздел «Безопасность» README, `docs/security.md` | — | `make verify-security` (17 проверок) | ✅ |
| П: Secret зашифрован в хранилище кластера | k3s `--secrets-encryption` | шаблон k3d | `make verify-security` | ✅ |
| П: non-root, RO FS, drop ALL, seccomp, PSA restricted, отдельный SA без токена | `charts/app`, `charts/platform` | — | `make verify-security` | ✅ |
| П: NetworkPolicy с проверкой enforcement | default-deny + разрешения слота | `charts/platform`, `charts/app` | `make verify-security` | ✅ |
| П: разделение bootstrap и релизных прав | Role `release-controller`, TokenRequest | `charts/platform/templates/rbac.yaml` | `make verify-security` | ✅ |

## Наблюдаемость

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| W5: Prometheus + Grafana | Prometheus 3.13.4, Grafana 13.2.3, Alertmanager 0.34.1, blackbox 0.28.0 — как код | `observability/` | `make verify` | ✅ |
| W5: ≥ 1 дашборд | «MTS DevOps — демо-API»: проба, 5xx, p50/p95/p99, трафик по слотам, версии, готовность, CPU/RAM, метки релизов | `observability/files/dashboards/` | `make verify` (provisioned, 15 панелей) | ✅ |
| W5: ≥ 1 алерт здоровья | 5 алертов; основной — синтетическая проба бизнес-метода | `observability/files/rules/` | `make demo-alert` (firing → resolved); `promtool test rules` | ✅ |
| П: runbook | 5 алертов + прерванный релиз | `docs/runbooks.md` | — | ✅ |
| ВКС [32:49]: SLI/SLO по выбору команды | учебные SLI и пороги демо-профиля (раздел README) | README «Мониторинг» | — | ✅ (описано) |

## LLM, сдача

| Источник / требование | Реализация | Путь | Статус |
|---|---|---|---|
| W6: LLM (опционально), промпты, экономия | Claude Code для кода/документации; мастер-промпт в репозитории; экономия не измерялась | `docs/llm-usage.md`, `docs/llm/master-prompt.md` | ✅ (честно: без количественной оценки) |
| W: «≤ 3 команды» | `git clone`, `cd`, `make up` | README | ✅ (в GitHub Actions на чистом runner) |
| W/ВКС [37:47]: README по шаблону | 12 разделов шаблона + «что сделано → где → как проверить» | `README.md` | ✅ |
| W/ВКС [07:23]: видео ≤ 5 мин | сценарий и кадры | `docs/demo-script.md` | ❌ запись — за командой |
| ВКС [37:47]: состав команды | Кутузов Дмитрий Сергеевич, Рожков Иван Валерьевич, Джумабаев Али | README §4 | ✅ (роли — по желанию участников) |
| ВКС [37:47]: лицензия (MIT — пример ведущего, не требование) | MIT | `LICENSE`, README §12 | ✅ |
