# Отчёт: release `v3-notready-20261015t224935z`

**Решение:** `rejected` — candidate_not_ready: helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии

- Начало: 2026-10-15T22:49:35.098Z
- Переключение: —
- Завершение: 2026-10-15T22:50:37.583Z
- Длительности, с: `{"seconds_from_start": {"deploy_started": 0.5, "total": 62.5}}`

## Артефакт

- Образ: `localhost:5001/mts-api@sha256:94262a4b831c9aba36d6ecd2a9b3fd6f04db381335f61d2e18e8d689275878f6`
- Версия: `v3-notready`, Git SHA: `6453a7bb47b3`
- CI: `{"lint": "passed", "test": "passed", "validate": "passed", "build": "passed", "scan": "passed", "push": "passed"}`; Trivy 0.75.0 (DB 2, обновлена 2026-10-15T19:09:25.631494278Z): passed

## Слоты

| роль | слот | версия | digest | release id |
|---|---|---|---|---|
| previous | green | v2 | `sha256:e02d419c28fe` | v2-20261015t224820z |
| candidate | blue | v3-notready | `sha256:94262a4b831c` | v3-notready-20261015t224935z |

## Проверки

| проверка | статус | детали |
|---|---|---|
| candidate_ready | **failed** | `{"duration_s": 61.7, "summary": "helm --wait не дождался готовности; Helm откатил слот к предыдущей ревизии", "helm_error": "amespace… exit 1: level=WARN msg=\"upgrade failed\" name=mts-api-blue error=\"resource Deployment/mts-app/mts-api-blue not ready. status: Failed, message: Progress deadline exceeded\" | Error: UPGRADE FAILED: release mts-api-blue failed, and has been rolled back due to roll |

Инструменты: `{"kubectl": "v1.36.5", "helm": "v4.3.0+gbec5b06", "k3s_server": "v1.36.5+k3s1"}`

## Хронология

- `2026-10-15T22:49:35.633Z` deploy_started `{"slot": "blue"}`
