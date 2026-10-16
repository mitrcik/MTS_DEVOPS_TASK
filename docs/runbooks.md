# Runbooks

Runbook — пошаговая инструкция для дежурного: что делать, когда сработал конкретный алерт.
Каждый раздел построен одинаково: симптом → проверка → вероятная причина → действия → критерий
восстановления.

Приложение развёрнуто по схеме blue-green: два слота, трафик идёт на активный слот, второй слот —
резервный.

Все команды запускаются из корня репозитория. `K` ниже — сокращение для kubectl с admin-kubeconfig:

```bash
K="./.local/bin/kubectl --kubeconfig .local/kube/admin.kubeconfig"
```

## MtsApiSyntheticProbeFailing

**Симптом.** Critical-алерт: синтетическая проба `GET /api/v1/tariffs` через Traefik не проходит
дольше 30 с. Синтетическая проба — запрос, который мониторинг (blackbox exporter) сам регулярно
отправляет в сервис. Пользователи получают 5xx/503 или не получают ответа.

**Проверка.**
```bash
make status                                   # какой слот активен, сколько реплик готово
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/v1/tariffs
$K -n mts-app get pods -l app.kubernetes.io/name=mts-api -o wide
$K -n mts-app get endpointslices -l kubernetes.io/service-name=mts-api-active
$K -n kube-system logs deploy/traefik --tail=50
```

**Вероятные причины.**
- У активного слота 0 готовых реплик (масштабирование, OOM, ошибка образа).
- Селектор `mts-api-active` указывает на слот без pod.
- Traefik недоступен.
- NetworkPolicy блокирует Traefik.

**Действия.**
1. Если активный слот масштабирован в 0:
   `$K -n mts-app scale deploy/mts-api-<slot> --replicas=2`.
2. Если pod падают (`CrashLoopBackOff`) после недавнего релиза, выполните `make status`. Он покажет,
   пригоден ли резервный слот. Если резервный слот помечен как подтверждённый ранее, есть два пути:
   - выполнить релиз его digest (`.local/reports/latest-release.json` → `slots.previous.digest`);
   - вернуть селектор на резервный слот:
     ```bash
     ./.local/bin/helm --kubeconfig .local/kube/deploy.kubeconfig -n mts-app upgrade mts-api-traffic charts/traffic --set-string activeSlot=<резервный> --set-string releaseId=manual-$(date +%s)
     ```
3. Если недоступен Traefik: `$K -n kube-system rollout restart deploy/traefik`.

**Критерий восстановления.** `probe_success == 1` держится не меньше минуты, алерт в Alertmanager
перешёл в `resolved`, `make verify` проходит все проверки.

## MtsApiSyntheticProbeAbsent

**Симптом.** Warning: данных `probe_success` нет уже минуту, поэтому состояние сервиса неизвестно.

**Проверка.** Откройте `http://prometheus.localhost:8080/targets` (job `blackbox-api`) и выполните
`$K -n monitoring get pods -l app.kubernetes.io/name=blackbox`.

**Причина.** Не работает blackbox exporter, или Prometheus не может его опросить.

**Действия.** Перезапустите exporter: `$K -n monitoring rollout restart deploy/blackbox`. Если
ошибка в конфигурации, выполните `make up`: он переустановит чарт наблюдаемости.

**Критерий восстановления.** Target `blackbox-api` в состоянии `up`, алерт в состоянии resolved.

## MtsApiHighErrorRate

**Симптом.** Critical: больше 5% бизнес-запросов завершаются с 5xx дольше 30 с. Алерт срабатывает,
только если трафик больше 0.2 rps.

**Проверка.**
```bash
# в Grafana: дашборд «MTS DevOps — демо-API», панели «Доля 5xx по слотам» и «Бизнес-запросы по маршруту и коду»
curl -s -H 'Host: prometheus.localhost' --data-urlencode \
  'query=sum by (slot,route,status) (rate(http_requests_total{job="mts-api",status=~"5.."}[1m]))' \
  http://127.0.0.1:8080/api/v1/query
$K -n mts-app logs -l app.kubernetes.io/name=mts-api --tail=50 | grep '"level": "ERROR"'
```

