# Устранение неполадок

При любой проблеме сначала выполните `make doctor`. Команда ничего не меняет. Она проверяет ОС,
Docker, ресурсы, порты, конфликтующие объекты и доступ к источникам загрузок.

## Docker

| Симптом | Причина | Решение |
|---|---|---|
| `permission denied while trying to connect to the Docker daemon socket` | Пользователь не в группе `docker` | `sudo usermod -aG docker $USER`, затем перелогиньтесь. Учтите: членство в группе `docker` равносильно root-доступу к хосту |
| `Cannot connect to the Docker daemon` | Демон не запущен или Docker не установлен | `make prereqs` или `sudo systemctl enable --now docker` |
| `toomanyrequests` / HTTP 429 при загрузке образов | Анонимный лимит Docker Hub для IP | Выполните `docker login` или настройте зеркало. Для Docker на хосте: в `/etc/docker/daemon.json` укажите `{"registry-mirrors":["https://mirror.gcr.io"]}`, затем `sudo systemctl restart docker`. Для узлов k3s: `DOCKERHUB_MIRROR=https://mirror.gcr.io` в `.env`, затем `make down && make up` |
| `x509: certificate signed by unknown authority` при сборке/загрузке | Корпоративный TLS-прокси | Задайте в `.env` `EXTRA_CA_BUNDLE=/путь/к/полному/ca-bundle.crt` (системные CA и CA прокси). Файл передаётся в сборку как BuildKit secret и монтируется в узел k3s |
| `no space left on device` | Мало места для образов | Освободите место. Можно выполнить `docker system prune`, но осторожно: команда удалит неиспользуемые образы всех проектов. Проекту нужно ≈ 10 ГБ (после полного прогона измерено ≈ 9 ГБ). `make doctor` предупреждает, если для Docker свободно < 10 ГБ |

## Окружение и перезагрузка

| Симптом | Решение |
|---|---|
| `ERROR: Ansible could not initialize the preferred locale: unsupported locale setting` | SSH передал локаль, которой нет в ВМ (например, `LANG=ru_RU.UTF-8`). Скрипты проекта и `make` сами задают `LC_ALL=C.UTF-8`. Если запускаете `ansible-playbook` вручную, сначала выполните `export LC_ALL=C.UTF-8` |
| `make status`/`make verify` сразу после перезагрузки: «кластер или инструмент недоступен» | k3s стартует через 1–2 минуты после Docker. Контейнеры стенда поднимаются сами (`restart: unless-stopped`). Повторите команду через минуту. Если не помогло — `make up` |
| `git не читает …` в `make doctor` | `make` запущен через `sudo` или не владельцем клона, либо проект скачан архивом без `.git`. Запускайте `make` от пользователя, который выполнил `git clone` |

## Порты

| Симптом | Решение |
|---|---|
| `doctor`: порт `127.0.0.1:8080`/`6550`/`5001` занят другим процессом | Найдите процесс: `ss -ltnp \| grep 8080`. Или задайте другие `INGRESS_PORT`/`API_PORT`/`REGISTRY_PORT` в `.env` и выполните `make down && make up` |
| `http://grafana.localhost:8080` не открывается | Браузер или резолвер не знает имена `*.localhost`. Используйте `curl -H 'Host: grafana.localhost' http://127.0.0.1:8080/` или добавьте в `/etc/hosts` строку `127.0.0.1 grafana.localhost prometheus.localhost alertmanager.localhost`. Обычно это не нужно: Chrome/Firefox и systemd-resolved резолвят `*.localhost` сами |

## Загрузка инструментов

| Симптом | Решение |
|---|---|
| `Checksum mismatch` в роли `tools` | Файл скачан не полностью или подменён. Удалите `.local/downloads/<файл>` и повторите `make up`. Не меняйте sha256 в `infra/tools/tools.yml`, пока не сверите его с checksum, который опубликовал разработчик инструмента |
| Нет доступа к `get.helm.sh`/GitHub Releases | `make doctor` покажет недоступный источник. Можно положить бинарник той же версии в `.local/bin`: роль проверит версию и не будет его скачивать |
| `python3 -m venv` не работает / нет Python ≥ 3.12 | `make prereqs` (на 22.04 ставит `python3.12` из PPA deadsnakes) или `PYTHON=/путь/к/python3.12` в `.env` |

## Кластер k3d

