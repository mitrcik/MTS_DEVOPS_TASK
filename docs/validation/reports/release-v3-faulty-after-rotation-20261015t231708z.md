# Отчёт: release `v3-faulty-after-rotation-20261015t231708z`

**Решение:** `rolled_back` — доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах

- Начало: 2026-10-15T23:17:08.421Z
- Переключение: 2026-10-15T23:17:22.353Z
- Завершение: 2026-10-15T23:17:37.031Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 7.5, "preview_passed": 8.2, "metrics_precheck_passed": 11.3, "traffic_switched": 13.9, "cutover_observed": 14.6, "traffic_rolled_back": 17.3, "cutback_observed": 18.3, "total": 28.6}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:8e4bb7fa2deb06dd7a73c1fc9b713d9e9c158e6a823d5d39200d4ce564f0bfd0`
- Версия: `v3-faulty-after-rotation`, Git SHA: `697dc896dfc0`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:a4b55a0e8550` | v2-20261015t231155z |
| candidate | blue | v3-faulty-after-rotation | `sha256:8e4bb7fa2deb` | v3-faulty-after-rotation-20261015t231708z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 6.9}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-blue-57d6fd94b7-dgctv", "mts-api-blue-57d6fd94b7-n494l"], "probes": [{"pod": "mts-api-blue-57d6fd94b7-dgctv", "probe": "healthz", "passed": true}, {"pod": "mts-api-blue-57d6fd94b7-dgctv", "probe": "readyz", "passed": true}, {"pod": "mts-api-blue-57d6fd94b7-dgctv", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-blue-57d6 |
| metrics_precheck | **passed** | `{"summary": "кандидат виден в Prometheus", "targets": {"mts-api-blue-7d84559fb6-hfqqg": 0.0, "mts-api-blue-7d84559fb6-pr5tb": 0.0, "mts-api-blue-b6f6b548c-jhb9m": 1.0, "mts-api-blue-b6f6b548c-fz6k6": 1.0, "mts-api-blue-c657d75c8-8x6qs": 1.0, "mts-api-blue-c657d75c8-8npx8": 1.0, "mts-api-blue-57d6fd94b7-n494l": 1.0, "mts-api-blue-57d6fd94b7-dgctv": 1.0}}` |
| switch_impact | **measured** | `{"requests": 37, "failed": 0, "note": "ошибки прежнего релиза в окне ±2 с вокруг переключения (ошибки кандидата учитывает gate)"}` |
| post_deploy_http | **failed** | `{"passed": false, "reasons": ["доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"], "details": {"requests": 21, "failed": 7, "error_ratio": 0.3333333333333333, "p95_seconds": 0.0064, "served_by_release": {"v3-faulty-after-rotation-20261015t231708z": 21}, "failures_by_status": {"500": 7}, "candidate_share": 1.0, "window_seconds_observed": 2.6}}` |
| metrics_gate | **failed** | `{"passed": false, "reasons": ["не оценивалось: HTTP-gate уже провален"], "details": {}}` |
| metrics_evidence_after_rollback | **recorded** | `{"note": "метрики кандидата за окно наблюдения; на решение не влияют", "available": true, "error": null, "requests": 12.0, "errors": 3.0, "p95_seconds": 0.004749999999999999, "build_info_pods": 2, "targets": [{"pod": "mts-api-blue-7d84559fb6-hfqqg", "up": 0.0, "age_seconds": 129.6}, {"pod": "mts-api-blue-7d84559fb6-pr5tb", "up": 0.0, "age_seconds": 132.4}, {"pod": "mts-api-blue-b6f6b548c-jhb9m",  |

## Возврат трафика

`{"performed": true, "target_slot": "green", "target_release": "v2-20261015t231155z", "seconds_to_cutback": 0.59, "recovery_verified": true, "verification": {"cutback_observed": true, "requests": 88, "failed": 0, "error_ratio": 0.0, "p95_seconds": 0.006, "served_by_release": {"v2-20261015t231155z": 88}, "failures_by_status": {}, "candidate_share": 1.0}}`

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-15T23:17:09.000Z` deploy_started `{"slot": "blue"}`
- `2026-10-15T23:17:15.907Z` candidate_ready
- `2026-10-15T23:17:16.650Z` preview_passed `{"probes": 16}`
- `2026-10-15T23:17:19.723Z` metrics_precheck_passed
- `2026-10-15T23:17:22.353Z` traffic_switched `{"to": "blue", "previous": "green"}`
- `2026-10-15T23:17:22.996Z` cutover_observed `{"seconds_after_switch": 0.52}`
- `2026-10-15T23:17:24.997Z` fail_fast `{"reason": "доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"}`
- `2026-10-15T23:17:25.671Z` traffic_rolled_back `{"to": "green"}`
- `2026-10-15T23:17:26.672Z` cutback_observed `{"seconds_after_rollback": 0.59}`
