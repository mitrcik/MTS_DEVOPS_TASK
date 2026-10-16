# Прогоны GitHub Actions

Независимая проверка на чистом GitHub-hosted runner `ubuntu-24.04` с полноценным интернетом —
это тот же путь, что у жюри (`make doctor` → `make up` по README), без ограничений среды разработки.
Репозиторий: https://github.com/mitrcik/MTS_DEVOPS_TASK, workflow `.github/workflows/ci.yml`.

## Прогон #1 — commit `da258dd`, событие `push`, ветка `claude/friendly-ride-7k6cyd`

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38818148796

| Job | Результат | Время | Что доказано |
|---|---|---|---|
| `checks` (lint · unit-тесты · проверка конфигурации) | ✅ success | 1 мин 06 с | `make tools` скачал **все** инструменты с официальных адресов (в т.ч. Helm с get.helm.sh) и проверил закреплённые sha256; ruff, yamllint, shellcheck, поиск секретов (104 файла, 0 нарушений), pytest 26, unittest gate 17, helm lint + схемы, promtool check/test, amtool |
| `image` (сборка · Trivy · публикация) | ✅ success | 1 мин 16 с | сборка, Trivy, политика, публикация в GHCR: `ghcr.io/mitrcik/mts_devops_task/mts-api@sha256:be85f06129d9d6881b5acdc39387725312133f7b836a4f5846013a1b9802a4b9` (`GITHUB_TOKEN`, `packages: write` только в этом job) |
| `e2e` (одноразовый k3d в runner) | ✅ success | 12 мин 27 с | `make doctor` 2 с; **`make up` с нуля — 3 мин 21 с**; 14 приёмочных сценариев — 9 мин; `make down` 3 с |
| `deploy` (CD на постоянный стенд) | ⏭ skipped | — | не `main` и не заданы `vars.DEPLOY_HOST`/secrets — доставка на постоянный стенд **не выполнялась** |

Сценарии e2e на runner (из лога job; отчёты загружены артефактом `e2e-reports`):

| сценарий | результат | время, с |
|---|---|---|
| verify — чистый стенд: API через ingress, Grafana, Prometheus targets | passed | 0 |
| idempotent-up — повторный make up не меняет ключ, секреты и активный релиз | passed | 16 |
| release — v2: неактивный слот → проверки → переключение → promoted | passed | 65 |
| not-ready — кандидат не Ready → rejected до переключения | passed | 73 |
| not-ready-safe — пользователи по-прежнему на v2 | passed | 1 |
| rollback — дефект после переключения → автоматический возврат | passed | 41 |
| rollback-safe — после возврата пользователи на v2 | passed | 0 |
| no-metrics — Prometheus недоступен → gate не даёт ложного успеха | passed | 24 |
| alert — реальный сбой → firing → восстановление → resolved | passed | 58 |
| rotation-chain — ротация → неудачный релиз → откат: новый токен работает, старый отклонён | passed | 44 |
| concurrency — конкурирующие ротация и релиз блокируются | passed | 72 |
| security — non-root, RO FS, NetworkPolicy, RBAC, шифрование Secret | passed | 6 |
| down-up — make down удаляет только стенд; повторный make up | passed | 138 |
| verify-again — проверка после пересоздания | passed | 0 |

Примечание: в прогоне #1 ещё не было сценария `interrupted` и исправления `--if-absent`
(они добавлены позже по итогам локального прогона; см. `docs/validation/local-e2e.md`).

## Прогон #2 — commit `6453a7b` (добавлен сценарий `interrupted`, исправление `--if-absent`)

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38819507850

| Job | Результат | Примечание |
|---|---|---|
| `checks` | ✅ success | 1 мин |
| `image` | ✅ success | публикация в GHCR |
| `e2e` | ❌ failure | `make up` с нуля — 3 мин 25 с (Docker 28.0.4 на runner); **14 из 15 сценариев passed**, упал `interrupted` (17 с) |
| `deploy` | ⏭ skipped | не `main` |

