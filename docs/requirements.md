# Матрица требований

Таблицы ниже связывают каждое требование с реализацией, файлами и способом проверки.

**Источник требования** (первая колонка):

- **Кейс** — документ кейса «Конкурс кейсов DevOps 2.1», кейс 1. «п. N» — номер пункта задания.
- **Консультация** — ответ организаторов на консультации с командами.
- **Проект** — инженерное решение команды. Это не требование МТС.

**Статусы:**

- ✅ **проверено** — реальный запуск, доказательства лежат в `docs/validation/`;
- 🟡 **реализовано, но не запущено**;
- 🔧 **требует внешней настройки**;
- ❌ **не реализовано**.

## Инфраструктура как код

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| Кейс, п. 1: Terraform/Ansible | Ansible управляет всем жизненным циклом стенда. Terraform не используется, обоснование — в решении D2 | `infra/ansible/` | `make up` | ✅ |
| Кейс, п. 1: развернуть ВМ/инстанс (VirtualBox/KVM/облако), netplan, cloud-init | Узел кластера — контейнер k3d. Организаторы разрешили это на консультации: «k3d с одной нодой принимается». Готовую ВМ с Ubuntu подготавливает одна команда `make prereqs` (`docs/vm-guide.md`). **Автоматическое создание ВМ (Terraform/cloud-init/netplan) не реализовано** | `scripts/install-prereqs.sh`, `docs/vm-guide.md`, `docs/decisions.md` D1, D13, D16 | Чистые ВМ GitHub: `make prereqs` → … → 15 сценариев на Ubuntu 22.04 x86_64 и 24.04 aarch64 (Docker CE предустановлен). Пакеты Ubuntu 22.04/24.04/26.04 проверены в контейнере (`docs/validation/compat.md`) | ✅ подготовка ВМ · ❌ создание ВМ (осознанная замена) |
| Кейс, п. 1: кластер k3s/minikube/Managed | k3s v1.36.5 в k3d 5.9.0, конфигурация кластера — шаблон в репозитории | `infra/ansible/roles/cluster/templates/k3d-cluster.yaml.j2` | `make up`; `make status` | ✅ |
| Кейс, п. 1: настройка сети | Порты открыты только на loopback (127.0.0.1). Ingress — Traefik. Зеркало registry — внутри узла. Сетевой доступ ограничен NetworkPolicy | шаблон k3d, `charts/platform`, `charts/app` | `make verify-security` | ✅ |
| Консультация: допустим Ansible, который вызывает `helm upgrade` | роли `platform`, `observability` | `infra/ansible/roles/*` | `make up` | ✅ |
| Консультация: свои чарты в репозитории, без приватных компонентов | 4 собственных чарта. Сторонние Helm-репозитории не используются | `charts/`, `observability/` | `helm lint` в `scripts/ci.sh validate` | ✅ |
| Консультация: версии указаны явно | `versions.env`, `infra/tools/tools.yml`, lock-файлы с хешами | README, раздел «Использованные инструменты» | `make doctor`, `make tools` | ✅ |

## CI

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| Кейс, п. 2: запуск по push | GitHub Actions запускается на push в любую ветку и на PR | `.github/workflows/ci.yml` | прогоны Actions (`docs/validation/github-actions.md`) | ✅ |
| Кейс, п. 2: линт | ruff (app, scripts), yamllint, shellcheck, поиск секретов | `scripts/ci.sh lint` | `make ci` | ✅ |
| Кейс, п. 2: unit-тесты | pytest (26 тестов) в образе `target=test`; unittest для gate (17 тестов) | `app/tests/`, `scripts/tests/` | `scripts/ci.sh test` | ✅ |
| Проект: проверка конфигурации | helm lint и JSON-схемы, promtool check/test, amtool, проверка дашборда и исключений Trivy | `scripts/ci.sh validate` | `scripts/ci.sh validate` | ✅ |
| Кейс, п. 2: сборка Docker-образа | Многостадийный Dockerfile. Приложение работает от UID 10001, в итоговом образе нет pip | `app/Dockerfile` | `scripts/ci.sh build` | ✅ |
| Кейс, п. 2: Trivy | Поиск уязвимостей и секретов, политика блокировки. В отчёте указаны версия и дата базы Trivy | `scripts/ci.sh scan`, `scripts/cihelper.py` | `.local/artifacts/*/trivy-summary.json` | ✅ |
| Кейс, п. 2: публикация в registry | Локальный registry (для проверки жюри) и GHCR (в Actions, при push) | `scripts/ci.sh push`, job `image` | прогон Actions: шаг «Публикация в GHCR» | ✅ |
| Проект: развёртывание по digest, тег = Git SHA, provenance | Digest — неизменяемый хеш образа. `provenance.json` — запись о происхождении образа. Без пройденного Trivy релиз отклоняется | `scripts/pylib/release.py` | отчёт релиза | ✅ |
| Проект: в PR нет секретов и публикации; права выдаются на уровне job; actions закреплены по SHA | `permissions: {}`; публикация только при `if: push` | `.github/workflows/ci.yml` | ревью workflow | ✅ (запуск на событие PR не проверялся) |

## CD, blue-green, откат

