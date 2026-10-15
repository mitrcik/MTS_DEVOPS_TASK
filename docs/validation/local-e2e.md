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
- Git SHA в отчётах этого прогона помечен `-dirty`: в рабочем дереве были незакоммиченные правки
  документации и `scripts/doctor.sh` (проверка buildx); код релизного пути совпадал с коммитом `6453a7b`.

## Полный приёмочный прогон `make test-e2e` — 2026-10-15 22:47–22:58 UTC

Команда: `make test-e2e`, код возврата 0, общее время 10 мин 44 с. Сводка — `reports/e2e-summary-20261015T224744Z.md`.

| сценарий | результат | время, с | доказательство |
|---|---|---|---|
| verify | passed | 1 | 14/14 проверок |
| idempotent-up | passed | 20 | отпечатки ключа, SOPS-файла и активного релиза не изменились; `make up: 20 с` |
| release (v2) | passed | 75 | `reports/release-v2-20261015t224820z.md` |
| not-ready | passed | 77 | `reports/release-v3-notready-20261015t224935z.md` |
| not-ready-safe | passed | 1 | активна v2 |
| rollback | passed | 48 | `reports/release-v3-faulty-20261015t225054z.md` (+ `.json`) |
| rollback-safe | passed | 1 | активна v2 |
| interrupted | passed | 25 | `reports/recovery-recover-20261015t225150z.md` |
| no-metrics | passed | 30 | `reports/release-v3-nometrics-20261015t225212z.md` |
| alert | passed | 51 | `reports/alert-demo-20261015t225222z.md` |
| rotation-chain | passed | 52 | `reports/rotation-20261015t225313z.md`; затем откат, токены проверены повторно |
| concurrency | passed | 75 | `reports/release-v4-competing-20261015t225425z.md` (blocked) |
| security | passed | 8 | 17/17 проверок |
| down-up | passed | 179 | `make down` + `make up: 168 с` (образы в кэше Docker) |
| verify-again | passed | 1 | 14/14 |

## Ключевые измерения

| Измерение | Значение | Источник |
|---|---|---|
| Холодный `make up` на чистом runner GitHub | 3 мин 21 с | `github-actions.md` |
| `make up` после `make down` (образы в кэше) | 168 с | лог сценария down-up |
| Повторный `make up` на работающем стенде | 20 с, изменений нет | idempotent-up |
| Релиз с полным CI (`make release`) | 72–80 с, из них стадии CI ≈ 15 с | логи релизов |
| Релиз-контроллер: развёртывание → готовность кандидата | 6–9 с | `durations` отчётов |
| Переключение → новый релиз на ingress | 0,6–0,7 с | `cutover_observed` |
| Окно post-deploy (успешный релиз) | 30 с, 245 запросов, 0 ошибок, p95 ≈ 6 мс | `post_deploy_http` |
| Ошибки прежнего релиза в окне ±2 с вокруг переключения | 0 из 36–37 запросов (в каждом из релизов v2/v4/v3-faulty) | `switch_impact` |
| Обнаружение дефекта после переключения | ранняя остановка через 2,6 с окна (21 запрос, 7 × HTTP 500) | `post_deploy_http` отката |
| Возврат трафика → прежний релиз на ingress | 0,44–0,46 с | `rollback.seconds_to_cutback` |
| Проверка восстановления после отката | 85–88 запросов, 0 ошибок | `rollback.verification` |
| Независимое подтверждение по метрикам после отката | Prometheus: 7 ошибок 5xx из 22 запросов кандидата | `metrics_evidence_after_rollback` |
| Отклонение неготового кандидата | 62 с (progressDeadlineSeconds 60 с) | not-ready |
| Отклонение без метрик | 8 с от старта (Prometheus недоступен) | no-metrics |
| Алерт: сбой → pending → firing → Alertmanager → восстановление → resolved | 0 → 10 с → 41 с → 43 с → 48 с → 51 с | alert-demo |
| Ротация с перекрытием (4 pod, 2 слота) | 2,4 с | rotation |
| Потребление стенда в покое | узел k3d 1,63 ГиБ RAM / ~0,16 vCPU; registry 35 МиБ | `docker stats` |
| Потребление по namespace (working set) | mts-app ≈ 300 МиБ (4 pod), monitoring ≈ 314 МиБ, kube-system ≈ 53 МиБ | cAdvisor через Prometheus |

Числа — один прогон на одной машине, не статистика и не SLA; они показывают порядок величин.

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