Разбор: локально сценарий проходил, на более быстром runner — нет. Логи сценария лежат в артефакте
`e2e-reports`, который из среды разработки скачать нельзя (blob-хранилище закрыто политикой сети),
поэтому причина установлена анализом кода, а не по логу. Наиболее вероятная причина — гонка: `bgctl recover`
переключал Service и сразу завершался, а следующая проверка обращалась к ingress раньше, чем Traefik
применял новые endpoints (~0,5 с), и получала ответ прерванного релиза. Исправление: `recover`
подтверждает восстановление на пользовательском пути — ждёт, пока ingress 5 раз подряд отдаст
release id последнего подтверждённого релиза (иначе ошибка); `e2e.sh` при падении выводит хвост
лога сценария в общий лог CI. Повторная проверка — прогон #3 (ниже): все 15 сценариев прошли,
в том числе `interrupted`. Это согласуется с исправлением, но один зелёный прогон не доказывает
исходную гипотезу о причине.

## Прогон #3 — commit `e6a19d1` (recover ждёт переключения на ingress) — все jobs зелёные

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38822012480

| Job | Результат | Время | Что доказано |
|---|---|---|---|
| `checks` | ✅ success | 1 мин 03 с | инструменты по sha256, lint, unit-тесты, проверка конфигурации |
| `image` | ✅ success | 1 мин 05 с | сборка, Trivy, политика, публикация: `ghcr.io/mitrcik/mts_devops_task/mts-api@sha256:282c0ca03d56db23e89e063c93632fe5f5edff99e7c063c29b33ea750548e31c` |
| `e2e` | ✅ success | 13 мин 03 с | `make doctor` 2 с; **`make up` с нуля — 3 мин 23 с** (Ansible: ok=62 changed=28 failed=0); **15 из 15 сценариев passed** — 9 мин 28 с; `make down` 2 с |
| `deploy` | ⏭ skipped | — | не `main` — доставка на постоянный стенд **не выполнялась** |

Хост runner: Ubuntu 24.04.5 LTS, 4 vCPU, 15 ГБ RAM, Docker 28.0.4. Сценарии (из лога job; отчёты —
артефакт `e2e-reports`):

| сценарий | результат | время, с |
|---|---|---|
| verify | passed | 0 |
| idempotent-up | passed | 16 |
| release (v2) | passed | 65 |
| not-ready | passed | 73 |
| not-ready-safe | passed | 1 |
| rollback | passed | 41 |
| rollback-safe | passed | 1 |
| interrupted | passed | 26 |
| no-metrics | passed | 25 |
| alert | passed | 56 |
| rotation-chain | passed | 44 |
| concurrency | passed | 67 |
| security | passed | 7 |
| down-up | passed | 146 |
| verify-again | passed | 0 |

## Последующие прогоны `ci`

| Run | Commit | Результат |
|---|---|---|
| [#6](https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38826353059) | `4d8a0ff` (make prereqs, arm64, лицензия) | ✅ checks, image, e2e |
| [#9](https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38827448057) | `e6bf26c` (инструкция для ВМ, исправления compat) | ✅ checks, image, e2e |

Прогоны #7 и #8 отменены GitHub как устаревшие ожидающие (в группе concurrency ждёт только самый
новый прогон). Совместимость с другими версиями Ubuntu и arm64 — `compat.md`.

## Итог по runner GitHub

Путь жюри (`git clone` → `cd` → `make up`) проверен на чистом `ubuntu-24.04` без каких-либо
обходов среды разработки: холодный `make up` — 3 мин 21 с, 3 мин 25 с, 3 мин 23 с (прогоны #1–#3).
Прогоны #3, #6 и #9 — все 15 приёмочных сценариев passed. Job `deploy` (CD на постоянный стенд)
ни разу не выполнялся: нет хоста — статус «настроено, не проверено».
