# Безопасность

Глубину мер команда выбирает сама, но меры должны быть описаны и проверяемы [10:55, 40:02].
Каждая мера ниже: что сделано → где → как проверить. Сводная проверка: `make verify-security`
(17 проверок на работающем стенде) и стадия `lint` конвейера.

## 1. Секреты

| Мера | Где | Проверка |
|---|---|---|
| Учебные секреты (API-токен, пароль Grafana) генерируются в памяти и шифруются SOPS + age из stdin; plaintext на диск не пишется | `scripts/pylib/secrets.py` (`init_source`, `write_source`) | `ls -l .local/secrets/` → только `app-secrets.sops.yaml` (0600); `head .local/secrets/app-secrets.sops.yaml` — значения `ENC[AES256_GCM,…]` |
| Закрытый age-ключ хранится отдельно и вне проекта: `~/.config/mts-devops/<cluster>/age.key` (0600, каталог 0700) | `ensure_age_key` | `stat -c %a ~/.config/mts-devops/mts-devops/age.key` → `600` |
| Повторный `make up` не меняет ключ и значения; существующий источник только проверяется на расшифровку | роль `secrets`, `init_source` | сценарий `idempotent-up` в `make test-e2e` сравнивает отпечатки до/после |
| Расшифровка только в память; в кластер — `kubectl apply --server-side -f -` из stdin (без аннотации `last-applied-configuration`) | `apply_api_secret`, `apply_grafana_secret` | `kubectl get secret api-auth -o yaml` — нет аннотации last-applied |
| В Secret `api-auth` лежат только SHA-256 токенов; токен — только в SOPS-файле | `api_secret_manifest`; `app/src/mts_api/auth.py` | `kubectl get secret api-auth -o jsonpath='{.data.token-hashes}' \| base64 -d` → 64-символьные хеши |
| Helm-чарт ссылается на `existingSecret`, значение через `--set` не передаётся и в release values не попадает | `charts/app/values.yaml` (`auth.existingSecret`) | `helm get values mts-api-blue -n mts-app` — секретов нет |
| Секреты не печатаются: `make credentials` показывает их только по явной команде; в логах приложения нет заголовков и тел запросов | `bgctl credentials`; `app/tests/test_api.py::test_logs_never_contain_token` | unit-тест; `kubectl logs` |
| Защита Secret в хранилище кластера: k3s `--secrets-encryption` (AES-CBC) | шаблон k3d, роль `cluster` | `make verify-security`: «Encryption Status: Enabled», хеш токена не встречается открытым текстом в `state.db`, есть записи `k8s:enc:aescbc:v1:` |
| Git без секретов: `.gitignore` для `.local/`, `.env`, ключей; проверка отслеживаемых файлов и `trivy fs --scanners secret` | стадия `lint` (`cihelper.py check-tracked-files`) | `scripts/ci.sh lint` |
| Образ без секретов: Trivy сканирует и уязвимости, и секреты; найденный секрет блокирует публикацию | стадия `scan` | `.local/artifacts/<tag>/trivy-summary.json` → `secrets: []` |

**Base64 — не шифрование.** Kubernetes API отдаёт Secret в base64 любому, у кого есть `get secrets`
в namespace. Поэтому у релизной учётной записи права ограничены namespace `mts-app`, а в самом
Secret нет исходного токена. Ключ шифрования k3s лежит на том же узле — это защищает копию/дамп
базы, но не скомпрометированный узел (для production — KMS-провайдер).

## 2. Ротация API-токена

Команда: `make rotate-secret`. Стратегия — **перекрытие (overlap)**, без окна недоступности:

1. Берётся общая блокировка стенда (та же, что у релизов): ротация и релиз не меняют стенд одновременно.
2. Генерируется новый токен; в SOPS-источнике `current=новый`, `previous=старый`; Secret содержит хеши обоих.
3. Аннотация каждого pod заставляет kubelet сразу пересинхронизировать volume Secret.
4. Проверка: **каждый pod обоих слотов** (через port-forward) принимает новый токен.
5. Отзыв: `previous` очищается, Secret содержит только новый хеш, повторная синхронизация.
6. Проверка: каждый pod обоих слотов отвергает старый (401) и принимает новый (200); то же через ingress.
7. Отчёт `.local/reports/rotation-*.json|md` (отпечатки токенов, статусы по pod), запись в ConfigMap состояния.

Почему откат после ротации безопасен: оба слота читают **один** Secret как файл, приложение
перечитывает его при смене inode/mtime (`TokenStore`). Возврат трафика на «старый» слот не
возвращает отозванный токен. Цепочка «ротация → неудачный релиз → откат» проверяется сценарием
`rotation-chain` в `make test-e2e`.

Пароль Grafana: хранится в том же SOPS-источнике; ротация вне учебного сценария (изменить значение
через `sops` и выполнить `make up`).

## 3. Kubernetes

