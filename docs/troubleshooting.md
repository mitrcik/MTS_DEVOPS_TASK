# Troubleshooting

Первая команда при любой проблеме — `make doctor` (ничего не меняет, проверяет ОС, Docker,
ресурсы, порты, конфликтующие объекты и доступ к источникам загрузок).

## Docker

| Симптом | Причина | Решение |
|---|---|---|
| `permission denied while trying to connect to the Docker daemon socket` | пользователь не в группе `docker` | `sudo usermod -aG docker $USER`, перелогиниться. Это эквивалент root-доступа к хосту |
| `Cannot connect to the Docker daemon` | демон не запущен | `sudo systemctl enable --now docker` |
| `toomanyrequests` / HTTP 429 при загрузке образов | анонимный лимит Docker Hub для IP | `docker login` или зеркало: в `/etc/docker/daemon.json` `{"registry-mirrors":["https://mirror.gcr.io"]}`, `sudo systemctl restart docker`; для узлов k3s — `DOCKERHUB_MIRROR=https://mirror.gcr.io` в `.env`, затем `make down && make up` |
| `x509: certificate signed by unknown authority` при сборке/загрузке | корпоративный TLS-прокси | `EXTRA_CA_BUNDLE=/путь/к/полному/ca-bundle.crt` в `.env` (системные CA + CA прокси): он передаётся в сборку как BuildKit secret и монтируется в узел k3s |
| `no space left on device` | мало места для образов | `docker system prune` (удалит неиспользуемые образы всех проектов — осторожно) или освободите место; проекту нужно ~6–8 ГБ |

## Порты

| Симптом | Решение |
|---|---|
| `doctor`: порт `127.0.0.1:8080`/`6550`/`5001` занят другим процессом | `ss -ltnp \| grep 8080` — найти процесс; либо изменить `INGRESS_PORT`/`API_PORT`/`REGISTRY_PORT` в `.env` и выполнить `make down && make up` |
| `http://grafana.localhost:8080` не открывается | браузер/резолвер не знает `*.localhost`: используйте `curl -H 'Host: grafana.localhost' http://127.0.0.1:8080/` или добавьте `127.0.0.1 grafana.localhost prometheus.localhost alertmanager.localhost` в `/etc/hosts` (не обязательно; Chrome/Firefox и systemd-resolved резолвят `*.localhost` сами) |

## Загрузка инструментов

| Симптом | Решение |
|---|---|
| `Checksum mismatch` в роли `tools` | файл скачан не полностью или подменён: удалите `.local/downloads/<файл>` и повторите `make up`. Не меняйте sha256 в `infra/tools/tools.yml` без сверки с опубликованным checksum проекта |
| нет доступа к `get.helm.sh`/GitHub Releases | `make doctor` покажет недоступный источник. Можно положить бинарник той же версии в `.local/bin` — роль проверит версию и не будет скачивать |
| `python3 -m venv` не работает | `sudo apt-get install -y python3-venv` |

## Кластер k3d

| Симптом | Причина / решение |
|---|---|
| `kubelet is configured to not run on a host using cgroup v1` | хост на cgroup v1; роль `cluster` сама добавляет `--kubelet-arg=fail-cgroupv1=false`, если `docker info` показывает cgroup v1. Если кластер создан до этого — `make down && make up` |
| pod в `ContainerCreating`, события `failed to pull image … x509` | узел k3s не доверяет TLS-прокси: задайте `EXTRA_CA_BUNDLE`, `make down && make up` |
| `too many open files` в логах pod | `sudo sysctl -w fs.inotify.max_user_instances=512` (и `max_user_watches=524288`) |
| `cluster dns configmap` не дождались | смотрите `docker logs k3d-mts-devops-server-0 2>&1 \| grep -i error` |
| нужно начать с чистого листа | `make down` (секреты сохраняются) → `make up`; полностью — `make down PURGE=1 CONFIRM=yes` |

## Registry

| Симптом | Решение |
|---|---|
| `ErrImagePull … localhost:5001/mts-api@sha256:…` | внутри узла `localhost:5001` перенаправляется на контейнер registry через `registries.yaml`: проверьте `docker exec k3d-mts-devops-server-0 cat /etc/rancher/k3s/registries.yaml` и что контейнер `mts-devops-registry` запущен |
| `push` отклонён | registry стенда поднят только вместе с кластером: `make up` |

## Prometheus / scrape targets

| Симптом | Решение |
|---|---|
| target `mts-api` в `down` | см. runbook `MtsApiTargetDown`; проверьте NetworkPolicy слота и что Prometheus имеет метку `app.kubernetes.io/name=prometheus` |
| target `kubelet-cadvisor` `x509` | TLS kubelet проверяется по CA кластера; при нестандартной установке k3s кластерный CA может не подписывать сертификат kubelet — проверьте `kubectl get --raw /api/v1/nodes/<node>/proxy/metrics/cadvisor` |
| релиз отклонён `metrics_unavailable` | Prometheus не отвечает через ingress или не скрейпит кандидата за 60 с — это защитное поведение (fail closed). Проверьте `make verify` |

## Secret / SOPS

| Симптом | Решение |
|---|---|
| `Recovery failed because no master key was able to decrypt the file` | SOPS-источник зашифрован другим age-ключом (ключ удалён/подменён). Ключ: `~/.config/mts-devops/<cluster>/age.key`. Если ключ утерян, данные не восстановить: `make down PURGE=1 CONFIRM=yes && make up` создаст новые |
| pod не Ready: `api token hashes are not mounted` | нет Secret `api-auth`: `make up` (роль platform применит секреты) |
| ротация «не все pod приняли новый токен за 150 с» | kubelet не обновил volume; перекрытие оставлено (безопасно, оба токена действуют). Повторите `make rotate-secret` |

## Helm

| Симптом | Решение |
|---|---|
| `another operation (install/upgrade/rollback) is in progress` | прерванная операция Helm: `./.local/bin/helm --kubeconfig .local/kube/admin.kubeconfig -n mts-app history mts-api-blue`, затем `helm rollback` к последней `deployed`-ревизии |
| `values don't meet the specifications of the schema` | схема чарта не пропускает слот вне blue/green и образ без digest — это намеренно |
| `Unauthorized` у релизов через неделю | истёк токен релизной учётной записи (7 дней): `make up` выпустит новый |

## Ресурсы

Цель проекта — 4 vCPU / 8 ГБ RAM. Измерено: весь стенд (k3s, приложение 4 pod, Prometheus,
Grafana, Alertmanager, blackbox) ≈ 1,6 ГиБ RAM в покое. Если памяти мало, уменьшите
`replicas` в `charts/app/values.yaml` до 1 и `prometheus.retentionSize`.

## Trivy

| Симптом | Решение |
|---|---|
| стадия `scan`: `BLOCK CVE-… (HIGH)` | вышло исправление уязвимости — обновите зависимость (`make lock`) или базовый образ; при обоснованной невозможности — адресное исключение в `.trivyignore.yaml` со `statement` и `expired_at` ≤ 90 дней |
| ошибка загрузки базы | Trivy берёт базу с `mirror.gcr.io` (резерв — ghcr.io); без базы стадия завершается ошибкой — это намеренно |
