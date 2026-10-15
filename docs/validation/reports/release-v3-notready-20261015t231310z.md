# Отчёт: release `v3-notready-20261015t231310z`

**Решение:** `rejected` — candidate_not_ready: helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии

- Начало: 2026-10-15T23:13:10.359Z
- Переключение: —
- Завершение: 2026-10-15T23:14:12.759Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.6, "total": 62.4}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:81a7edf77bfc1eaca3fa63cc228eb696926bc743a96fab90b8c7913887247ce4`
- Версия: `v3-notready`, Git SHA: `697dc896dfc0`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:a4b55a0e8550` | v2-20261015t231155z |
| candidate | blue | v3-notready | `sha256:81a7edf77bfc` | v3-notready-20261015t231310z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **failed** | `{"duration_s": 61.5, "summary": "helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии", "helm_error": "amespace… exit 1: level=WARN msg=\"upgrade failed\" name=mts-api-blue error=\"resource Deployment/mts-app/mts-api-blue not ready. status: Failed, message: Progress deadline exceeded\" | Error: UPGRADE FAILED: release mts-api-blue failed, and has been rolled back due to roll |

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-15T23:13:10.941Z` deploy_started `{"slot": "blue"}`
