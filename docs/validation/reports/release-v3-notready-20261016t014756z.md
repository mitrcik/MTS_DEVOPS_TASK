# Отчёт: release `v3-notready-20261016t014756z`

**Решение:** `rejected` — candidate_not_ready: helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии

- Начало: 2026-10-16T01:47:56.342Z
- Переключение: —
- Завершение: 2026-10-16T01:48:58.556Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.7, "total": 62.2}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:0ce1bfc6d8d84fdcdbf2618a3a1ea5120086d99b2ad526e2490c03ff02f040a0`
- Версия: `v3-notready`, Git SHA: `a6703daae18c`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:14475ad6d0a8` | v2-20261016t014642z |
| candidate | blue | v3-notready | `sha256:0ce1bfc6d8d8` | v3-notready-20261016t014756z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **failed** | `{"duration_s": 61.3, "summary": "helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии", "helm_error": "amespace… exit 1: level=WARN msg=\"upgrade failed\" name=mts-api-blue error=\"resource Deployment/mts-app/mts-api-blue not ready. status: Failed, message: Progress deadline exceeded\" | Error: UPGRADE FAILED: release mts-api-blue failed, and has been rolled back due to roll |

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-16T01:47:57.021Z` deploy_started `{"slot": "blue"}`