| Симптом | Причина / решение |
|---|---|
| `kubelet is configured to not run on a host using cgroup v1` | Хост работает на cgroup v1. Роль `cluster` сама добавляет `--kubelet-arg=fail-cgroupv1=false`, если `docker info` показывает cgroup v1. Если кластер был создан без этого флага — `make down && make up` |
| pod в `ContainerCreating`, события `failed to pull image … x509` | Узел k3s не доверяет TLS-прокси. Задайте `EXTRA_CA_BUNDLE` и выполните `make down && make up` |
| `too many open files` в логах pod | `sudo sysctl -w fs.inotify.max_user_instances=512` (и `max_user_watches=524288`) |
| `cluster dns configmap` не дождались | Посмотрите ошибки узла: `docker logs k3d-mts-devops-server-0 2>&1 \| grep -i error` |
| Нужно начать с чистого листа | `make down` (секреты сохраняются), затем `make up`. Полная очистка — `make down PURGE=1 CONFIRM=yes` |

## Registry

| Симптом | Решение |
|---|---|
| `ErrImagePull … localhost:5001/mts-api@sha256:…` | Внутри узла адрес `localhost:5001` перенаправляется на контейнер registry через `registries.yaml`. Проверьте файл: `docker exec k3d-mts-devops-server-0 cat /etc/rancher/k3s/registries.yaml`. Убедитесь, что контейнер `mts-devops-registry` запущен |
| `push` отклонён | Registry стенда работает только вместе с кластером. Выполните `make up` |

## Prometheus / scrape targets

| Симптом | Решение |
|---|---|
| target `mts-api` в `down` | См. runbook `MtsApiTargetDown`. Проверьте NetworkPolicy слота и что у Prometheus есть метка `app.kubernetes.io/name=prometheus` |
| target `kubelet-cadvisor` `x509` | TLS kubelet проверяется по CA кластера. При нестандартной установке k3s кластерный CA может не подписывать сертификат kubelet. Проверьте: `kubectl get --raw /api/v1/nodes/<node>/proxy/metrics/cadvisor` |
| Релиз отклонён: `metrics_unavailable` | Prometheus не отвечает через ingress или не скрейпит кандидата за 60 с. Это защитное поведение: без метрик релиз не проходит (fail closed). Проверьте `make verify` |

## Secret / SOPS

| Симптом | Решение |
|---|---|
| `Recovery failed because no master key was able to decrypt the file` | SOPS-источник зашифрован другим age-ключом (ключ удалён или подменён). Ключ лежит в `~/.config/mts-devops/<cluster>/age.key`. Если ключ утерян, данные не восстановить. Команда `make down PURGE=1 CONFIRM=yes && make up` создаст новые |
| pod не Ready: `api token hashes are not mounted` | Нет Secret `api-auth`. Выполните `make up`: роль platform применит секреты |
| Ротация: «не все pod приняли новый токен за 150 с» | kubelet не обновил volume. Перекрытие остаётся в силе: действуют оба токена, это безопасно. Повторите `make rotate-secret` |

## Helm

| Симптом | Решение |
|---|---|
| `another operation (install/upgrade/rollback) is in progress` | Операция Helm была прервана. Посмотрите историю: `./.local/bin/helm --kubeconfig .local/kube/admin.kubeconfig -n mts-app history mts-api-blue`. Затем выполните `helm rollback` к последней ревизии со статусом `deployed` |
| `values don't meet the specifications of the schema` | Схема чарта не пропускает слот вне blue/green и образ без digest. Так задумано |
| `Unauthorized` у релизов через неделю | Истёк токен релизной учётной записи (срок — 7 дней). `make up` выпустит новый |

## Ресурсы

Цель проекта — 4 vCPU / 8 ГБ RAM. По замеру весь стенд в покое занимает ≈ 1,6 ГиБ RAM. Сюда входят
k3s, приложение (4 pod), Prometheus, Grafana, Alertmanager и blackbox. Если памяти мало, уменьшите
`replicas` в `charts/app/values.yaml` до 1 и уменьшите `prometheus.retentionSize`.

## Trivy

| Симптом | Решение |
|---|---|
| Стадия `scan`: `BLOCK CVE-… (HIGH)` | Для уязвимости вышло исправление. Обновите зависимость (`make lock`) или базовый образ. Если обновиться обоснованно нельзя, добавьте адресное исключение в `.trivyignore.yaml` со `statement` и `expired_at` ≤ 90 дней |
| Ошибка загрузки базы | Trivy берёт базу с `mirror.gcr.io`, резерв — ghcr.io. Без базы стадия завершается ошибкой. Так задумано |