| Мера | Где | Проверка |
|---|---|---|
| Pod Security Admission `restricted` (enforce) для `mts-app` и `monitoring` | `charts/platform/templates/namespaces.yaml` | `kubectl get ns mts-app --show-labels` |
| Отдельный ServiceAccount на слот, токен API не монтируется (`automountServiceAccountToken: false`) | `charts/app/templates/*` | `verify-security`: «токен ServiceAccount не смонтирован» |
| Контейнер: UID 10001, `runAsNonRoot`, без privilege escalation, `drop: [ALL]`, `seccompProfile: RuntimeDefault`, read-only root FS, `/tmp` — отдельный emptyDir 16 МиБ, requests/limits | `charts/app/templates/deployment.yaml` | `verify-security`: uid=10001, `touch /app/probe` → Read-only, CapEff=0 |
| NetworkPolicy: default-deny на namespace; слоту разрешён вход только от Traefik и Prometheus на порт 8000, выход только в DNS | `charts/platform`, `charts/app/templates/networkpolicy.yaml` | `verify-security`: pod из чужого namespace получает отказ; тот же pod через ingress — 200; из pod приложения DNS работает, TCP к API-серверу запрещён. Контроллер NetworkPolicy k3s (kube-router) применяет политики — это проверено, а не предполагается |
| RBAC релизов: `release-controller` — Role только в `mts-app`; нет `pods/exec`, узлов, ClusterRole, других namespace | `charts/platform/templates/rbac.yaml` | `verify-security`: `kubectl auth can-i …` |
| Prometheus: `nodes/metrics` вместо `nodes/proxy`; обнаружение pod — Role только в нужных namespace; TLS к kubelet проверяется по CA кластера | `observability/templates/prometheus.yaml` | `kubectl auth can-i --as=system:serviceaccount:monitoring:prometheus get nodes/proxy` → no |
| Образ: Alpine 3.24, без pip, без shell-утилит сверх busybox, непривилегированный пользователь | `app/Dockerfile` | `docker run --rm --entrypoint python <img> -c "import pip"` → ModuleNotFoundError |

## 4. Разделение привилегий

| Роль | Учётные данные | Что может |
|---|---|---|
| Bootstrap (`make up`) | `.local/kube/admin.kubeconfig` (0600, cluster-admin k3d) — **только** на хосте стенда | создаёт кластер, namespace, RBAC, наблюдаемость, Secret Grafana |
| Релизы, ротация, демо-алерт | `.local/kube/deploy.kubeconfig` (0600): ServiceAccount `release-controller`, токен TokenRequest со сроком 7 дней | только объекты `mts-app` |
| GitHub Actions (CI) | `GITHUB_TOKEN`: `contents: read`; `packages: write` — только у job `image`, а использует его только шаг публикации, который выполняется лишь при push (для PR шаг пропускается; PR из форков получают токен только на чтение) | нет доступа к кластерам |
| GitHub Actions (CD, ветка по умолчанию) | SSH-ключ деплоя → forced command `deploy-gate.sh` | только `status` и `release < provenance.json` на удалённом стенде |

Остаточные привилегии, о которых нужно знать: доступ к Docker на хосте эквивалентен root;
admin-kubeconfig k3d даёт полный доступ к учебному кластеру; у релизной учётной записи есть
`get secrets` в `mts-app` (нужно Helm для хранения релизов) — поэтому в Secret нет самих токенов.
На удалённом стенде (не проверено) `release` от CI выполняется от служебного пользователя стенда,
который состоит в группе `docker`; граница доверия — forced command и проверка provenance
(`docs/remote-cd.md`, «Границы полномочий»).

## 5. Цепочка поставки

| Мера | Где |
|---|---|
| CLI-инструменты загружаются с официальных адресов и проверяются по закреплённым sha256 до установки; checksum Helm подтверждён загрузкой с get.helm.sh в GitHub Actions | `infra/tools/tools.yml`, роль `tools` |
| Python-зависимости: lock-файлы с хешами, `pip --require-hashes --only-binary=:all:` | `app/requirements*.lock`, `infra/tooling/requirements.lock` |
| Действия GitHub закреплены по commit SHA с комментарием версии; права — на уровне job | `.github/workflows/ci.yml` |
| Не пересобираем после сканирования; деплой только по digest; контроллер принимает только provenance с `trivy.result=passed` и совпадающим digest | `scripts/ci.sh`, `scripts/pylib/release.py` (`Artifact.from_provenance`) |
| Удалённый стенд может ограничить репозиторий образов: `ALLOWED_IMAGE_REPOSITORY` | `scripts/bgctl.py release` |

### Политика Trivy

- Блокируют публикацию: уязвимости **HIGH/CRITICAL с доступным исправлением** и **любые найденные секреты**.
- Не блокируют, но выводятся и считаются: остальные уязвимости, включая HIGH/CRITICAL без исправления.
- Исключения: только адресно в `.trivyignore.yaml`, с `statement` и `expired_at` ≤ 90 дней (проверяется в CI).
- Недоступная база/сбой сканера = провал стадии. В отчёт записываются версия Trivy и дата БД.

## 6. Сеть стенда

Ingress, API Kubernetes и registry публикуются только на `127.0.0.1`. Локальный HTTP без TLS —
осознанное ограничение демо-профиля. Для удалённого профиля TLS настраивается отдельно
(`docs/remote-cd.md`), локальный registry наружу не публикуется — удалённый стенд берёт образы из GHCR.
