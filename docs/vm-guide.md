# Запуск на виртуальной машине с Ubuntu — пошагово

Инструкция для самостоятельной проверки проекта на чистой ВМ: VirtualBox, VMware, Hyper-V, UTM или
Parallels на Mac, облачная ВМ. Вложенная виртуализация не нужна: Kubernetes (k3s) работает внутри
контейнера Docker.

Весь путь коротко:

1. Создайте ВМ с нужными параметрами (раздел 1).
2. Подготовьте ВМ: `make prereqs` и `make doctor` (раздел 2, ~2–5 минут).
3. Запустите стенд: `make up` (раздел 3, 3–6 минут).
4. Проверьте стенд и сценарии релизов (раздел 4).
5. Откройте Grafana, Prometheus и Alertmanager (раздел 5).

## 1. Параметры ВМ

| Параметр | Рекомендуется | Комментарий |
|---|---|---|
| ОС | Ubuntu Server или Desktop **24.04 LTS** | Также поддерживаются 22.04 и 26.04 LTS (см. раздел 8 «Что проверено») |
| Архитектура | x86_64 (amd64) или aarch64 (arm64) | arm64 — например, UTM или Parallels на Mac с Apple Silicon |
| vCPU | 4 | С 2 vCPU `make doctor` выдаст предупреждение, всё будет работать медленнее (не проверялось) |
| RAM | 8 ГБ | Минимум — 4 ГБ, `make doctor` выдаст предупреждение. Если ВМ видит меньше ≈ 3,5 ГиБ, `make doctor` завершится ошибкой. Пик за полный прогон — ≈ 2,2 ГиБ (раздел 8) |
| Диск | 40 ГБ | Образы, кэш сборки, база Trivy и данные кластера занимают ≈ 10 ГБ |
| Сеть | Доступ в интернет (NAT достаточно) | Входящие порты не нужны: все адреса стенда работают только на `127.0.0.1` внутри ВМ |

ВМ нужен доступ в интернет. Основные источники загрузок:

- архивы Ubuntu: archive.ubuntu.com, security.ubuntu.com (для arm64 — ports.ubuntu.com) или зеркало;
- Docker Hub: registry-1.docker.io, auth.docker.io;
- ghcr.io, github.com (Releases), dl.k8s.io, get.helm.sh;
- pypi.org и files.pythonhosted.org;
- mirror.gcr.io;
- только на Ubuntu 22.04: keyserver.ubuntu.com и ppa.launchpadcontent.net.

Загрузки перенаправляются на CDN: release-assets.githubusercontent.com,
pkg-containers.githubusercontent.com, production.cloudflare.docker.com,
production.cloudfront.docker.com и другие. Если сеть пропускает только хосты из белого списка,
откройте и основные источники, и CDN-хосты (для Docker Hub — по списку со страницы Docker
«Allowlist»). `make doctor` проверяет основные источники, но не каждый CDN-хост.

## 2. Подготовка ВМ (однократно, ~2–5 минут)

```bash
sudo apt-get update && sudo apt-get install -y git make
git clone https://github.com/mitrcik/MTS_DEVOPS_TASK.git mts-devops
cd mts-devops
make prereqs       # Docker Engine + buildx, Python >= 3.12 с venv, curl, лимиты inotify (спросит пароль sudo)
newgrp docker      # или выйти из сеанса и войти снова: группа docker должна вступить в силу
make doctor        # итог: «doctor: обязательные проверки пройдены»
```

Что делает `make prereqs` (скрипт `scripts/install-prereqs.sh`):

- ставит только пакеты из репозиториев Ubuntu: `docker.io`, `docker-buildx`, `python3-venv` и другие;
- на Ubuntu 22.04 ставит `python3.12` из PPA deadsnakes и проверяет отпечаток ключа этого PPA;
- не трогает уже установленный Docker, в том числе Docker CE;
- безопасно запускается повторно.

Членство в группе `docker` равносильно root-доступу к ВМ. На учебной ВМ это нормально. На общих
серверах выдавайте его осознанно.

Если `make doctor` сообщает об ошибке, посмотрите раздел 7 «Частые проблемы на ВМ».

> Совет: сделайте снимок (snapshot) ВМ после `make prereqs`. К нему удобно возвращаться.

## 3. Запуск стенда

```bash
make up
```

Первый запуск занимает 3–6 минут, при медленном интернете — дольше. На чистых ВМ GitHub он занял
от 3 мин 17 с до 3 мин 40 с. За это время `make up`:

- скачивает инструменты и проверяет их sha256;
- скачивает образы k3s, Prometheus, Grafana и базу Trivy;
- собирает образ приложения и сканирует его;
- выполняет первый blue-green релиз `v1`. Blue-green — два слота приложения (blue и green), трафик
  переключается между ними.

В конце вывода — сводка с адресами стенда, активной версией и подсказкой, что делать дальше:

