# Материалы к защите

Короткие ответы с привязкой к файлам и проверкам. На защите спрашивают детали — «почему так
стартует контейнер и почему у него такие опции» [15:56]; ниже — то, что команда должна уметь
объяснить без подсказки.

### 1. Почему k3d/k3s и чем стенд отличается от отказоустойчивой промышленной платформы?

- k3d запускает настоящий k3s (API-сервер, kubelet, containerd, Traefik, NetworkPolicy-контроллер
  kube-router, local-path) как контейнер Docker: стенд поднимается за ~15 с без гипервизора; жюри
  проверяет на Ubuntu, однонодовый k3d прямо разрешён [24:27]. Решение D1 в `docs/decisions.md`.
- Отличия от production: один узел (нет HA control plane и рабочих узлов), хранилище kine/sqlite
  вместо etcd, HTTP на loopback без TLS, Prometheus без HA. Путь к HA — `docs/architecture.md` §7.
- Что важно: свойства доставки (неизменяемый артефакт, проверка до/после переключения, откат,
  секреты, наблюдаемость) от числа узлов не зависят и проверяются здесь по-настоящему.

### 2. Как готовится инфраструктура и что заменено по разрешению ВКС?

- `make up` → `scripts/playbook.sh` → `infra/ansible/up.yml`: роли preflight (doctor), tools
  (sha256), secrets (age+SOPS), cluster (шаблон k3d), platform (PSA, NetworkPolicy, RBAC), observability,
  app (CI + первый релиз), summary.
- Буквальный пункт Word «Terraform/Ansible — ВМ/инстанс, netplan, cloud-init» заменён контейнерным
  узлом k3d по ответу [24:27]. **ВМ в проекте не создаётся, Terraform не используется** (D13).
- На готовой ВМ с Ubuntu 22.04/24.04/26.04 (x86_64 или arm64) всё ставится `make prereqs` и
  `make up` (D16, `docs/vm-guide.md`); проверено на чистых ВМ GitHub и в окружениях Ubuntu в контейнере.

### 3. Какой путь проходит образ и как доказать, что деплоится прошедший scan digest?

`scripts/ci.sh`: lint → test → validate → build (тег `<git-sha12>-<версия>`, запоминается image ID)
→ Trivy по этому образу → **проверка, что тег всё ещё указывает на тот же image ID** → push →
digest из `RepoDigests` + сверка с ответом registry (`Docker-Content-Digest`) → `provenance.json`.
Release controller (`Artifact.from_provenance`) отказывает, если `trivy.result != passed` или digest
в provenance не совпадает со ссылкой на образ; чарт принимает только `repo@sha256:…`
(`values.schema.json`). В отчёте релиза — digest, версия Trivy и дата БД.
Проверить: `.local/artifacts/<tag>/provenance.json` и `.local/reports/release-*.md`.

### 4. Как runner достигает целевого окружения и какие права получает?

- GitHub-hosted runner **не** имеет доступа к кластеру на ноутбуке. Локальный путь жюри не зависит
  от GitHub. В GitHub: `checks` и `image` (сборка, Trivy, публикация в GHCR) и `e2e` — одноразовый
  k3d внутри runner (интеграционная проверка, не доставка).
- Постоянный стенд: job `deploy` (только ветка по умолчанию) передаёт `provenance.json` по SSH с проверкой
  `known_hosts` пользователю `deploy`, у которого forced command `scripts/remote/deploy-gate.sh`
  (только `status` и `release`). На стенде релиз выполняет тот же `bgctl` с kubeconfig
  ServiceAccount `release-controller` (Role только в `mts-app`). Kubeconfig администратора не
  покидает стенд. **Статус: настроено, не проверено** — нет хоста (`docs/remote-cd.md`).

### 5. Где переключается пользовательский трафик и кто владеет этим ресурсом?

Service `mts-api-active` (селектор `slot=blue|green`) и Ingress принадлежат **только** Helm-релизу
`mts-api-traffic` (`charts/traffic`). Слоты `mts-api-blue/green` владеют своими Deployment/Service/
NetworkPolicy и маршрутизацию не трогают. Переключение и откат — только из release controller
(`_switch`). Схема чарта traffic требует явный `activeSlot`, поэтому повторный `helm upgrade` не может
незаметно вернуть «слот по умолчанию». Фактический активный слот читается из живого Service.

### 6. Почему pod Ready ещё не означает успешный релиз?

