# Отчёт: release `v3-nometrics-20261016t015031z`

**Решение:** `rejected` — metrics_unavailable: Prometheus недоступен — релиз без наблюдаемости запрещён

- Начало: 2026-10-16T01:50:31.488Z
- Переключение: —
- Завершение: 2026-10-16T01:50:39.897Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 7.4, "preview_passed": 8.2, "total": 8.4}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:02c628af7f3520e7d2aefe3b3cd0b0d61c26a42700b533ef8eb50aeb6c7a7c23`
- Версия: `v3-nometrics`, Git SHA: `a6703daae18c`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:14475ad6d0a8` | v2-20261016t014642z |
| candidate | blue | v3-nometrics | `sha256:02c628af7f35` | v3-nometrics-20261016t015031z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 6.7}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-blue-56d6dfd84-9cdbj", "mts-api-blue-56d6dfd84-mt7s5"], "probes": [{"pod": "mts-api-blue-56d6dfd84-9cdbj", "probe": "healthz", "passed": true}, {"pod": "mts-api-blue-56d6dfd84-9cdbj", "probe": "readyz", "passed": true}, {"pod": "mts-api-blue-56d6dfd84-9cdbj", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-blue-56d6dfd84 |
| metrics_precheck | **failed** | `{"summary": "Prometheus недоступен — релиз без наблюдаемости запрещён"}` |

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-16T01:50:32.082Z` deploy_started `{"slot": "blue"}`
- `2026-10-16T01:50:38.862Z` candidate_ready
- `2026-10-16T01:50:39.674Z` preview_passed `{"probes": 16}`