```text
 Стенд готов за 207 с. Все адреса открываются только на этом компьютере (127.0.0.1).

   API:           http://127.0.0.1:8080/api/v1/tariffs
   Grafana:       http://grafana.localhost:8080   (логин admin, пароль: make credentials)
   Prometheus:    http://prometheus.localhost:8080
   Alertmanager:  http://alertmanager.localhost:8080

   Пользователей обслуживает: v1 в слоте blue (релиз v1-…)
```

Как это выглядит в терминале — [`images/make-up.png`](images/make-up.png).

Повторный `make up` безопасен: он ничего не ломает и не перевыпускает работающую версию (≈ 20 с).

## 4. Проверка — что запускать и что должно получиться

Выполняйте команды сверху вниз. После `make release VERSION=v2` активной становится версия v2, и
ожидаемые результаты следующих строк исходят из этого. Preview — проверка кандидата до
переключения трафика.

| Команда | Время | Ожидаемый результат |
|---|---|---|
| `make verify` | ~1 с | 14 проверок `[ OK ]`: API через ingress, ответ 401 без токена, расчёт с токеном, Prometheus targets, правила алертов, Grafana |
| `make release VERSION=v2` | 75–120 с | Полный CI → кандидат в неактивном слоте → preview → переключение → окно наблюдения → решение `promoted`. `make status` показывает `[ACTIVE ] green версия=v2`. Первый релиз после включения ВМ дольше: Trivy обновляет базу уязвимостей, кэши ещё пустые |
| `make demo-failure` | ~45 с | Версия с дефектом проходит preview, но после переключения отвечает 5xx. Трафик **автоматически возвращается** на прежний слот, решение `rolled_back`. Активной остаётся v2 |
| `make demo-not-ready` | ~75 с | Кандидат не становится Ready → решение `rejected` **до** переключения. Пользователи не затронуты |
| `make demo-no-metrics` | ~30 с | Prometheus временно выключен → релиз `rejected`: нет метрик — значит, нет и подтверждения успеха. Затем Prometheus возвращается |
| `make demo-alert` | ~55 с | Реальный сбой → алерт `MtsApiSyntheticProbeFailing` проходит pending → firing → Alertmanager → восстановление → resolved. На показе: `make demo-alert HOLD=60` держит сбой ещё 60 с после доставки алерта — успеете открыть Prometheus, Alertmanager и Grafana |
| `make rotate-secret` | ~3 с | Новый токен работает во всех pod обоих слотов, старый отклоняется (401) |
| `make verify-security` | ~10 с | 17 проверок: non-root, read-only FS, NetworkPolicy, RBAC, шифрование Secret |
| `make status` | ~1 с | Активный слот, версии, история решений |
| `make test-e2e` | ~10–13 мин | Все 15 приёмочных сценариев подряд, итог `все сценарии пройдены` |

Каждый релиз сохраняет отчёт в `.local/reports/release-*.md` (и `.json`): решение, причина,
проверки, метрики, длительности. Если результат отличается от таблицы, выполните `make status` и
откройте [`docs/troubleshooting.md`](troubleshooting.md).

## 5. Веб-интерфейсы (Grafana, Prometheus, Alertmanager)

Стенд слушает только `127.0.0.1:8080` внутри ВМ. Наружу ничего не открыто — так безопаснее.

**Ubuntu Desktop.** Откройте браузер внутри ВМ и перейдите по адресам из таблицы ниже.

**Ubuntu Server (ВМ без графического интерфейса).** Откройте SSH-туннель со своего компьютера.
Туннель передаёт порт 8080 вашего компьютера на порт 8080 внутри ВМ.

1. Включите SSH-сервер в ВМ. При установке Ubuntu Server отметьте «Install OpenSSH server» или
   выполните в ВМ `sudo apt-get install -y openssh-server`.
2. Только для VirtualBox с сетью NAT: Настройки ВМ → Сеть → Дополнительно → Проброс портов: TCP,
   порт хоста 2222 → порт гостя 22.
3. Откройте туннель со своего компьютера:

```bash
ssh -L 8080:127.0.0.1:8080 <пользователь>@<IP-адрес ВМ>
# VirtualBox с NAT и пробросом порта 2222 → 22:
ssh -p 2222 -L 8080:127.0.0.1:8080 <пользователь>@127.0.0.1
```

Пока туннель открыт, откройте на своём компьютере:

| Адрес | Что |
|---|---|
| http://grafana.localhost:8080 | Grafana, дашборд «MTS DevOps — демо-API: доступность, релизы, ресурсы». Логин `admin`, пароль покажет `make credentials` в ВМ |
| http://prometheus.localhost:8080 | Prometheus: Status → Targets, Alerts |
| http://alertmanager.localhost:8080 | Alertmanager |
| http://127.0.0.1:8080/api/v1/tariffs | API |