**Причина.** Дефект нового релиза, который проявляется только под пользовательским трафиком
(учебный режим `errors-behind-ingress`), или деградация зависимостей.

**Действия.**
- **Ошибки начались сразу после релиза.** Post-deploy gate обычно уже вернул трафик. Gate — это
  проверка HTTP-ответов и метрик после переключения трафика; при ошибках контроллер релизов сам
  делает откат. `make status` покажет решение `rolled_back`.
- **Релиз был продвинут (promoted) раньше.** Верните трафик на резервный слот (см.
  [MtsApiSyntheticProbeFailing](#mtsapisyntheticprobefailing), шаг 2) и выпустите исправление через
  `make release VERSION=…`.

**Критерий восстановления.** Доля 5xx < 1% в течение 5 минут, алерт resolved.

## MtsApiHighLatencyP95

**Симптом.** Warning: p95 (95-й перцентиль времени ответа) бизнес-запросов > 500 мс дольше 2 минут.

**Проверка.** Смотрите панели «Latency p50/p95/p99» и «CPU pod приложения». Команда
`$K -n mts-app top pods` недоступна, потому что metrics-server отключён. Вместо неё используйте
панель CPU/RAM.

**Причина.** Достигнут CPU-лимит (500m), на узле есть «шумный сосед» (другая нагрузка на том же
узле) или вырос трафик.

**Действия.** Увеличьте `replicas`/`resources` в `charts/app/values.yaml` и выпустите релиз.
Проверьте нагрузку на узел: `docker stats k3d-mts-devops-server-0`.

**Критерий восстановления.** p95 < 250 мс в течение 10 минут.

## MtsApiTargetDown

**Симптом.** Warning: Prometheus уже минуту не может снять `/metrics` у pod приложения.

**Проверка.** Откройте `http://prometheus.localhost:8080/targets`, job `mts-api`, и прочитайте текст
ошибки scrape (сбора метрик).

**Причина.** Pod завис или перезапускается. Другой вариант — NetworkPolicy не пропускает Prometheus
(pod с меткой `app.kubernetes.io/name=prometheus` в namespace `monitoring`).

**Действия.** Проверьте события pod. Убедитесь, что NetworkPolicy слота содержит правило для
Prometheus: `$K -n mts-app get netpol mts-api-<slot> -o yaml`.

**Критерий восстановления.** `up{job="mts-api"} == 1` у всех pod активного слота.

## Релиз завис или прерван

**Симптом.** `make release` прерван (Ctrl+C, обрыв SSH). `make status` показывает фазу
`switching`/`observing`/`rolling_back` или занятую блокировку.

**Действия.** Запустите любой следующий релиз. Контроллер обнаружит прерванную операцию, вернёт
трафик на последний подтверждённый релиз и запишет `interrupted`.

Блокировка — это объект Kubernetes Lease. Если её не продлевают, она истекает сама через 120 с, и
следующий запуск её перехватывает. Удаляйте Lease вручную, только если уверены, что ни один процесс
релиза не идёт:

```bash
./.local/bin/kubectl --kubeconfig .local/kube/deploy.kubeconfig -n mts-app delete lease mts-api-change-lock
```

## Параметры для постоянного стенда

Демо-профиль использует короткие окна: `for: 30s`, rate по 1m, окно gate 30 с. Так сбой и
восстановление видны за минуты. Для постоянного стенда рекомендуется:

- `for: 2m–5m`;
- burn-rate алерты по SLO с несколькими окнами (например, 5m/1h и 30m/6h) — они срабатывают по
  скорости расхода бюджета ошибок;
- окно gate 5–10 минут;
- `LOAD_RPS` по реальному профилю трафика;
- внешний получатель в Alertmanager.
