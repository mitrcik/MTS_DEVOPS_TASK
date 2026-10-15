# Отчёт: release `v3-nometrics-20261015t231548z`

**Решение:** `rejected` — metrics_unavailable: Prometheus недоступен — релиз без наблюдаемости запрещён

- Начало: 2026-10-15T23:15:48.752Z
- Переключение: —
- Завершение: 2026-10-15T23:15:56.642Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 6.9, "preview_passed": 7.7, "total": 7.9}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:f71f729b2696176c2253c8f8923768d1b6c667751da373850a206dc203c01ba7`
- Версия: `v3-nometrics`, Git SHA: `697dc896dfc0`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:a4b55a0e8550` | v2-20261015t231155z |
| candidate | blue | v3-nometrics | `sha256:f71f729b2696` | v3-nometrics-20261015t231548z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 6.2}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-blue-c657d75c8-8npx8", "mts-api-blue-c657d75c8-8x6qs"], "probes": [{"pod": "mts-api-blue-c657d75c8-8npx8", "probe": "healthz", "passed": true}, {"pod": "mts-api-blue-c657d75c8-8npx8", "probe": "readyz", "passed": true}, {"pod": "mts-api-blue-c657d75c8-8npx8", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-blue-c657d75c8 |
| metrics_precheck | **failed** | `{"summary": "Prometheus недоступен — релиз без наблюдаемости запрещён"}` |

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-15T23:15:49.352Z` deploy_started `{"slot": "blue"}`
- `2026-10-15T23:15:55.630Z` candidate_ready
- `2026-10-15T23:15:56.428Z` preview_passed `{"probes": 16}`
