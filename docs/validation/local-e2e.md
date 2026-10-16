# Локальные прогоны (среда разработки)

## Среда

- Ubuntu 24.04.5 LTS x86_64, 4 vCPU, 15 ГБ RAM, Docker Engine 29.8.2 (buildx 0.37.1), Python 3.13.16.
- Дата: 2026-10-15. Версии инструментов — как в README (k3s v1.36.5+k3s1, Helm v4.3.0, kubectl v1.36.5,
  k3d v5.9.0, SOPS 3.13.1, age 1.3.1, Trivy 0.75.0, БД Trivy от 2026-10-15T19:09:25Z).
- Особенности облачной среды разработки и обходы — только через параметры `.env`, пустые по
  умолчанию (`docs/decisions.md` D15): хост на cgroup v1 (автоматический kubelet-флаг), TLS-перехват
  (`EXTRA_CA_BUNDLE`), лимит Docker Hub (`DOCKERHUB_MIRROR`), нет `CAP_SYS_RESOURCE`
  (`K3D_EXTRA_ARGS`), закрыты get.helm.sh и блобы ghcr.io (helm 4.3.0 из `alpine/helm:4.3.0`,
  `K3D_IMAGE_TOOLS=rancher/k3d-tools:5.3.0`). Путь жюри без этих обходов проверен в GitHub Actions
  (`github-actions.md`).
- Финальный прогон выполнен на чистом закоммиченном дереве: Git SHA `a6703daae18c` без пометки `-dirty`.

## Финальный приёмочный прогон `make test-e2e` — 2026-10-16 01:45–01:57 UTC

Команда: `make up && make test-e2e`, код возврата 0, сценарии — 11 мин 15 с, commit `a6703da`
(после независимой перепроверки: сценарии выполняются со строгим `set -e`, поэтому упавший
промежуточный шаг теперь тоже валит сценарий). Сводка — `reports/e2e-summary-20261016T014549Z.md`.
Предыдущие полные прогоны (`697dc89` — дважды 2026-10-15, `e6bf26c` — 2026-10-16 00:28) тоже прошли 15/15.

| сценарий | результат | время, с | доказательство |
|---|---|---|---|
| verify | passed | 1 | 14/14 проверок |
| idempotent-up | passed | 23 | отпечатки ключа, SOPS-файла и активного релиза не изменились |
| release (v2) | passed | 85 | `reports/release-v2-20261016t014642z.md` |
| not-ready | passed | 80 | `reports/release-v3-notready-20261016t014756z.md` |
| not-ready-safe | passed | 1 | активна v2 |
| rollback | passed | 49 | `reports/release-v3-faulty-20261016t014916z.md` (+ `.json`) |
| rollback-safe | passed | 1 | активна v2 |
| interrupted | passed | 24 | `reports/recovery-recover-20261016t015008z.md`: `traffic_restored_to_previous`, ingress подтвердил v2 |
| no-metrics | passed | 29 | `reports/release-v3-nometrics-20261016t015031z.md` |
| alert | passed | 56 | `reports/alert-demo-20261016t015043z.md` |
| rotation-chain | passed | 49 | `reports/rotation-20261016t015138z.md`, затем `reports/release-v3-faulty-after-rotation-20261016t015159z.md` |
| concurrency | passed | 73 | `reports/release-v4-20261016t015244z.md` (promoted); `reports/release-v4-competing-20261016t015250z.md`, `reports/rotation-20261016t015245z.md` (оба `blocked`) |
| security | passed | 11 | 17/17 проверок |
| down-up | passed | 192 | `make down` + `make up` (образы в кэше Docker); `reports/release-v1-20261016t015603z.md` |
| verify-again | passed | 1 | 14/14 |

## Маршрут жюри вручную и «перезагрузка» — 2026-10-16, commit `e6bf26c`

Команды из README и `docs/vm-guide.md` по одной, на стенде после `make down` → `make up` (160 с):

| Команда | Время | Результат |
|---|---|---|
| `make verify` | < 1 с | 14/14 |
| `make release VERSION=v2` | 72 с | `promoted`; HTTP gate: 246 запросов, 0 ошибок, p95 5,9 мс |
| `make status` | 1 с | `[ACTIVE ] green версия=v2`, история решений |
| `make demo-failure` | 44 с | `rolled_back`: 31,8% неуспешных на 22 запросах → возврат, восстановление подтверждено |
| `make demo-not-ready` | 79 с | `rejected` (candidate_not_ready), пользователи на v2 |
| `make demo-no-metrics` | 30 с | `rejected` (metrics_unavailable), Prometheus восстановлен |
| `make demo-alert` | 57 с | pending 10 с → firing 41 с → Alertmanager 43 с → восстановление 47 с → resolved 57 с |
| `make rotate-secret` | 2 с | новый токен работает во всех pod, старый отклоняется |
| `make verify-security` | 7 с | 17/17 |
| `make credentials`, `make help` | < 1 с | вывод учётных данных по явной команде; 21 строка справки |
| перезапуск Docker daemon (имитация перезагрузки ВМ) | 34 с до зелёного `verify` | контейнеры стенда поднялись сами (`restart: unless-stopped`), `make verify` 14/14, активная v2 сохранена; резервный слот с отклонённым релизом помечен «не использовать для ручного возврата» |

## Ключевые измерения (финальный прогон)

