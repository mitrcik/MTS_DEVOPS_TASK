# Безопасность

На консультации организаторы разрешили команде самой выбрать глубину мер безопасности. Условие
одно: каждая мера описана, и её можно проверить.

Для каждой меры ниже указано: что сделано, где это находится и как это проверить. Сводная проверка —
`make verify-security` (17 проверок на работающем стенде) и стадия `lint` конвейера CI.

## 1. Секреты

| Мера | Где | Проверка |
|---|---|---|
| Учебные секреты (API-токен, пароль Grafana) создаются в памяти и шифруются SOPS + age (шифрование значений в YAML-файле) через stdin. Открытый текст на диск не попадает | `scripts/pylib/secrets.py` (`init_source`, `write_source`) | `ls -l .local/secrets/` → только `app-secrets.sops.yaml` (0600); `head .local/secrets/app-secrets.sops.yaml` — значения `ENC[AES256_GCM,…]` |
| Закрытый age-ключ хранится отдельно, вне каталога проекта: `~/.config/mts-devops/<cluster>/age.key` (права 0600, каталог 0700) | `ensure_age_key` | `stat -c %a ~/.config/mts-devops/mts-devops/age.key` → `600` |
| Повторный `make up` не меняет ни ключ, ни значения секретов. Существующий файл-источник он только проверяет на расшифровку | роль Ansible `secrets`, `init_source` | сценарий `idempotent-up` в `make test-e2e` сравнивает отпечатки до и после |
| Секреты расшифровываются только в память. В кластер они передаются через stdin командой `kubectl apply --server-side -f -`, поэтому у Secret нет аннотации `last-applied-configuration` (в ней kubectl хранит копию манифеста) | `apply_api_secret`, `apply_grafana_secret` | `kubectl get secret api-auth -o yaml` — нет аннотации last-applied |
| В Secret `api-auth` лежат только SHA-256-хеши токенов. Сам токен есть только в SOPS-файле | `api_secret_manifest`; `app/src/mts_api/auth.py` | `kubectl get secret api-auth -o jsonpath='{.data.token-hashes}' \| base64 -d` → 64-символьные хеши |
| Helm-чарт ссылается на готовый Secret (`existingSecret`). Значение не передаётся через `--set` и не попадает в values релиза | `charts/app/values.yaml` (`auth.existingSecret`) | `helm get values mts-api-blue -n mts-app` — секретов нет |
| Секреты не выводятся без запроса: их показывает только явная команда `make credentials`. В логах приложения нет заголовков и тел запросов | `bgctl credentials`; `app/tests/test_api.py::test_logs_never_contain_token` | unit-тест; `kubectl logs` |
| Объекты Secret зашифрованы в хранилище кластера: k3s запущен с `--secrets-encryption` (AES-CBC) | шаблон k3d, роль Ansible `cluster` | `make verify-security`: «Encryption Status: Enabled», хеш токена не встречается открытым текстом в `state.db`, есть записи `k8s:enc:aescbc:v1:` |
| В Git нет секретов: `.local/`, `.env` и ключи исключены через `.gitignore`. CI проверяет список отслеживаемых файлов и запускает `trivy fs --scanners secret` | стадия `lint` (`cihelper.py check-tracked-files`) | `scripts/ci.sh lint` |
| В образе нет секретов: Trivy ищет и уязвимости, и секреты. Найденный секрет блокирует публикацию образа | стадия `scan` | `.local/artifacts/<tag>/trivy-summary.json` → `secrets: []` |

**Base64 — это не шифрование.** Kubernetes API отдаёт Secret в base64 любому, у кого есть право
`get secrets` в namespace. Поэтому права релизной учётной записи ограничены namespace `mts-app`, а в
самом Secret нет исходного токена.

Шифрование k3s защищает копию или дамп базы. Но ключ шифрования лежит на том же узле, поэтому от
взлома самого узла оно не защищает. Для production нужен KMS-провайдер.

## 2. Ротация API-токена

