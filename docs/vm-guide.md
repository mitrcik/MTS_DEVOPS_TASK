# Запуск на виртуальной машине с Ubuntu — пошагово

Документ для самостоятельной проверки проекта на чистой ВМ (VirtualBox, VMware, Hyper-V, UTM/Parallels
на Mac, облачная ВМ). Виртуализация внутри ВМ не нужна: Kubernetes (k3s) работает в контейнере Docker.

## 1. Параметры ВМ

| Параметр | Рекомендуется | Комментарий |
|---|---|---|
| ОС | Ubuntu Server или Desktop **24.04 LTS** | также поддерживаются 22.04 и 26.04 LTS (см. «Что проверено») |
| Архитектура | x86_64 (amd64) или aarch64 (arm64) | arm64 — например, UTM/Parallels на Mac с Apple Silicon |
| vCPU | 4 | 2 — `make doctor` предупредит, всё будет медленнее (не проверялось) |
| RAM | 8 ГБ | меньше 7 ГБ — предупреждение, меньше 4 ГБ — ошибка `make doctor`; пик на стенде — в «Что проверено» |
| Диск | 40 ГБ | образы, кэш сборки, база Trivy и данные кластера занимают ≈ 10 ГБ |
| Сеть | доступ в интернет (NAT достаточно) | входящие порты не нужны: все адреса стенда — только `127.0.0.1` внутри ВМ |

Нужен доступ к: archive.ubuntu.com (или зеркалу), Docker Hub, ghcr.io, github.com (Releases),
dl.k8s.io, get.helm.sh, pypi.org, mirror.gcr.io; на Ubuntu 22.04 ещё keyserver.ubuntu.com и
ppa.launchpadcontent.net. `make doctor` проверяет доступность каждого источника.

## 2. Подготовка ВМ (однократно, ~2–5 минут)

```bash
sudo apt-get update && sudo apt-get install -y git make
git clone https://github.com/mitrcik/MTS_DEVOPS_TASK.git mts-devops
cd mts-devops
make prereqs       # Docker Engine + buildx, Python >= 3.12 с venv, curl, лимиты inotify (спросит пароль sudo)
newgrp docker      # или выйти из сеанса и войти снова: группа docker должна вступить в силу
make doctor        # итог: «doctor: обязательные проверки пройдены»
```

`make prereqs` (`scripts/install-prereqs.sh`) ставит только пакеты из репозиториев Ubuntu
(`docker.io`, `docker-buildx`, `python3-venv`, …); на 22.04 — `python3.12` из PPA deadsnakes с
проверкой отпечатка ключа. Уже установленный Docker (в т.ч. Docker CE) не трогает. Повторный
запуск безопасен. Членство в группе `docker` — эквивалент root-доступа к ВМ; на учебной ВМ это
нормально, на общих серверах решайте осознанно.

> Совет: сделайте снимок (snapshot) ВМ после `make prereqs` — к нему удобно возвращаться.

## 3. Запуск стенда

```bash
make up
```

Первый запуск — 3–6 минут (на чистом runner GitHub — 3 мин 21–25 с), дольше при медленном интернете:
скачиваются инструменты (с проверкой sha256), образы k3s, Prometheus, Grafana и база Trivy,
собирается и сканируется образ приложения, выполняется первый blue-green релиз `v1`.
Последний блок вывода — адреса и состояние слотов:

```text
Стенд готов. Все адреса — только loopback.
...
[ACTIVE ] blue  версия=v1  release=v1-…  ready=2/2  digest=sha256:…
```

Повторный `make up` ничего не ломает и не перевыпускает работающую версию (≈ 20 с).

## 4. Проверка — что запускать и что должно получиться

| Команда | Время | Ожидаемый результат |
|---|---|---|
| `make verify` | ~1 с | 14 проверок `[ OK ]`: API через ingress, 401 без токена, расчёт с токеном, Prometheus targets, правила алертов, Grafana |
| `make release VERSION=v2` | ~75 с | полный CI → кандидат в неактивном слоте → preview → переключение → окно наблюдения → `promoted`; `make status` показывает `[ACTIVE ] green версия=v2` |
| `make demo-failure` | ~45 с | версия с дефектом проходит preview, после переключения даёт 5xx → **автоматический возврат трафика**, решение `rolled_back`; активной остаётся v2 |
| `make demo-not-ready` | ~75 с | кандидат не становится Ready → `rejected` **до** переключения, пользователи не затронуты |
| `make demo-no-metrics` | ~30 с | Prometheus временно выключен → релиз `rejected` (нет метрик ≠ успех), Prometheus возвращается |
| `make demo-alert` | ~55 с | реальный сбой → алерт `MtsApiSyntheticProbeFailing` pending → firing → Alertmanager → восстановление → resolved |
| `make rotate-secret` | ~3 с | новый токен работает во всех pod обоих слотов, старый отклоняется (401) |
| `make verify-security` | ~10 с | 17 проверок: non-root, read-only FS, NetworkPolicy, RBAC, шифрование Secret |
| `make status` | ~1 с | активный слот, версии, история решений |
| `make test-e2e` | ~11–13 мин | все 15 приёмочных сценариев подряд, итог `все сценарии пройдены` |

