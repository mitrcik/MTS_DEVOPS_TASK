# Отчёт: release `v3-faulty-20261015t225054z`

**Решение:** `rolled_back` — доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах

- Начало: 2026-10-15T22:50:54.331Z
- Переключение: 2026-10-15T22:51:12.481Z
- Завершение: 2026-10-15T22:51:26.607Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "candidate_ready": 8.7, "preview_passed": 9.5, "metrics_precheck_passed": 15.6, "traffic_switched": 18.2, "cutover_observed": 18.8, "traffic_rolled_back": 21.4, "cutback_observed": 21.9, "total": 32.3}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:892af913c41539692426bee7e240963c65e357fe5302dc91a46d7228092676cf`
- Версия: `v3-faulty`, Git SHA: `6453a7bb47b3-dirty`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:e02d419c28fe` | v2-20261015t224820z |
| candidate | blue | v3-faulty | `sha256:892af913c415` | v3-faulty-20261015t225054z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **passed** | `{"duration_s": 8.0}` |
| preview | **passed** | `{"summary": "16/16 проверок прошли", "pods": ["mts-api-blue-8c8bd4d89-76rqp", "mts-api-blue-8c8bd4d89-w9fmm"], "probes": [{"pod": "mts-api-blue-8c8bd4d89-76rqp", "probe": "healthz", "passed": true}, {"pod": "mts-api-blue-8c8bd4d89-76rqp", "probe": "readyz", "passed": true}, {"pod": "mts-api-blue-8c8bd4d89-76rqp", "probe": "version_matches_release", "passed": true}, {"pod": "mts-api-blue-8c8bd4d89 |
| metrics_precheck | **passed** | `{"summary": "кандидат виден в Prometheus", "targets": {"mts-api-blue-bcc666b55-gf8rf": 1.0, "mts-api-blue-bcc666b55-94cr2": 1.0, "mts-api-blue-8c8bd4d89-76rqp": 1.0, "mts-api-blue-8c8bd4d89-w9fmm": 1.0}}` |
| switch_impact | **measured** | `{"requests": 37, "failed": 0, "note": "ошибки прежнего релиза в окне ±2 с вокруг переключения (ошибки кандидата учитывает gate)"}` |
| post_deploy_http | **failed** | `{"passed": false, "reasons": ["доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"], "details": {"requests": 21, "failed": 7, "error_ratio": 0.3333333333333333, "p95_seconds": 0.0061, "served_by_release": {"v3-faulty-20261015t225054z": 21}, "failures_by_status": {"500": 7}, "candidate_share": 1.0, "window_seconds_observed": 2.5}}` |
| metrics_gate | **failed** | `{"passed": false, "reasons": ["не оценивалось: HTTP-gate уже провален"], "details": {}}` |
| metrics_evidence_after_rollback | **recorded** | `{"note": "метрики кандидата за окно наблюдения; на решение не влияют", "available": true, "error": null, "requests": 22.4, "errors": 6.999999999999999, "p95_seconds": 0.00475, "build_info_pods": 2, "targets": [{"pod": "mts-api-blue-8c8bd4d89-76rqp", "up": 1.0, "age_seconds": 2.7}, {"pod": "mts-api-blue-8c8bd4d89-w9fmm", "up": 1.0, "age_seconds": 2.4}], "range_seconds": 14}` |

## Возврат трафика

`{"performed": true, "target_slot": "green", "target_release": "v2-20261015t224820z", "seconds_to_cutback": 0.44, "recovery_verified": true, "verification": {"cutback_observed": true, "requests": 85, "failed": 0, "error_ratio": 0.0, "p95_seconds": 0.0062, "served_by_release": {"v2-20261015t224820z": 85}, "failures_by_status": {}, "candidate_share": 1.0}}`

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-15T22:50:54.929Z` deploy_started `{"slot": "blue"}`
- `2026-10-15T22:51:02.991Z` candidate_ready
- `2026-10-15T22:51:03.802Z` preview_passed `{"probes": 16}`
- `2026-10-15T22:51:09.902Z` metrics_precheck_passed
- `2026-10-15T22:51:12.481Z` traffic_switched `{"to": "blue", "previous": "green"}`
- `2026-10-15T22:51:13.108Z` cutover_observed `{"seconds_after_switch": 0.51}`
- `2026-10-15T22:51:15.108Z` fail_fast `{"reason": "доля неуспешных бизнес-запросов 33.3% > 2.0% на 21 запросах"}`
- `2026-10-15T22:51:15.723Z` traffic_rolled_back `{"to": "green"}`
- `2026-10-15T22:51:16.223Z` cutback_observed `{"seconds_after_rollback": 0.44}`