Приложение развёрнуто по схеме blue-green: два слота (`blue` и `green`), трафик переключается между
ними. Ротация обновляет токен в обоих слотах.

Команда: `make rotate-secret`. Стратегия — **перекрытие (overlap)**: какое-то время действуют и старый,
и новый токен, поэтому окна недоступности нет. Шаги:

1. Ротация берёт общую блокировку стенда — ту же, что и релизы. Поэтому ротация и релиз не меняют
   стенд одновременно.
2. Создаётся новый токен. В SOPS-источнике записывается `current=новый`, `previous=старый`. Secret
   содержит хеши обоих токенов.
3. На каждый pod ставится аннотация. Она заставляет kubelet сразу пересинхронизировать volume с Secret.
4. Проверка: **каждый pod обоих слотов** принимает новый токен (запросы идут через port-forward).
5. Отзыв старого токена: `previous` очищается, в Secret остаётся только новый хеш, volume снова
   синхронизируется.
6. Проверка: каждый pod обоих слотов отвергает старый токен (401) и принимает новый (200). То же
   проверяется через ingress.
7. Результат записывается в отчёт `.local/reports/rotation-*.json|md` (отпечатки токенов, статусы по
   каждому pod) и в ConfigMap состояния.

**Почему откат после ротации безопасен.** Оба слота читают **один и тот же** Secret как файл.
Приложение перечитывает этот файл, когда меняется его inode или mtime (`TokenStore`). Поэтому возврат
трафика на «старый» слот не возвращает отозванный токен. Цепочку «ротация → неудачный релиз → откат»
проверяет сценарий `rotation-chain` в `make test-e2e`.

Пароль Grafana хранится в том же SOPS-источнике. Его ротация не входит в учебный сценарий. Чтобы
сменить пароль, измените значение через `sops` и выполните `make up`.

## 3. Kubernetes

| Мера | Где | Проверка |
|---|---|---|
| Pod Security Admission в режиме `restricted` (enforce) для `mts-app` и `monitoring`: кластер не запустит pod с небезопасными настройками | `charts/platform/templates/namespaces.yaml` | `kubectl get ns mts-app --show-labels` |
| У каждого слота свой ServiceAccount. Токен API в pod не монтируется (`automountServiceAccountToken: false`) | `charts/app/templates/*` | `verify-security`: «токен ServiceAccount не смонтирован» |
| Контейнер: UID 10001, `runAsNonRoot`, без privilege escalation, все capabilities сброшены (`drop: [ALL]`), `seccompProfile: RuntimeDefault`, корневая ФС только для чтения, `/tmp` — отдельный emptyDir 16 МиБ, заданы requests/limits | `charts/app/templates/deployment.yaml` | `verify-security`: uid=10001, `touch /app/probe` → Read-only, CapEff=0 |
| NetworkPolicy: в namespace по умолчанию запрещён весь трафик (default-deny). В слот разрешён вход только от Traefik и Prometheus на порт 8000, выход — только в DNS | `charts/platform`, `charts/app/templates/networkpolicy.yaml` | `verify-security`: pod из чужого namespace получает отказ, а через ingress тот же pod получает 200. Из pod приложения DNS работает, TCP к API-серверу запрещён. То, что контроллер NetworkPolicy в k3s (kube-router) применяет политики, проверено, а не предполагается |
| RBAC релизов: у `release-controller` есть Role только в `mts-app`. Нет прав на `pods/exec`, узлы, ClusterRole и другие namespace | `charts/platform/templates/rbac.yaml` | `verify-security`: `kubectl auth can-i …` |
| Prometheus: доступ к `nodes/metrics` вместо `nodes/proxy`. Для обнаружения pod — Role только в нужных namespace. TLS к kubelet проверяется по CA кластера | `observability/templates/prometheus.yaml` | `kubectl auth can-i --as=system:serviceaccount:monitoring:prometheus get nodes/proxy` → no |
| Образ: Alpine 3.24, без pip, без shell-утилит сверх busybox, запуск от непривилегированного пользователя | `app/Dockerfile` | `docker run --rm --entrypoint python <img> -c "import pip"` → ModuleNotFoundError |