Отчёт каждого релиза — `.local/reports/release-*.md` (и `.json`): решение, причина, проверки,
метрики, длительности. Если команда завершилась не так, как в таблице, — `make status` и
`docs/troubleshooting.md`.

## 5. Веб-интерфейсы (Grafana, Prometheus, Alertmanager)

Стенд слушает только `127.0.0.1:8080` внутри ВМ — так безопаснее, наружу ничего не открыто.

**Ubuntu Desktop:** откройте браузер внутри ВМ.

**Ubuntu Server (ВМ без графики) — SSH-туннель с вашего компьютера:**

```bash
ssh -L 8080:127.0.0.1:8080 <пользователь>@<IP-адрес ВМ>
# VirtualBox с NAT и пробросом порта 2222 → 22:
ssh -p 2222 -L 8080:127.0.0.1:8080 <пользователь>@127.0.0.1
```

Пока туннель открыт, на своём компьютере откройте:

| Адрес | Что |
|---|---|
| http://grafana.localhost:8080 | Grafana, дашборд «MTS DevOps — демо-API: доступность, релизы, ресурсы» (логин `admin`, пароль — `make credentials` в ВМ) |
| http://prometheus.localhost:8080 | Prometheus: Status → Targets, Alerts |
| http://alertmanager.localhost:8080 | Alertmanager |
| http://127.0.0.1:8080/api/v1/tariffs | API |

Chrome, Firefox и Edge сами направляют `*.localhost` на `127.0.0.1`. Если браузер не открывает
адрес (например, Safari), добавьте на **своём** компьютере в файл hosts строку
`127.0.0.1 grafana.localhost prometheus.localhost alertmanager.localhost`
(Windows: `C:\Windows\System32\drivers\etc\hosts`, macOS/Linux: `/etc/hosts`).

## 6. Остановка, перезапуск ВМ, удаление

| Действие | Команда |
|---|---|
| удалить стенд, сохранить ключ и секреты | `make down` |
| удалить всё, включая age-ключ и SOPS-файл | `make down PURGE=1 CONFIRM=yes` |
| поднять заново | `make up` |
| после перезагрузки ВМ | контейнеры стенда запускаются вместе с Docker; через 1–2 минуты выполните `make verify` (при ошибках — `make up`) |

## 7. Частые проблемы на ВМ

| Симптом | Решение |
|---|---|
| `permission denied … /var/run/docker.sock` | группа `docker` ещё не действует: `newgrp docker` или перелогиньтесь |
| `make doctor`: мало RAM/CPU/диска | увеличьте ресурсы ВМ (раздел 1) |
| `toomanyrequests` (лимит Docker Hub) | `DOCKERHUB_MIRROR=https://mirror.gcr.io` в `.env` и зеркало для Docker хоста (`docs/troubleshooting.md`), затем `make down && make up` |
| `x509: certificate …` за корпоративным прокси | `EXTRA_CA_BUNDLE=/путь/к/ca-bundle.crt` в `.env` |
| `certificate is not yet valid` / ошибки TLS после паузы ВМ | сбились часы ВМ: `sudo timedatectl set-ntp true`, проверьте `date` |
| Docker установлен из snap | `make doctor` предупредит; рекомендуется `sudo snap remove docker && make prereqs` |
| порт 8080 на вашем компьютере занят (для туннеля) | в ВМ: `INGRESS_PORT=18080` в `.env`, `make down && make up`; туннель `ssh -L 18080:127.0.0.1:18080 …`, адреса `http://grafana.localhost:18080`. Номер порта по обе стороны туннеля должен совпадать: Grafana и Prometheus строят ссылки по нему |

## 8. Что проверено

| Окружение | Как | Результат |
|---|---|---|
| Ubuntu 24.04 x86_64, чистая ВМ | GitHub-hosted runner, `make doctor` → `make up` → 15 сценариев (`ci.yml`, job e2e) | см. `docs/validation/github-actions.md` |
| Ubuntu 22.04 x86_64, чистая ВМ | runner `ubuntu-22.04`: `make prereqs` → … → 15 сценариев (`compat.yml`) | см. `docs/validation/compat.md` |
| Ubuntu 24.04 aarch64 (arm64), чистая ВМ | runner `ubuntu-24.04-arm`: `make prereqs` → … → 15 сценариев | см. `docs/validation/compat.md` |
| Ubuntu 22.04 / 24.04 / 26.04 — пакеты и окружение | контейнер `ubuntu:<версия>` с Docker хоста: `make prereqs` ставит Docker CLI, buildx, Python из архивов Ubuntu; дальше полный путь | см. `docs/validation/compat.md` |

Не проверялось: настоящая ВМ с Ubuntu 26.04 (проверено окружение 26.04 в контейнере на ядре
Ubuntu 24.04), ВМ с 2 vCPU, WSL2.
