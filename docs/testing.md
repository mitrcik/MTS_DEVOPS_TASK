# Тестирование и приёмка

Приоритет — опасные переходы релиза, бизнес-API, безопасность и воспроизводимость, а не число тестов.

## Уровни

| Уровень | Что проверяет | Где | Как запустить |
|---|---|---|---|
| Unit: приложение (26) | расчёт стоимости и округление, валидация (422), 401/404, Ready/не Ready, учебные неисправности детерминированы, перечитывание токенов при ротации, кардинальность меток, отсутствие токена в логах | `app/tests/` | `scripts/ci.sh test` (pytest в образе `target=test`, read-only FS, UID 10001) |
| Unit: gate (17) | нет данных/NaN/пустой вектор/мало трафика/устаревшие серии → провал; доля ошибок, p95, доля трафика кандидата; ранняя остановка; определение момента переключения | `scripts/tests/test_gate.py` | `scripts/ci.sh test` |
| Правила Prometheus (6 групп) | pending→firing→resolved пробы; алерт «нет данных»; доля 5xx с порогом трафика; нулевой трафик не даёт ложного алерта; p95 по histogram | `observability/tests/rules.test.yml` | `scripts/ci.sh validate` (`promtool test rules`) |
| Статические проверки | ruff, yamllint, shellcheck, поиск секретов в Git и Trivy fs, `helm lint --strict` + JSON-схемы (отказ на тег вместо digest), `promtool check config`, `amtool check-config`, проверка дашборда и исключений Trivy | `scripts/ci.sh lint validate` | `make ci` |
| Интеграция / приёмка (15 сценариев) | реальный стенд: см. ниже | `scripts/e2e.sh` | `make test-e2e` |

## Приёмочные сценарии (`make test-e2e`)

| # мастер-промпта | Сценарий | Что считается успехом |
|---|---|---|
| 1 | `verify` | API через ingress, токен из SOPS, 401 без токена, все scrape targets up, проба = 1, правила загружены, Grafana и дашборд provisioned |
| 2 | `idempotent-up` | отпечатки age-ключа, SOPS-источника и активного релиза совпадают до/после повторного `make up` |
| 3 | `release` | решение `promoted`; ingress отдаёт новый release id; gate пройден |
| 4 | `not-ready`, `not-ready-safe` | `rejected` до переключения; активна прежняя версия, `verify` проходит |
| 5 | `rollback`, `rollback-safe` | кандидат Ready и прошёл preview, после переключения 5xx на пользовательском пути → `rolled_back`, восстановление подтверждено; `verify` на прежней версии |
| 6 | `no-metrics` | при остановленном Prometheus релиз `rejected` (metrics_unavailable), Prometheus восстановлен |
| 7 | `alert` | `MtsApiSyntheticProbeFailing`: pending → firing → получен Alertmanager (маршрут) → resolved |
| 8 | `rotation-chain` | новый токен 200, старый 401 в каждом pod обоих слотов и через ingress; затем неудачный релиз → откат → отозванный токен по-прежнему 401 |
| 9 | `security` | 17 проверок `verify-security` |
| 10 | `concurrency` | при идущем релизе конкурирующие `rotate-secret` и релиз завершаются кодом 10 с именем держателя; основной релиз `promoted` |
| — | `interrupted` | SIGTERM контроллеру в фазе `observing`: блокировка освобождена, фаза сохранена; `make recover` возвращает трафик на последний подтверждённый релиз; `verify` проходит |
| 11 | `down-up`, `verify-again` | после `make down` нет контейнеров кластера; `make up` снова поднимает рабочий стенд |
| 12 | удалённый pipeline | push запускает CI/публикацию/E2E (проверено, `docs/validation/github-actions.md`); доставка на постоянный стенд **не проверена** (нет хоста) |

Каждый сценарий пишет лог в `.local/e2e/<run>/<сценарий>.log` и сводку `summary.md`
(время, код, последний отчёт). Отчёты релизов/ротации/алерта — `.local/reports/`.

## Замеры

Время холодного запуска, повторного запуска, релиза и отката измеряется раздельно по отчётам
(`durations.seconds_from_start`) и выводу `make`; монтаж видео в замеры не входит. Фактические
значения — `docs/validation/local-e2e.md` и `docs/validation/github-actions.md`.

## Как воспроизвести на своей машине

```bash
make up && make test-e2e          # ~20–25 минут; E2E_REBUILD=0 — без финального down/up
E2E_ONLY="release rollback" make test-e2e   # только выбранные сценарии
```
