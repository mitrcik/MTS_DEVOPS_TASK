# Отчёт: release `v3-faulty-20261016t014916z`

**Решение:** `rolled_back` — доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах

- Начало: 2026-10-16T01:49:16.915Z
- Переключение: 2026-10-16T01:49:34.147Z
- Завершение: 2026-10-16T01:49:48.369Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 7.6, "preview_passed": 8.5, "metrics_precheck_passed": 14.6, "traffic_switched": 17.2, "cutover_observed": 17.9, "traffic_rolled_back": 20.5, "cutback_observed": 21.0, "total": 31.5}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:2d8f386e9d2552144945ab8d6ef369eb4719c81106e617e2d9fd93c18b93639f`
- Версия: `v3-faulty`, Git SHA: `a6703daae18c`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:14475ad6d0a8` | v2-20261016t014642z |
| candidate | blue | v3-faulty | `sha256:2d8f386e9d25` | v3-faulty-20261016t014916z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 6.9}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-blue-d6cdf994d-jxrgm", "mts-api-blue-d6cdf994d-lfgcp"], "probes": [{"pod": "mts-api-blue-d6cdf994d-jxrgm", "probe": "healthz", "passed": true}, {"pod": "mts-api-blue-d6cdf994d-jxrgm", "probe": "readyz", "passed": true}, {"pod": "mts-api-blue-d6cdf994d-jxrgm", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-blue-d6cdf994d |
| metrics_precheck | **passed** | `{"summary": "кандидат виден в Prometheus", "targets": {"mts-api-blue-5584866b4b-pk46l": 1.0, "mts-api-blue-5584866b4b-696h6": 0.0, "mts-api-blue-d6cdf994d-lfgcp": 1.0, "mts-api-blue-d6cdf994d-jxrgm": 1.0}}` |
| switch_impact | **measured** | `{"requests": 36, "failed": 0, "note": "ошибки прежнего релиза в окне ±2 с вокруг переключения (ошибки кандидата учитывает gate)"}` |
| post_deploy_http | **failed** | `{"passed": false, "reasons": ["доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"], "details": {"requests": 21, "failed": 7, "error_ratio": 0.3333333333333333, "p95_seconds": 0.0067, "served_by_release": {"v3-faulty-20261016t014916z": 21}, "failures_by_status": {"500": 7}, "candidate_share": 1.0, "window_seconds_observed": 2.6}}` |
| metrics_gate | **failed** | `{"passed": false, "reasons": ["не оценивалось: HTTP-gate уже провален"], "details": {}}` |
| metrics_evidence_after_rollback | **recorded** | `{"note": "метрики кандидата за окно наблюдения; на решение не влияют", "available": true, "error": null, "requests": 0.0, "errors": 0.0, "p95_seconds": null, "build_info_pods": 2, "targets": [{"pod": "mts-api-blue-d6cdf994d-lfgcp", "up": 1.0, "age_seconds": 4.2}, {"pod": "mts-api-blue-d6cdf994d-jxrgm", "up": 1.0, "age_seconds": 4.3}], "range_seconds": 14}` |

## Возврат трафика

`{"performed": true, "target_slot": "green", "target_release": "v2-20261016t014642z", "seconds_to_cutback": 0.53, "recovery_verified": true, "verification": {"cutback_observed": true, "requests": 85, "failed": 0, "error_ratio": 0.0, "p95_seconds": 0.0064, "served_by_release": {"v2-20261016t014642z": 85}, "failures_by_status": {}, "candidate_share": 1.0}}`

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-16T01:49:17.516Z` deploy_started `{"slot": "blue"}`
- `2026-10-16T01:49:24.495Z` candidate_ready
- `2026-10-16T01:49:25.399Z` preview_passed `{"probes": 16}`
- `2026-10-16T01:49:31.531Z` metrics_precheck_passed
- `2026-10-16T01:49:34.147Z` traffic_switched `{"to": "blue", "previous": "green"}`
- `2026-10-16T01:49:34.774Z` cutover_observed `{"seconds_after_switch": 0.52}`
- `2026-10-16T01:49:36.775Z` fail_fast `{"reason": "доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"}`
- `2026-10-16T01:49:37.440Z` traffic_rolled_back `{"to": "green"}`
- `2026-10-16T01:49:37.941Z` cutback_observed `{"seconds_after_rollback": 0.53}`
