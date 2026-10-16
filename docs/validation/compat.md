# Совместимость с ВМ пользователя (workflow `compat.yml`)

Цель — подтвердить путь из [`docs/vm-guide.md`](../vm-guide.md) (`make prereqs` → `make doctor` →
`make up` → 15 приёмочных сценариев) за пределами основного профиля Ubuntu 24.04 x86_64. Основной
профиль проверяется на каждый push в `ci.yml` ([`github-actions.md`](github-actions.md)).

Окружения:

- **ВМ** — чистые ВМ GitHub Actions (`ubuntu-22.04`, `ubuntu-24.04-arm`). Команды те же, что у
  пользователя.
- **Окружение в контейнере** — контейнер `ubuntu:<версия>`, подключённый к Docker Engine runner
  (через сокет и `--network host`). `make prereqs` ставит Docker CLI, buildx, Python и остальное из
  архивов этой версии Ubuntu. Дальше весь путь идёт на её пакетах и её Python. Ядро и Docker Engine
  при этом от runner (Ubuntu 24.04). Поэтому это проверка пакетов и пользовательского окружения, а
  не настоящей ВМ этой версии.

## Прогон #5 — commit `a6703da` — все jobs зелёные

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38836825406

Повтор всей матрицы после исправлений по независимой перепроверке:

- строгий `set -e` в сценариях;
- `LC_ALL=C.UTF-8`;
- ключ PPA deadsnakes экспортируется в keyring только с закреплённым отпечатком;
- `--only-binary` для venv.

Все 6 jobs (`pins`, ВМ Ubuntu 22.04 x86_64, ВМ Ubuntu 24.04 aarch64, окружения Ubuntu
22.04/24.04/26.04) — ✅, в каждом окружении 15/15 сценариев.

## Прогон #4 — commit `e6bf26c` — все jobs зелёные

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38827448022

| Job | Окружение | `make prereqs` | `make up` (с нуля) | Сценарии | Итог |
|---|---|---|---|---|---|
| `pins` | Сверка sha256 всех CLI (amd64 и arm64) с официальными файлами checksum | — | — | — | ✅ 10 совпадений; age не публикует checksum (пропуск) |
| ВМ Ubuntu 22.04 x86_64 | runner `ubuntu-22.04`, системный Python 3.10, Docker CE предустановлен | ✅ 30 с, python3.12 из PPA deadsnakes (ключ сверен по отпечатку) | ✅ 3 мин 22 с | ✅ 15/15, 9 мин 09 с | ✅ |
| ВМ Ubuntu 24.04 aarch64 | runner `ubuntu-24.04-arm` (arm64), Docker CE предустановлен | ✅ 13 с | ✅ 3 мин 17 с | ✅ 15/15, 9 мин 38 с | ✅ |
| Ubuntu 22.04 в контейнере | `ubuntu:22.04`: docker.io 29.1.3 + docker-buildx 0.30.1 из Ubuntu, python3.12 из deadsnakes | ✅ | ✅ | ✅ 15/15 | ✅ 14 мин 21 с всего |
| Ubuntu 24.04 в контейнере | `ubuntu:24.04`: docker.io 29.1.3, Python 3.12.3 | ✅ | ✅ | ✅ 15/15 | ✅ 12 мин 21 с всего |
| Ubuntu 26.04 в контейнере | `ubuntu:26.04`: docker.io 29.1.3, Python 3.14.4 | ✅ | ✅ | ✅ 15/15 | ✅ 13 мин 20 с всего |

Сценарии на ВМ Ubuntu 24.04 aarch64 (прогон #3, по логу job; в прогоне #4 прошли те же 15):

| сценарий | результат | время, с |
|---|---|---|
| verify | passed | 1 |
| idempotent-up | passed | 14 |
| release (v2) | passed | 69 |
| not-ready | passed | 77 |
| not-ready-safe | passed | 1 |
| rollback | passed | 42 |
| rollback-safe | passed | 0 |
| interrupted | passed | 26 |
| no-metrics | passed | 28 |
| alert | passed | 57 |
| rotation-chain | passed | 48 |
| concurrency | passed | 74 |
| security | passed | 11 |
| down-up | passed | 133 |
| verify-again | passed | 0 |

## Прогон #3 — commit `0d78b73`

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38826688142

| Job | Результат | Что найдено и исправлено |
|---|---|---|
| `pins` | ✅ | В этом прогоне — ничего. В прогонах #1–#2 job `pins` нашёл ошибку: YAML читал заглушку sha256 из нулей как число. Исправление: все sha256 взяты в кавычки, добавлена офлайн-проверка `check-tools-file`. Также job выдал официальный sha256 Helm arm64 с get.helm.sh |
| ВМ Ubuntu 22.04 x86_64 | ✅ 15/15 (`make up` 3 мин 40 с) | — |
| ВМ Ubuntu 24.04 aarch64 | ✅ 15/15 (`make up` 3 мин 20 с) | — |
| Ubuntu 22.04 в контейнере | ❌ | `add-apt-repository` не импортировал ключ PPA в минимальном образе. Исправление: ключ загружается с keyserver.ubuntu.com и сверяется с отпечатком (`160c0e3`) |
| Ubuntu 24.04 / 26.04 в контейнере | ❌ | Ошибка в настройке самой проверки: checkout принадлежит пользователю runner, а в контейнере работает root, поэтому git отказал («dubious ownership»). Исправлено в workflow. Теперь `make doctor` явно сообщает о такой ситуации (запуск через sudo от другого пользователя) |

## Локальная проверка в среде разработки (Ubuntu 26.04, свежий клон)

Путь: `git clone` → `make prereqs` → `make doctor` → `make up` → `make test-e2e` в контейнере
`ubuntu:26.04` (Python 3.14.4, docker.io 29.1.3) на Docker среды разработки, commit `68a1df6`.

- `make up` — 206 с.
- Сценарии — **15/15 passed**.
- Пиковое использование памяти хоста за весь прогон — 2,2 ГиБ (по `free`, вместе с ≈ 0,8 ГиБ
  фоновой нагрузки среды).
- Место на диске после прогона — ≈ 9 ГБ всего: образы 2,4 ГБ, тома k3d (образы в узле, PV,
  registry) 3,3 ГБ, кэш сборки 0,7 ГБ, `.local` проекта 2,4 ГБ.

## Не проверено

- Настоящая ВМ с Ubuntu 26.04 (проверено окружение 26.04 в контейнере на ядре 24.04).
- Запуск daemon из пакета `docker.io` и шаг с группой `docker` и `newgrp` на настоящей ВМ. На ВМ
  GitHub Docker CE предустановлен, и `make prereqs` его не переустанавливал. В контейнерных
  проверках работал Docker хоста.
- ВМ с 2 vCPU или 4 ГБ RAM.
- WSL2.
- Docker из snap.
