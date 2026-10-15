# Отчёт: release `v3-faulty-20261015t231429z`

**Решение:** `rolled_back` — доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах

- Начало: 2026-10-15T23:14:29.799Z
- Переключение: 2026-10-15T23:14:49.873Z
- Завершение: 2026-10-15T23:15:04.051Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 7.6, "preview_passed": 8.3, "metrics_precheck_passed": 17.4, "traffic_switched": 20.1, "cutover_observed": 20.7, "traffic_rolled_back": 23.4, "cutback_observed": 23.9, "total": 34.3}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:fa8b0e89cd95db1116b86db5b8602701381f1b570872eb75c40c51a7fbdaac52`
- Версия: `v3-faulty`, Git SHA: `697dc896dfc0`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:a4b55a0e8550` | v2-20261015t231155z |
| candidate | blue | v3-faulty | `sha256:fa8b0e89cd95` | v3-faulty-20261015t231429z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 6.9}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-blue-7d84559fb6-hfqqg", "mts-api-blue-7d84559fb6-pr5tb"], "probes": [{"pod": "mts-api-blue-7d84559fb6-hfqqg", "probe": "healthz", "passed": true}, {"pod": "mts-api-blue-7d84559fb6-hfqqg", "probe": "readyz", "passed": true}, {"pod": "mts-api-blue-7d84559fb6-hfqqg", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-blue-7d84 |
| metrics_precheck | **passed** | `{"summary": "кандидат виден в Prometheus", "targets": {"mts-api-blue-6bfdddcb69-pp9ww": 1.0, "mts-api-blue-6bfdddcb69-mg8rx": 1.0, "mts-api-blue-7d84559fb6-hfqqg": 1.0, "mts-api-blue-7d84559fb6-pr5tb": 1.0}}` |
| switch_impact | **measured** | `{"requests": 37, "failed": 0, "note": "ошибки прежнего релиза в окне ±2 с вокруг переключения (ошибки кандидата учитывает gate)"}` |
| post_deploy_http | **failed** | `{"passed": false, "reasons": ["доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"], "details": {"requests": 21, "failed": 7, "error_ratio": 0.3333333333333333, "p95_seconds": 0.0062, "served_by_release": {"v3-faulty-20261015t231429z": 21}, "failures_by_status": {"500": 7}, "candidate_share": 1.0, "window_seconds_observed": 2.6}}` |
| metrics_gate | **failed** | `{"passed": false, "reasons": ["не оценивалось: HTTP-gate уже провален"], "details": {}}` |
| metrics_evidence_after_rollback | **recorded** | `{"note": "метрики кандидата за окно наблюдения; на решение не влияют", "available": true, "error": null, "requests": 5.6, "errors": 1.4, "p95_seconds": 0.00475, "build_info_pods": 2, "targets": [{"pod": "mts-api-blue-7d84559fb6-hfqqg", "up": 1.0, "age_seconds": 1.6}, {"pod": "mts-api-blue-7d84559fb6-pr5tb", "up": 1.0, "age_seconds": 4.4}], "range_seconds": 14}` |

## Возврат трафика

`{"performed": true, "target_slot": "green", "target_release": "v2-20261015t231155z", "seconds_to_cutback": 0.47, "recovery_verified": true, "verification": {"cutback_observed": true, "requests": 85, "failed": 0, "error_ratio": 0.0, "p95_seconds": 0.007, "served_by_release": {"v2-20261015t231155z": 85}, "failures_by_status": {}, "candidate_share": 1.0}}`

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-15T23:14:30.399Z` deploy_started `{"slot": "blue"}`
- `2026-10-15T23:14:37.354Z` candidate_ready
- `2026-10-15T23:14:38.112Z` preview_passed `{"probes": 16}`
- `2026-10-15T23:14:47.245Z` metrics_precheck_passed
- `2026-10-15T23:14:49.873Z` traffic_switched `{"to": "blue", "previous": "green"}`
- `2026-10-15T23:14:50.522Z` cutover_observed `{"seconds_after_switch": 0.5}`
- `2026-10-15T23:14:52.523Z` fail_fast `{"reason": "доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"}`
- `2026-10-15T23:14:53.158Z` traffic_rolled_back `{"to": "green"}`
- `2026-10-15T23:14:53.659Z` cutback_observed `{"seconds_after_rollback": 0.47}`
