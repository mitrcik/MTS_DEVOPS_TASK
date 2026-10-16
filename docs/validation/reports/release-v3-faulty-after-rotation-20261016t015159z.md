# Отчёт: release `v3-faulty-after-rotation-20261016t015159z`

**Решение:** `rolled_back` — доля неуспешных бизнес-запросов 31.8% > 2.0% на 22 запросах

- Начало: 2026-10-16T01:51:59.219Z
- Переключение: 2026-10-16T01:52:11.220Z
- Завершение: 2026-10-16T01:52:26.387Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 8.5, "preview_passed": 9.4, "metrics_precheck_passed": 9.4, "traffic_switched": 12.0, "cutover_observed": 12.6, "traffic_rolled_back": 15.3, "cutback_observed": 16.8, "total": 27.2}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:96962d5c5d066e3eb61d67b0db0b9739b178aed39537f097d4c86b97186f1e9f`
- Версия: `v3-faulty-after-rotation`, Git SHA: `a6703daae18c`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:14475ad6d0a8` | v2-20261016t014642z |
| candidate | blue | v3-faulty-after-rotation | `sha256:96962d5c5d06` | v3-faulty-after-rotation-20261016t015159z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 7.8}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-blue-8655666bd-m6ksd", "mts-api-blue-8655666bd-xgbm8"], "probes": [{"pod": "mts-api-blue-8655666bd-m6ksd", "probe": "healthz", "passed": true}, {"pod": "mts-api-blue-8655666bd-m6ksd", "probe": "readyz", "passed": true}, {"pod": "mts-api-blue-8655666bd-m6ksd", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-blue-8655666bd |
| metrics_precheck | **passed** | `{"summary": "кандидат виден в Prometheus", "targets": {"mts-api-blue-d6cdf994d-lfgcp": 0.0, "mts-api-blue-d6cdf994d-jxrgm": 0.0, "mts-api-blue-5b5b58b948-pffvq": 1.0, "mts-api-blue-5b5b58b948-54xpf": 1.0, "mts-api-blue-56d6dfd84-mt7s5": 1.0, "mts-api-blue-56d6dfd84-9cdbj": 1.0, "mts-api-blue-8655666bd-m6ksd": 1.0, "mts-api-blue-8655666bd-xgbm8": 1.0}}` |
| switch_impact | **measured** | `{"requests": 36, "failed": 0, "note": "ошибки прежнего релиза в окне ±2 с вокруг переключения (ошибки кандидата учитывает gate)"}` |
| post_deploy_http | **failed** | `{"passed": false, "reasons": ["доля неуспешных бизнес-запросов 31.8% > 2.0% на 22 запросах"], "details": {"requests": 22, "failed": 7, "error_ratio": 0.3181818181818182, "p95_seconds": 0.007, "served_by_release": {"v3-faulty-after-rotation-20261016t015159z": 22}, "failures_by_status": {"500": 7}, "candidate_share": 1.0, "window_seconds_observed": 2.7}}` |
| metrics_gate | **failed** | `{"passed": false, "reasons": ["не оценивалось: HTTP-gate уже провален"], "details": {}}` |
| metrics_evidence_after_rollback | **recorded** | `{"note": "метрики кандидата за окно наблюдения; на решение не влияют", "available": true, "error": null, "requests": 27.0, "errors": 6.0, "p95_seconds": 0.00475, "build_info_pods": 2, "targets": [{"pod": "mts-api-blue-d6cdf994d-lfgcp", "up": 0.0, "age_seconds": 137.2}, {"pod": "mts-api-blue-d6cdf994d-jxrgm", "up": 0.0, "age_seconds": 142.4}, {"pod": "mts-api-blue-5b5b58b948-pffvq", "up": 1.0, "ag |

## Возврат трафика

`{"performed": true, "target_slot": "green", "target_release": "v2-20261016t014642z", "seconds_to_cutback": 1.31, "recovery_verified": true, "verification": {"cutback_observed": true, "requests": 86, "failed": 0, "error_ratio": 0.0, "p95_seconds": 0.0065, "served_by_release": {"v2-20261016t014642z": 86}, "failures_by_status": {}, "candidate_share": 1.0}}`

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-16T01:51:59.854Z` deploy_started `{"slot": "blue"}`
- `2026-10-16T01:52:07.702Z` candidate_ready
- `2026-10-16T01:52:08.611Z` preview_passed `{"probes": 16}`
- `2026-10-16T01:52:08.663Z` metrics_precheck_passed
- `2026-10-16T01:52:11.220Z` traffic_switched `{"to": "blue", "previous": "green"}`
- `2026-10-16T01:52:11.855Z` cutover_observed `{"seconds_after_switch": 0.39}`
- `2026-10-16T01:52:13.856Z` fail_fast `{"reason": "доля неуспешных бизнес-запросов 31.8% > 2.0% на 22 запросах"}`
- `2026-10-16T01:52:14.499Z` traffic_rolled_back `{"to": "green"}`
- `2026-10-16T01:52:16.000Z` cutback_observed `{"seconds_after_rollback": 1.31}`
