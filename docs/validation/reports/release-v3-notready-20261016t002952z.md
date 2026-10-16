# Отчёт: release `v3-notready-20261016t002952z`

**Решение:** `rejected` — candidate_not_ready: helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии

- Начало: 2026-10-16T00:29:52.268Z
- Переключение: —
- Завершение: 2026-10-16T00:30:54.516Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.5, "total": 62.2}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:c2000513a9cd3cc8e5cb96f10de7c81f4e67ca9a82a64f9bed8a63b6619e3367`
- Версия: `v3-notready`, Git SHA: `e6bf26c83d03`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | blue | v2 | `sha256:6184f6ebc861` | v2-20261016t002840z |
| candidate | green | v3-notready | `sha256:c2000513a9cd` | v3-notready-20261016t002952z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **failed** | `{"duration_s": 61.5, "summary": "helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии", "helm_error": "pace… exit 1: level=WARN msg=\"upgrade failed\" name=mts-api-green error=\"resource Deployment/mts-app/mts-api-green not ready. status: Failed, message: Progress deadline exceeded\" | Error: UPGRADE FAILED: release mts-api-green failed, and has been rolled back due to rollb |

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-16T00:29:52.801Z` deploy_started `{"slot": "green"}`
