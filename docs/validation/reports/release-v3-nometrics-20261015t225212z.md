# Отчёт: release `v3-nometrics-20261015t225212z`

**Решение:** `rejected` — metrics_unavailable: Prometheus недоступен — релиз без наблюдаемости запрещён

- Начало: 2026-10-15T22:52:12.161Z
- Переключение: —
- Завершение: 2026-10-15T22:52:20.128Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 7.0, "preview_passed": 7.7, "total": 8.0}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:360bdbde426716bf35324e0ad75d2b29a5e6e232d0b58ea2c6d37db50ce250bb`
- Версия: `v3-nometrics`, Git SHA: `6453a7bb47b3-dirty`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:e02d419c28fe` | v2-20261015t224820z |
| candidate | blue | v3-nometrics | `sha256:360bdbde4267` | v3-nometrics-20261015t225212z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 6.4}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-blue-6c677bc57c-5ns8s", "mts-api-blue-6c677bc57c-t97xw"], "probes": [{"pod": "mts-api-blue-6c677bc57c-5ns8s", "probe": "healthz", "passed": true}, {"pod": "mts-api-blue-6c677bc57c-5ns8s", "probe": "readyz", "passed": true}, {"pod": "mts-api-blue-6c677bc57c-5ns8s", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-blue-6c67 |
| metrics_precheck | **failed** | `{"summary": "Prometheus недоступен — релиз без наблюдаемости запрещён"}` |

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-15T22:52:12.723Z` deploy_started `{"slot": "blue"}`
- `2026-10-15T22:52:19.167Z` candidate_ready
- `2026-10-15T22:52:19.900Z` preview_passed `{"probes": 16}`