Chrome, Firefox и Edge сами направляют `*.localhost` на `127.0.0.1`. Если браузер не открывает
адрес (например, Safari), добавьте на **своём** компьютере в файл hosts строку
`127.0.0.1 grafana.localhost prometheus.localhost alertmanager.localhost`.
Файл hosts: Windows — `C:\Windows\System32\drivers\etc\hosts`, macOS и Linux — `/etc/hosts`.

## 6. Остановка, перезапуск ВМ, удаление

Учебные секреты хранятся в SOPS-файле, зашифрованном age-ключом.

| Действие | Команда |
|---|---|
| Удалить стенд, сохранить ключ и секреты | `make down` |
| Удалить всё, включая age-ключ и SOPS-файл | `make down PURGE=1 CONFIRM=yes` |
| Поднять заново | `make up` |
| После перезагрузки ВМ | Контейнеры стенда запускаются вместе с Docker. Подождите 1–2 минуты и выполните `make verify`. При ошибках выполните `make up` |

## 7. Частые проблемы на ВМ

Параметры вроде `DOCKERHUB_MIRROR` и `INGRESS_PORT` задаются в файле `.env` в корне репозитория.

| Симптом | Решение |
|---|---|
| `permission denied … /var/run/docker.sock` | Группа `docker` ещё не действует. Выполните `newgrp docker` или выйдите из сеанса и войдите снова |
| `make doctor`: мало RAM/CPU/диска | Увеличьте ресурсы ВМ (раздел 1) |
| `toomanyrequests` (лимит Docker Hub) | Добавьте `DOCKERHUB_MIRROR=https://mirror.gcr.io` в `.env` и настройте зеркало для Docker хоста ([`docs/troubleshooting.md`](troubleshooting.md)). Затем выполните `make down && make up` |
| `x509: certificate …` за корпоративным прокси | Добавьте `EXTRA_CA_BUNDLE=/путь/к/ca-bundle.crt` в `.env` |
| `certificate is not yet valid` или ошибки TLS после паузы ВМ | Сбились часы ВМ. Выполните `sudo timedatectl set-ntp true` и проверьте `date` |
| Docker установлен из snap | `make doctor` выдаст предупреждение. Рекомендуется `sudo snap remove docker && make prereqs` |
| Порт 8080 на вашем компьютере занят (для туннеля) | В ВМ добавьте `INGRESS_PORT=18080` в `.env` и выполните `make down && make up`. Туннель: `ssh -L 18080:127.0.0.1:18080 …`, адреса: `http://grafana.localhost:18080`. Номер порта должен совпадать по обе стороны туннеля: Grafana и Prometheus строят ссылки по нему |

## 8. Что проверено

«Чистая ВМ» здесь — новая ВМ GitHub Actions (runner), на которой проект ещё не запускался.

| Окружение | Как | Результат |
|---|---|---|
| Ubuntu 24.04 x86_64, чистая ВМ | Runner GitHub `ubuntu-24.04`: `make doctor` → `make up` → 15 сценариев (`ci.yml`, на каждый push) | ✅ 15/15 ([`docs/validation/github-actions.md`](validation/github-actions.md)) |
| Ubuntu 22.04 x86_64, чистая ВМ | Runner `ubuntu-22.04`: `make prereqs` (python3.12 из deadsnakes; Docker CE на runner предустановлен) → … → 15 сценариев (`compat.yml`) | ✅ 15/15, `make up` 3 мин 22 с ([`docs/validation/compat.md`](validation/compat.md)) |
| Ubuntu 24.04 aarch64 (arm64), чистая ВМ | Runner `ubuntu-24.04-arm`: `make prereqs` → … → 15 сценариев | ✅ 15/15, `make up` 3 мин 17 с |
| Ubuntu 22.04 / 24.04 / 26.04 — пакеты и окружение | Контейнер `ubuntu:<версия>` с Docker хоста. `make prereqs` ставит Docker CLI (`docker.io`), buildx и Python из архивов Ubuntu, дальше — полный путь. Docker daemon — от хоста | ✅ 15/15 в каждом (Python 3.12 / 3.12 / 3.14) |
| Ubuntu 24.04, среда разработки | Маршрут из раздела 4 вручную; перезапуск Docker как имитация перезагрузки | ✅ все команды; после перезапуска `verify` 14/14 через 34 с ([`docs/validation/local-e2e.md`](validation/local-e2e.md)) |

Пиковая память хоста за `make up` и 15 сценариев — около 2,2 ГиБ. Место на диске после полного
прогона — около 9 ГБ.

Не проверялось:

- настоящая ВМ с Ubuntu 26.04 (проверено окружение 26.04 в контейнере на ядре Ubuntu 24.04);
- запуск Docker daemon из пакета `docker.io` и шаг с группой `docker` и `newgrp` на настоящей ВМ:
  на ВМ GitHub Docker CE предустановлен, а в контейнерных проверках работал Docker хоста;
- ВМ с 2 vCPU или 4 ГБ RAM;
- WSL2;
- Docker из snap.
