# Runbooks

Формат: симптом → проверка → вероятная причина → действия → критерий восстановления.
Все команды выполняются из корня репозитория. `K` ниже — сокращение:

```bash
K="./.local/bin/kubectl --kubeconfig .local/kube/admin.kubeconfig"
```

## MtsApiSyntheticProbeFailing

**Симптом.** Critical-алерт: синтетическая проба `GET /api/v1/tariffs` через Traefik неуспешна дольше 30 с.
Пользователи получают 5xx/503 или не получают ответа.

**Проверка.**
```bash
make status                                   # какой слот активен, сколько реплик готово
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/v1/tariffs
$K -n mts-app get pods -l app.kubernetes.io/name=mts-api -o wide
$K -n mts-app get endpointslices -l kubernetes.io/service-name=mts-api-active
$K -n kube-system logs deploy/traefik --tail=50
```

**Вероятные причины.** У активного слота 0 готовых реплик (масштабирование, OOM, ошибка образа);
селектор `mts-api-active` указывает на слот без pod; Traefik недоступен; NetworkPolicy блокирует Traefik.

**Действия.**
1. Если активный слот масштабирован в 0: `$K -n mts-app scale deploy/mts-api-<slot> --replicas=2`.
2. Если pod падают (`CrashLoopBackOff`) после недавнего релиза — `make status` покажет, пригоден ли
   резервный слот; если он помечен как подтверждённый ранее, выполните релиз его digest
   (`.local/reports/latest-release.json` → `slots.previous.digest`) либо верните селектор:
   `./.local/bin/helm --kubeconfig .local/kube/deploy.kubeconfig -n mts-app upgrade mts-api-traffic charts/traffic --set-string activeSlot=<резервный> --set-string releaseId=manual-$(date +%s)`.
3. Если недоступен Traefik: `$K -n kube-system rollout restart deploy/traefik`.

**Критерий восстановления.** `probe_success == 1` не менее минуты, алерт `resolved` в Alertmanager,
`make verify` — все проверки пройдены.

## MtsApiSyntheticProbeAbsent

**Симптом.** Warning: нет данных `probe_success` минуту — состояние сервиса неизвестно.

**Проверка.** `http://prometheus.localhost:8080/targets` (job `blackbox-api`),
`$K -n monitoring get pods -l app.kubernetes.io/name=blackbox`.

**Причина.** Не работает blackbox exporter или Prometheus не может его опросить.

**Действия.** `$K -n monitoring rollout restart deploy/blackbox`; при ошибке конфигурации —
`make up` (переустановит чарт наблюдаемости).

**Критерий.** Target `blackbox-api` в состоянии `up`, алерт resolved.

## MtsApiHighErrorRate

**Симптом.** Critical: > 5% бизнес-запросов завершаются 5xx (при трафике > 0.2 rps) дольше 30 с.

**Проверка.**
```bash
# в Grafana: дашборд «MTS DevOps — демо-API», панели «Доля 5xx по слотам» и «Бизнес-запросы по маршруту и коду»
curl -s -H 'Host: prometheus.localhost' --data-urlencode \
  'query=sum by (slot,route,status) (rate(http_requests_total{job="mts-api",status=~"5.."}[1m]))' \
  http://127.0.0.1:8080/api/v1/query
$K -n mts-app logs -l app.kubernetes.io/name=mts-api --tail=50 | grep '"level": "ERROR"'
```

**Причина.** Дефект нового релиза, проявляющийся только под пользовательским трафиком (учебный
режим `errors-behind-ingress`), или деградация зависимостей.

**Действия.** Если ошибки начались сразу после релиза, post-deploy gate обычно уже вернул трафик
(`make status` → решение `rolled_back`). Если релиз был продвинут ранее — вернуть трафик на резервный
слот (см. выше) и выпустить исправление через `make release VERSION=…`.

**Критерий.** Доля 5xx < 1% в течение 5 минут, алерт resolved.

## MtsApiHighLatencyP95

**Симптом.** Warning: p95 бизнес-запросов > 500 мс дольше 2 минут.

**Проверка.** Панель «Latency p50/p95/p99» и «CPU pod приложения»; `$K -n mts-app top pods` недоступен
(metrics-server отключён) — используйте панель CPU/RAM.

**Причина.** CPU-лимит (500m) достигнут, «шумный сосед» на узле, рост трафика.

**Действия.** Увеличить `replicas`/`resources` в `charts/app/values.yaml` и выпустить релиз;
проверить нагрузку на узел (`docker stats k3d-mts-devops-server-0`).

**Критерий.** p95 < 250 мс 10 минут.

## MtsApiTargetDown

**Симптом.** Warning: Prometheus не может снять `/metrics` у pod приложения минуту.

**Проверка.** `http://prometheus.localhost:8080/targets`, job `mts-api` — текст ошибки scrape.

**Причина.** Pod завис/перезапускается; NetworkPolicy не пропускает Prometheus (метки pod
`app.kubernetes.io/name=prometheus` в namespace `monitoring`).

**Действия.** Проверить события pod; убедиться, что NetworkPolicy слота содержит правило для Prometheus
(`$K -n mts-app get netpol mts-api-<slot> -o yaml`).

**Критерий.** `up{job="mts-api"} == 1` у всех pod активного слота.

## Релиз завис / прерван

**Симптом.** `make release` прерван (Ctrl+C, обрыв SSH), `make status` показывает фазу `switching`/
`observing`/`rolling_back` или занятую блокировку.

**Действия.** Запустить любой следующий релиз — контроллер обнаружит прерванную операцию, вернёт
трафик на последний подтверждённый релиз и запишет `interrupted`. Блокировка (Lease) истекает сама
через 120 с без продления и затем перехватывается следующим запуском. Удалять Lease вручную нужно
только если вы уверены, что никакой процесс релиза не идёт:
`./.local/bin/kubectl --kubeconfig .local/kube/deploy.kubeconfig -n mts-app delete lease mts-api-change-lock`.

## Параметры для постоянного стенда

Демо-профиль использует короткие окна (`for: 30s`, rate по 1m, окно gate 30 с), чтобы сбой и
восстановление были видны за минуты. Для постоянного стенда рекомендуется: `for: 2m–5m`,
многоокновые burn-rate алерты по SLO (например, 5m/1h и 30m/6h), окно gate 5–10 минут,
`LOAD_RPS` по реальному профилю трафика, внешний получатель в Alertmanager.
