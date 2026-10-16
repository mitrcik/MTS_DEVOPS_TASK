# Совместимость с ВМ пользователя (workflow `compat.yml`)

Цель — подтвердить путь из [`docs/vm-guide.md`](../vm-guide.md) (`make prereqs` → `make doctor` →
`make up` → 15 приёмочных сценариев) за пределами основного профиля Ubuntu 24.04 x86_64, который
проверяется на каждый push в `ci.yml` (`github-actions.md`).

Окружения:

- **ВМ** — чистые GitHub-hosted ВМ (`ubuntu-22.04`, `ubuntu-24.04-arm`), команды как у пользователя.
- **Окружение в контейнере** — `ubuntu:<версия>` с Docker Engine runner'а (сокет и `--network host`):
  `make prereqs` ставит Docker CLI, buildx, Python и остальное из архивов этой версии Ubuntu, дальше
  весь путь идёт её пакетами и её Python. Ядро и Docker Engine — runner'а (Ubuntu 24.04), поэтому
  это проверка пакетов и пользовательского окружения, а не настоящей ВМ этой версии.

## Прогон #5 — commit `a6703da` — все jobs зелёные

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38836825406

Повтор всей матрицы после исправлений по независимой перепроверке: строгий `set -e` в сценариях,
`LC_ALL=C.UTF-8`, ключ PPA deadsnakes экспортируется в keyring только с закреплённым отпечатком,
`--only-binary` для venv. Все 6 jobs (`pins`, ВМ Ubuntu 22.04 x86_64, ВМ Ubuntu 24.04 aarch64,
окружения Ubuntu 22.04/24.04/26.04) — ✅, в каждом окружении 15/15 сценариев.

## Прогон #4 — commit `e6bf26c` — все jobs зелёные

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38827448022

| Job | Окружение | `make prereqs` | `make up` (с нуля) | Сценарии | Итог |
|---|---|---|---|---|---|
| `pins` | sha256 всех CLI (amd64 и arm64) против официальных файлов checksum | — | — | — | ✅ 10 совпадений; age не публикует checksum (пропуск) |
| ВМ Ubuntu 22.04 x86_64 | runner `ubuntu-22.04`, системный Python 3.10, Docker CE предустановлен | ✅ 30 с, python3.12 из PPA deadsnakes (ключ сверен по отпечатку) | ✅ 3 мин 22 с | ✅ 15/15, 9 мин 09 с | ✅ |
| ВМ Ubuntu 24.04 aarch64 | runner `ubuntu-24.04-arm` (arm64), Docker CE предустановлен | ✅ 13 с | ✅ 3 мин 17 с | ✅ 15/15, 9 мин 38 с | ✅ |
| Ubuntu 22.04 в контейнере | `ubuntu:22.04`: docker.io 29.1.3 + docker-buildx 0.30.1 из Ubuntu, python3.12 из deadsnakes | ✅ | ✅ | ✅ 15/15 | ✅ 14 мин 21 с всего |
| Ubuntu 24.04 в контейнере | `ubuntu:24.04`: docker.io 29.1.3, Python 3.12.3 | ✅ | ✅ | ✅ 15/15 | ✅ 12 мин 21 с всего |
| Ubuntu 26.04 в контейнере | `ubuntu:26.04`: docker.io 29.1.3, Python 3.14.4 | ✅ | ✅ | ✅ 15/15 | ✅ 13 мин 20 с всего |

Сценарии на ВМ Ubuntu 24.04 aarch64 (прогон #3, из лога job; в прогоне #4 — те же 15 passed):

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
| `pins` | ✅ | — (в прогонах #1–#2 job `pins` нашёл: YAML читал заглушку sha256 из нулей как число → все sha256 в кавычках и офлайн-проверка `check-tools-file`; дал официальный sha256 Helm arm64 с get.helm.sh) |
| ВМ Ubuntu 22.04 x86_64 | ✅ 15/15 (`make up` 3 мин 40 с) | — |
| ВМ Ubuntu 24.04 aarch64 | ✅ 15/15 (`make up` 3 мин 20 с) | — |
| Ubuntu 22.04 в контейнере | ❌ | `add-apt-repository` не импортировал ключ PPA в минимальном образе → ключ загружается с keyserver.ubuntu.com и сверяется с отпечатком (`160c0e3`) |
| Ubuntu 24.04 / 26.04 в контейнере | ❌ | ошибка стенда проверки: checkout принадлежит пользователю runner, в контейнере root — git отказал («dubious ownership»). Исправлено в workflow; `make doctor` теперь явно сообщает о такой ситуации (запуск через sudo от другого пользователя) |

## Локальная проверка в среде разработки (Ubuntu 26.04, свежий клон)

`git clone` → `make prereqs` → `make doctor` → `make up` → `make test-e2e` в `ubuntu:26.04`
(Python 3.14.4, docker.io 29.1.3) на Docker среды разработки, commit `68a1df6`:
`make up` 206 с, **15/15 сценариев passed**. Пиковое использование памяти хоста за весь прогон —
2,2 ГиБ (`free`, вместе с ≈ 0,8 ГиБ фоновой нагрузки среды); место после прогона — образы 2,4 ГБ,
тома k3d (образы в узле, PV, registry) 3,3 ГБ, кэш сборки 0,7 ГБ, `.local` проекта 2,4 ГБ
(≈ 9 ГБ всего).

## Не проверено

Настоящая ВМ с Ubuntu 26.04 (проверено окружение 26.04 в контейнере на ядре 24.04); запуск daemon из
пакета `docker.io` и шаг с группой `docker`/`newgrp` на настоящей ВМ (на ВМ GitHub Docker CE
предустановлен — `make prereqs` его не переустанавливал; в контейнерных проверках работал Docker хоста);
ВМ с 2 vCPU или 4 ГБ RAM, WSL2, Docker из snap.
