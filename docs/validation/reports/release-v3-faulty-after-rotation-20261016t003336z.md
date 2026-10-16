# Отчёт: release `v3-faulty-after-rotation-20261016t003336z`

**Решение:** `rolled_back` — доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах

- Начало: 2026-10-16T00:33:36.317Z
- Переключение: 2026-10-16T00:33:53.183Z
- Завершение: 2026-10-16T00:34:07.630Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 7.5, "preview_passed": 8.3, "metrics_precheck_passed": 14.4, "traffic_switched": 16.9, "cutover_observed": 17.5, "traffic_rolled_back": 20.0, "cutback_observed": 21.0, "total": 31.3}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:855e0d8a2bae8468cbebbcc08ad29e975ff6c49752223ad7039064fc68b37ce8`
- Версия: `v3-faulty-after-rotation`, Git SHA: `e6bf26c83d03`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | blue | v2 | `sha256:6184f6ebc861` | v2-20261016t002840z |
| candidate | green | v3-faulty-after-rotation | `sha256:855e0d8a2bae` | v3-faulty-after-rotation-20261016t003336z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 6.8}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-green-665cd9c9bf-48bl5", "mts-api-green-665cd9c9bf-svfq6"], "probes": [{"pod": "mts-api-green-665cd9c9bf-48bl5", "probe": "healthz", "passed": true}, {"pod": "mts-api-green-665cd9c9bf-48bl5", "probe": "readyz", "passed": true}, {"pod": "mts-api-green-665cd9c9bf-48bl5", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-gree |
| metrics_precheck | **passed** | `{"summary": "кандидат виден в Prometheus", "targets": {"mts-api-green-5964d8bfbd-jw79p": 0.0, "mts-api-green-5964d8bfbd-qwrrt": 0.0, "mts-api-green-6c694789b9-8lx7f": 1.0, "mts-api-green-6c694789b9-slwml": 1.0, "mts-api-green-744d998c57-p26vs": 1.0, "mts-api-green-744d998c57-pgmlw": 1.0, "mts-api-green-665cd9c9bf-48bl5": 1.0, "mts-api-green-665cd9c9bf-svfq6": 1.0}}` |
| switch_impact | **measured** | `{"requests": 36, "failed": 0, "note": "ошибки прежнего релиза в окне ±2 с вокруг переключения (ошибки кандидата учитывает gate)"}` |
| post_deploy_http | **failed** | `{"passed": false, "reasons": ["доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"], "details": {"requests": 21, "failed": 7, "error_ratio": 0.3333333333333333, "p95_seconds": 0.0065, "served_by_release": {"v3-faulty-after-rotation-20261016t003336z": 21}, "failures_by_status": {"500": 7}, "candidate_share": 1.0, "window_seconds_observed": 2.6}}` |
| metrics_gate | **failed** | `{"passed": false, "reasons": ["не оценивалось: HTTP-gate уже провален"], "details": {}}` |
| metrics_evidence_after_rollback | **recorded** | `{"note": "метрики кандидата за окно наблюдения; на решение не влияют", "available": true, "error": null, "requests": 16.5, "errors": 3.0, "p95_seconds": 0.00475, "build_info_pods": 2, "targets": [{"pod": "mts-api-green-5964d8bfbd-jw79p", "up": 0.0, "age_seconds": 132.6}, {"pod": "mts-api-green-5964d8bfbd-qwrrt", "up": 0.0, "age_seconds": 127.9}, {"pod": "mts-api-green-6c694789b9-8lx7f", "up": 1.0 |

## Возврат трафика

`{"performed": true, "target_slot": "blue", "target_release": "v2-20261016t002840z", "seconds_to_cutback": 0.4, "recovery_verified": true, "verification": {"cutback_observed": true, "requests": 88, "failed": 0, "error_ratio": 0.0, "p95_seconds": 0.0059, "served_by_release": {"v2-20261016t002840z": 88}, "failures_by_status": {}, "candidate_share": 1.0}}`

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-16T00:33:36.898Z` deploy_started `{"slot": "green"}`
- `2026-10-16T00:33:43.788Z` candidate_ready
- `2026-10-16T00:33:44.572Z` preview_passed `{"probes": 16}`
- `2026-10-16T00:33:50.679Z` metrics_precheck_passed
- `2026-10-16T00:33:53.183Z` traffic_switched `{"to": "green", "previous": "blue"}`
- `2026-10-16T00:33:53.823Z` cutover_observed `{"seconds_after_switch": 0.42}`
- `2026-10-16T00:33:55.823Z` fail_fast `{"reason": "доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"}`
- `2026-10-16T00:33:56.307Z` traffic_rolled_back `{"to": "blue"}`
- `2026-10-16T00:33:57.307Z` cutback_observed `{"seconds_after_rollback": 0.4}`