Blue-green — два слота приложения (blue и green), трафик переключается между ними.
Gate — автоматическая проверка метрик и ответов, которая решает, оставить релиз или откатить его.

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| Кейс, п. 3: деплой через Helm | Чарты слотов и маршрутизации, Helm 4.3.0 | `charts/` | `make release VERSION=v2` | ✅ |
| Кейс, п. 3: blue-green через ingress | Два слота и стабильный Service. Стабильным Service управляет только один Helm-релиз. Ingress — Traefik | `charts/app`, `charts/traffic` | сценарий `release` | ✅ |
| Кейс, п. 3: автоматический откат неудачного релиза | (а) Неготовый кандидат отклоняется до переключения, Helm откатывает слот. (б) Если после переключения сервис деградирует, трафик возвращается на прежний слот, восстановление проверяется | `scripts/pylib/release.py` | `make demo-not-ready`, `make demo-failure` | ✅ |
| Проект: нет метрик — нет успеха | Fail closed: без данных gate не пропускает релиз. Логику покрывают unit-тесты gate | `scripts/pylib/gate.py` | `make demo-no-metrics`; `scripts/tests` | ✅ |
| Проект: общая блокировка для конкурирующих операций | Lease (объект-блокировка Kubernetes) в кластере | `scripts/pylib/lock.py` | сценарий `concurrency` | ✅ |
| Проект: прерывание и восстановление | Фаза релиза хранится в ConfigMap. `make recover` возвращает трафик на последний подтверждённый релиз и снимает зависшие Helm-ревизии | `release.py` | сценарий `interrupted` | ✅ |
| Проект: отчёт о релизе | JSON и Markdown, собираются из фактического выполнения | `.local/reports/` | любой релиз | ✅ |
| Проект: CD на постоянный стенд по SSH | job `deploy` и SSH forced command (ключ может запустить только один скрипт) | `.github/workflows/ci.yml`, `scripts/remote/deploy-gate.sh`, `docs/remote-cd.md` | нужны хост и secrets | 🔧 не проверено |

## Безопасность

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| Кейс, п. 4: секреты вне репозитория (SOPS/Sealed Secrets/Vault) | SOPS + age. Ключ хранится вне проекта. Открытый текст секретов не записывается на диск | `scripts/pylib/secrets.py` | `make verify-security`; `scripts/ci.sh lint` | ✅ |
| Кейс, п. 4: описан процесс ротации | Ротация с перекрытием: какое-то время действуют старый и новый токен. Обновляются оба слота. Ротация идёт под общей блокировкой | `docs/security.md`, `scripts/pylib/rotation.py` | `make rotate-secret`; сценарий `rotation-chain` | ✅ |
| Консультация: меры безопасности описаны и проверяемы | README, раздел «Безопасность»; `docs/security.md` | — | `make verify-security` (17 проверок) | ✅ |
| Проект: Secret зашифрован в хранилище кластера | k3s `--secrets-encryption` | шаблон k3d | `make verify-security` | ✅ |
| Проект: non-root, RO FS, drop ALL, seccomp, PSA restricted, отдельный SA без токена | Pod работает не от root, с файловой системой только для чтения, без Linux capabilities (drop ALL), с профилем seccomp. Namespace — с PSA restricted. У приложения отдельный ServiceAccount без токена | `charts/app`, `charts/platform` | `make verify-security` | ✅ |
| Проект: NetworkPolicy с проверкой, что она реально применяется | default-deny (по умолчанию всё запрещено) и разрешения для слотов | `charts/platform`, `charts/app` | `make verify-security` | ✅ |
| Проект: разные права для установки стенда и для релизов | Role `release-controller`, токен через TokenRequest | `charts/platform/templates/rbac.yaml` | `make verify-security` | ✅ |

## Наблюдаемость

| Источник / требование | Реализация | Путь | Проверка | Статус |
|---|---|---|---|---|
| Кейс, п. 5: Prometheus + Grafana | Prometheus 3.13.4, Grafana 13.2.3, Alertmanager 0.34.1, blackbox 0.28.0. Вся конфигурация — код в репозитории | `observability/` | `make verify` | ✅ |
| Кейс, п. 5: не меньше 1 дашборда | Дашборд «MTS DevOps — демо-API»: проба, 5xx, p50/p95/p99, трафик по слотам, версии, готовность, CPU/RAM, метки релизов | `observability/files/dashboards/` | `make verify` (дашборд загружается автоматически, 15 панелей) | ✅ |
| Кейс, п. 5: не меньше 1 алерта здоровья | 5 алертов. Основной — синтетическая проба: регулярный тестовый запрос к бизнес-методу API | `observability/files/rules/` | `make demo-alert` (firing → resolved); `promtool test rules` | ✅ |
| Проект: runbook | Инструкции по 5 алертам и по прерванному релизу | `docs/runbooks.md` | — | ✅ |
| Консультация: SLI/SLO команда выбирает сама | Учебные SLI и пороги демо-профиля | README, раздел «Мониторинг и наблюдаемость» | — | ✅ (описано) |

## LLM, сдача

| Источник / требование | Реализация | Путь | Статус |
|---|---|---|---|
| Кейс, п. 6: LLM (по желанию), промпты, экономия времени | Claude Code использовался для кода и документации. Мастер-промпт лежит в репозитории. Экономия времени не измерялась | `docs/llm-usage.md`, `docs/llm/master-prompt.md` | ✅ (экономия без количественной оценки) |
| Кейс: запуск не более чем за 3 команды | `git clone`, `cd`, `make up` | README | ✅ (проверено в GitHub Actions на чистом runner) |
| Кейс + консультация: README по шаблону | 12 разделов шаблона и таблица «что сделано → где → как проверить» | `README.md` | ✅ |
| Кейс + консультация: видео не длиннее 5 минут | Сценарий и раскадровка | `docs/demo-script.md` | ❌ видео ещё не записано, запись — задача команды |
| Консультация: состав команды | Кутузов Дмитрий Сергеевич, Рожков Иван Валерьевич, Джумабаев Али | README, раздел 4 | ✅ (роли указываются по желанию участников) |
| Консультация: лицензия (MIT — пример организаторов, не требование) | MIT | `LICENSE`, README, раздел 12 | ✅ |
