# Отчёт: release `v3-faulty-20261016t003110z`

**Решение:** `rolled_back` — доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах

- Начало: 2026-10-16T00:31:10.487Z
- Переключение: 2026-10-16T00:31:23.594Z
- Завершение: 2026-10-16T00:31:38.110Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.5, "candidate_ready": 6.8, "preview_passed": 7.5, "metrics_precheck_passed": 10.6, "traffic_switched": 13.1, "cutover_observed": 13.7, "traffic_rolled_back": 16.2, "cutback_observed": 17.2, "total": 27.6}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:f275ddca82397e4c10eb51fe53d611293479dd35aad327ad17b7bb6a5c973aea`
- Версия: `v3-faulty`, Git SHA: `e6bf26c83d03`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | blue | v2 | `sha256:6184f6ebc861` | v2-20261016t002840z |
| candidate | green | v3-faulty | `sha256:f275ddca8239` | v3-faulty-20261016t003110z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 6.2}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-green-5964d8bfbd-jw79p", "mts-api-green-5964d8bfbd-qwrrt"], "probes": [{"pod": "mts-api-green-5964d8bfbd-jw79p", "probe": "healthz", "passed": true}, {"pod": "mts-api-green-5964d8bfbd-jw79p", "probe": "readyz", "passed": true}, {"pod": "mts-api-green-5964d8bfbd-jw79p", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-gree |
| metrics_precheck | **passed** | `{"summary": "кандидат виден в Prometheus", "targets": {"mts-api-green-77dd84d4d9-75lrt": 1.0, "mts-api-green-77dd84d4d9-qjzfc": 1.0, "mts-api-green-77dd84d4d9-wk558": 1.0, "mts-api-green-77dd84d4d9-mk464": 1.0, "mts-api-green-5964d8bfbd-jw79p": 1.0, "mts-api-green-5964d8bfbd-qwrrt": 1.0}}` |
| switch_impact | **measured** | `{"requests": 36, "failed": 0, "note": "ошибки прежнего релиза в окне ±2 с вокруг переключения (ошибки кандидата учитывает gate)"}` |
| post_deploy_http | **failed** | `{"passed": false, "reasons": ["доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"], "details": {"requests": 21, "failed": 7, "error_ratio": 0.3333333333333333, "p95_seconds": 0.0063, "served_by_release": {"v3-faulty-20261016t003110z": 21}, "failures_by_status": {"500": 7}, "candidate_share": 1.0, "window_seconds_observed": 2.6}}` |
| metrics_gate | **failed** | `{"passed": false, "reasons": ["не оценивалось: HTTP-gate уже провален"], "details": {}}` |
| metrics_evidence_after_rollback | **recorded** | `{"note": "метрики кандидата за окно наблюдения; на решение не влияют", "available": true, "error": null, "requests": 27.0, "errors": 7.5, "p95_seconds": 0.00475, "build_info_pods": 2, "targets": [{"pod": "mts-api-green-5964d8bfbd-jw79p", "up": 1.0, "age_seconds": 3.0}, {"pod": "mts-api-green-5964d8bfbd-qwrrt", "up": 1.0, "age_seconds": 3.3}], "range_seconds": 15}` |

## Возврат трафика

`{"performed": true, "target_slot": "blue", "target_release": "v2-20261016t002840z", "seconds_to_cutback": 0.4, "recovery_verified": true, "verification": {"cutback_observed": true, "requests": 88, "failed": 0, "error_ratio": 0.0, "p95_seconds": 0.0056, "served_by_release": {"v2-20261016t002840z": 88}, "failures_by_status": {}, "candidate_share": 1.0}}`

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-16T00:31:11.031Z` deploy_started `{"slot": "green"}`
- `2026-10-16T00:31:17.316Z` candidate_ready
- `2026-10-16T00:31:17.998Z` preview_passed `{"probes": 16}`
- `2026-10-16T00:31:21.071Z` metrics_precheck_passed
- `2026-10-16T00:31:23.594Z` traffic_switched `{"to": "green", "previous": "blue"}`
- `2026-10-16T00:31:24.208Z` cutover_observed `{"seconds_after_switch": 0.4}`
- `2026-10-16T00:31:26.209Z` fail_fast `{"reason": "доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"}`
- `2026-10-16T00:31:26.716Z` traffic_rolled_back `{"to": "blue"}`
- `2026-10-16T00:31:27.716Z` cutback_observed `{"seconds_after_rollback": 0.4}`
