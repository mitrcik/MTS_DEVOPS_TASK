# Отчёт: release `v3-nometrics-20261016t003219z`

**Решение:** `rejected` — metrics_unavailable: Prometheus недоступен — релиз без наблюдаемости запрещён

- Начало: 2026-10-16T00:32:19.128Z
- Переключение: —
- Завершение: 2026-10-16T00:32:28.578Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.5, "candidate_ready": 8.4, "preview_passed": 9.2, "total": 9.4}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:c5b2228daccb62658cda774aeb9d7592afa2093d0582e41e1693805b51ff251e`
- Версия: `v3-nometrics`, Git SHA: `e6bf26c83d03`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | blue | v2 | `sha256:6184f6ebc861` | v2-20261016t002840z |
| candidate | green | v3-nometrics | `sha256:c5b2228daccb` | v3-nometrics-20261016t003219z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 7.8}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-green-744d998c57-p26vs", "mts-api-green-744d998c57-pgmlw"], "probes": [{"pod": "mts-api-green-744d998c57-p26vs", "probe": "healthz", "passed": true}, {"pod": "mts-api-green-744d998c57-p26vs", "probe": "readyz", "passed": true}, {"pod": "mts-api-green-744d998c57-p26vs", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-gree |
| metrics_precheck | **failed** | `{"summary": "Prometheus недоступен — релиз без наблюдаемости запрещён"}` |

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-16T00:32:19.673Z` deploy_started `{"slot": "green"}`
- `2026-10-16T00:32:27.550Z` candidate_ready
- `2026-10-16T00:32:28.346Z` preview_passed `{"probes": 16}`