## 4. Разделение привилегий

| Роль | Учётные данные | Что может |
|---|---|---|
| Первичная установка, bootstrap (`make up`) | `.local/kube/admin.kubeconfig` (0600, cluster-admin k3d) — **только** на хосте стенда | создаёт кластер, namespace, RBAC, наблюдаемость, Secret Grafana |
| Релизы, ротация, демо-алерт | `.local/kube/deploy.kubeconfig` (0600): ServiceAccount `release-controller`, токен TokenRequest со сроком 7 дней | работает только с объектами в `mts-app` |
| GitHub Actions (CI) | `GITHUB_TOKEN` с правом `contents: read`. Право `packages: write` есть только у job `image`. Его использует только шаг публикации, а он выполняется лишь при push. Для PR этот шаг пропускается; PR из форков получают токен только на чтение | нет доступа к кластерам |
| GitHub Actions (CD, ветка по умолчанию) | SSH-ключ деплоя, привязанный к forced command `deploy-gate.sh` (по этому ключу SSH запускает только этот скрипт) | только `status` и `release < provenance.json` на удалённом стенде; provenance.json — файл с digest образа и результатом Trivy |

**Остаточные привилегии**, о которых нужно знать:

- Доступ к Docker на хосте равнозначен root.
- admin-kubeconfig k3d даёт полный доступ к учебному кластеру.
- У релизной учётной записи есть право `get secrets` в `mts-app`: оно нужно Helm для хранения
  релизов. Поэтому в Secret нет самих токенов.
- На удалённом стенде (не проверено) команду `release` от CI выполняет служебный пользователь стенда.
  Он состоит в группе `docker`. Граница доверия — forced command и проверка provenance
  (см. [remote-cd.md](remote-cd.md), раздел «Границы полномочий»).

## 5. Цепочка поставки

| Мера | Где |
|---|---|
| CLI-инструменты скачиваются с официальных адресов. До установки их sha256 сверяется с закреплённым значением. Контрольную сумму Helm подтвердила загрузка с get.helm.sh в GitHub Actions | `infra/tools/tools.yml`, роль `tools` |
| Python-зависимости: lock-файлы с хешами, `pip --require-hashes --only-binary=:all:` | `app/requirements*.lock`, `infra/tooling/requirements.lock` |
| Действия (actions) GitHub закреплены по commit SHA, рядом — комментарий с версией. Права задаются на уровне job | `.github/workflows/ci.yml` |
| Образ не пересобирается после сканирования. Деплой идёт только по digest (sha256-идентификатор конкретного образа). Контроллер релизов принимает только provenance с `trivy.result=passed` и совпадающим digest | `scripts/ci.sh`, `scripts/pylib/release.py` (`Artifact.from_provenance`) |
| Удалённый стенд может разрешить образы только из одного репозитория: `ALLOWED_IMAGE_REPOSITORY` | `scripts/bgctl.py release` |

### Политика Trivy

- Блокируют публикацию: уязвимости **HIGH/CRITICAL с доступным исправлением** и **любые найденные секреты**.
- Не блокируют, но выводятся и подсчитываются: остальные уязвимости, включая HIGH/CRITICAL без исправления.
- Исключения — только точечные, в `.trivyignore.yaml`. У каждого исключения есть `statement`
  (обоснование) и `expired_at` ≤ 90 дней. CI это проверяет.
- Если база недоступна или сканер дал сбой, стадия считается проваленной. В отчёт записываются
  версия Trivy и дата базы.

## 6. Сеть стенда

Ingress, API Kubernetes и registry публикуются только на `127.0.0.1`. Локальный HTTP без TLS —
осознанное ограничение демо-профиля. Для удалённого профиля TLS настраивается отдельно
(см. [remote-cd.md](remote-cd.md)). Локальный registry наружу не публикуется: удалённый стенд берёт
образы из GHCR.
