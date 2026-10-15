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

Разбор: локально сценарий проходил, на более быстром runner — нет. Причина — гонка: `bgctl recover`
переключал Service и сразу завершался, а следующая проверка обращалась к ingress раньше, чем Traefik
применял новые endpoints (~0,5 с), и получала ответ прерванного релиза. Исправление: `recover`
подтверждает восстановление на пользовательском пути — ждёт, пока ingress 5 раз подряд отдаст
release id последнего подтверждённого релиза (иначе ошибка); `e2e.sh` при падении выводит хвост
лога сценария в общий лог CI. Повторная проверка — прогон #3.