| Измерение | Значение | Источник |
|---|---|---|
| Холодный `make up` на чистом runner GitHub | 3 мин 17 с – 3 мин 40 с (Ubuntu 22.04/24.04, x86_64/arm64) | `github-actions.md`, `compat.md` |
| `make up` после `make down` (образы в кэше) | 160–170 с | лог `make up`, сценарий down-up |
| Повторный `make up` на работающем стенде | 20 с, изменений нет | idempotent-up |
| Релиз с полным CI (`make release`) | 72–85 с, из них решение контроллера 56–57 с | release |
| Развёртывание → готовность кандидата | 6–7 с | `durations` отчётов |
| Переключение → новый релиз на ingress | 0,6–0,7 с | `cutover_observed` |
| Окно post-deploy (успешный релиз) | 30 с, 245–246 запросов, 0 ошибок, p95 6–7 мс | `post_deploy_http` |
| Ошибки прежнего релиза в окне ±2 с вокруг переключения | 0 из 37 запросов | `switch_impact` |
| Обнаружение дефекта после переключения | ранняя остановка: 21–22 запроса, 32–33% HTTP 500 | `post_deploy_http` откатов |
| Возврат трафика → прежний релиз на ingress | 0,4–0,5 с | `rollback.seconds_to_cutback` |
| Проверка восстановления после отката | 85–88 запросов, 0 ошибок | `rollback.verification` |
| Полное время неудачного релиза до `rolled_back` | 28–32 с от старта контроллера | `durations.total` |
| Отклонение неготового кандидата | 62 с (progressDeadlineSeconds 60 с) | not-ready |
| Отклонение без метрик | 9 с от старта контроллера | no-metrics |
| Алерт: сбой → pending → firing → Alertmanager → восстановление → resolved | 0 → 2–10 с → 32–39 с → 35–41 с → 40–46 с → 43–55 с | alert-demo (два последних прогона) |
| Ротация с перекрытием (4 pod, 2 слота) | 2–3 с | rotation |
| Пиковая память хоста за `make up` + 15 сценариев | 2,2 ГиБ (`free`, вместе с ≈ 0,8 ГиБ фоновой нагрузки среды) | `compat.md`, прогон Ubuntu 26.04 |
| Место на диске после полного прогона | ≈ 9 ГБ: образы 2,4 ГБ, тома k3d 3,3 ГБ, кэш сборки 0,7 ГБ, `.local` 2,4 ГБ | `docker system df`, `du` |
| Потребление стенда в покое | узел k3d 1,63 ГиБ RAM / ~0,16 vCPU; registry 35 МиБ | `docker stats` |
| Образ приложения | 29 МБ сжатых слоёв, ≈ 122 МБ распакованный | `docker image inspect` |

Числа — один прогон на одной машине, не статистика и не SLA; они показывают порядок величин.
В первом развёртывании (`release-v1-…`) `switch_impact` показывает ошибки «до переключения» —
это 404 до появления маршрута к API, что отмечено в самом отчёте.

## Отдельные проверки во время разработки

| Проверка | Результат |
|---|---|
| `make verify-security` | 17/17: PSA restricted; automount=false; securityContext; uid=10001; `touch /app/probe` → Read-only file system; CapEff=0; токен SA не смонтирован; из pod приложения DNS работает, TCP к API-серверу — отказ; pod из чужого namespace → отказ, через ingress → 200; RBAC deploy SA (update deployments — yes; secrets в kube-system, nodes, clusterroles, pods/exec — no); secrets-encryption Enabled; хеш токена 0 раз открытым текстом в `state.db`, 84 записи `k8s:enc:aescbc:v1:` |
| Trivy, `python:3.13-slim-trixie` vs `python:3.13-alpine3.24` | 166 находок (44 HIGH без исправления, 52 МБ) vs 1 MEDIUM (29 МБ) — выбрана Alpine |
| Прерванный `helm upgrade` (SIGKILL-подобное завершение) | следующий запуск: просроченная Lease перехвачена, операция помечена `interrupted`, ревизия `pending-upgrade` откатана к 7, релиз `promoted` |
| `promtool test rules` | SUCCESS (6 групп) |
| unit-тесты | pytest 26 passed; unittest 17 OK |

## Ошибки, найденные приёмочными сценариями и исправленные

| Найдено | Исправление | Перепроверка |
|---|---|---|
| повторный `make up` при активной v4 перевыпускал начальную v1 | `--if-absent`: начальная версия только при отсутствии здорового активного релиза | idempotent-up passed |
| прерванный `helm upgrade` блокировал следующие релизы (`another operation in progress`) | снятие `pending-*` под общей блокировкой (`_unstick_helm`) | ручной сценарий + interrupted |
| SIGTERM не освобождал Lease | SIGTERM обрабатывается как Ctrl+C | interrupted passed |
| метрики отката снимались до scrape и попадали в причину решения | доказательства по метрикам снимаются после возврата трафика | rollback passed |
| Grafana 13 получала OOMKilled (лимит 384 МиБ) при входе пользователя и открытии дашборда — найдено при снятии скриншота браузером | лимит 1 ГиБ, request 192 МиБ (`observability/values.yaml`); применено через `make up` (44 с) | 0 перезапусков; пик working set 378 МиБ; `grafana-dashboard.png` |

## Снимки

- `grafana-dashboard.png` — дашборд после `make release VERSION=v6` и `make demo-failure`: трафик
  переключается между слотами, у неудачного кандидата (green) доля 5xx ≈ 15%, трафик возвращён.
- `prometheus-targets.png` — все scrape targets `up` (снимок верхней части страницы).