Readiness (`/readyz`) говорит только, что процесс готов принимать запросы (смонтированы хеши
токенов, нет режима `not-ready`). Учебный дефект `errors-behind-ingress` показывает разницу:
кандидат Ready и проходит все 16 preview-проверок напрямую, но через ingress метод расчёта даёт 500.
Поэтому после переключения идёт окно с реальным трафиком через Traefik и проверкой метрик.

### 7. Как определяется неудача, что при отсутствии метрик и как выполняется возврат?

- До переключения: `helm --wait` (Ready, иначе Helm сам откатывает слот), preview каждого pod
  (известный ответ расчёта, 401 без токена, 422 на неверный ввод, версия/release id, метрики),
  Prometheus обязан скрейпить кандидата.
- После: ~8 rps бизнес-запросов через ingress с ранней остановкой (> 2% неуспешных на ≥ 20 запросах),
  затем PromQL по слоту кандидата: число запросов, доля 5xx, p95 по histogram, свежесть scrape
  каждого pod, `app_build_info` с release id.
- **Нет данных ≠ успех** (`scripts/pylib/gate.py`, 17 unit-тестов): недоступный Prometheus, пустой
  вектор, NaN, мало трафика, устаревшая серия → провал. Сценарий `no-metrics` — релиз отклонён.
- Возврат: `helm upgrade mts-api-traffic activeSlot=<прежний>` → ingress стабильно отдаёт прежний
  release id → 10 с проверки без ошибок → `rolled_back` (код 3). Первое развёртывание: возвращаться
  некуда → `failed`, а не «rolled_back».

### 8. Где хранятся секреты, как ротация и что будет при откате после неё?

`docs/security.md`. Источник — SOPS+age `.local/secrets/app-secrets.sops.yaml`, ключ — вне проекта
`~/.config/mts-devops/<cluster>/age.key`. В кластере — Secret с SHA-256 токенов, зашифрованный в базе
k3s. Ротация `make rotate-secret`: перекрытие → проверка каждого pod обоих слотов → отзыв →
проверка → ingress. Оба слота читают один Secret как файл, поэтому откат на другой слот не вернёт
отозванный токен (сценарий `rotation-chain`).

### 9. Как проверить алерт и чем подтверждено восстановление?

`make demo-alert`: активный слот масштабируется в 0 (реальный сбой пользовательского пути) →
`MtsApiSyntheticProbeFailing` pending → firing (≈ 38 с: scrape 5 с + for 30 с) → Alertmanager
(маршрут `team-oncall-critical`) → восстановление реплик → resolved (≈ 10 с). Таймлайн в
`.local/reports/alert-demo-*.json`. Правила дополнительно покрыты `promtool test rules`.

### 10. Что реализовано и проверено, а что остаётся ограничением?

См. `docs/requirements.md` (матрица со статусами) и `docs/validation/`. Ограничения: один узел,
локальный HTTP, CD на постоянный стенд не проверен (нет хоста), ВМ не создаётся автоматически
(Terraform/cloud-init) — готовая ВМ с Ubuntu подготавливается `make prereqs` (`docs/vm-guide.md`),
видео не записано.

## Частые уточняющие вопросы

| Вопрос | Ответ |
|---|---|
| Почему свой контроллер, а не Argo Rollouts/Flagger? | Меньше компонентов и CRD; ≈ 1 300 строк Python (release.py ≈ 760) без сторонних зависимостей, которые можно объяснить построчно; те же шаги работают локально и на удалённом стенде. Для production разумно взять Argo Rollouts — модель (два слота, анализ метрик, abort) та же |
| Почему blue-green, а не canary? | Простая модель отката и проверяемость на одном узле; canary с долями трафика потребовал бы TraefikService/weighted routing и усложнил бы оценку метрик на малом трафике |
| Что если два человека запустят релиз? | Lease `mts-api-change-lock` в кластере: второй получает отказ с именем держателя (код 10). Сценарий `concurrency` |
| Что если релиз прервали? | Фаза в ConfigMap; `make recover` или следующий релиз возвращает трафик на последний подтверждённый релиз и снимает зависшие Helm-ревизии. Сценарий `interrupted` |
| Почему Alpine? | Сравнение Trivy: Debian slim — 166 находок (44 HIGH без исправлений), Alpine 3.24 — 1 MEDIUM; образ 29 МБ сжатых слоёв |
| Почему нет kube-prometheus-stack? | Тяжелее цели 4 vCPU/8 ГБ и сложнее объяснить; собственный чарт ≈ 600 строк шаблонов и values (D12) |
| Сколько ресурсов? | Весь стенд ≈ 1,6 ГиБ RAM в покое, узел k3d ~0,2 vCPU в покое (замер `docker stats`) |
