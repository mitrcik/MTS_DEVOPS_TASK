# Совместимость с ВМ пользователя (workflow `compat.yml`)

Цель — подтвердить путь из [`docs/vm-guide.md`](../vm-guide.md) (`make prereqs` → `make doctor` →
`make up` → 15 приёмочных сценариев) за пределами основного профиля Ubuntu 24.04 x86_64.

## Прогон #3 — commit `0d78b73` (идёт)

Run: https://github.com/mitrcik/MTS_DEVOPS_TASK/actions/runs/38826688142

| Job | Окружение | Результат на момент записи |
|---|---|---|
| `pins` | sha256 всех CLI (amd64 и arm64) против официальных файлов checksum | ✅ 10 совпадений; age — без файла checksum (пропуск) |
| ВМ Ubuntu 22.04 x86_64 | чистый runner `ubuntu-22.04` | `make prereqs` ✅ (python3.12 из PPA deadsnakes), `make doctor` ✅, `make up` ✅ 3 мин 40 с; сценарии — выполняются |
| ВМ Ubuntu 24.04 aarch64 | чистый runner `ubuntu-24.04-arm` | `make prereqs` ✅, `make doctor` ✅, `make up` ✅ 3 мин 20 с; сценарии — выполняются |
| окружение 22.04 в контейнере | `ubuntu:22.04` + Docker runner'а | ❌ `add-apt-repository` не импортировал ключ PPA в минимальном образе → заменён на загрузку ключа с проверкой отпечатка (`160c0e3`) |
| окружения 24.04 / 26.04 в контейнере | `ubuntu:24.04`, `ubuntu:26.04` + Docker runner'а | ❌ ошибка стенда проверки: checkout принадлежит пользователю runner, а в контейнере root — git отказал («dubious ownership»); исправлено в workflow (`safe.directory`, возврат владельца `.local`); doctor теперь явно сообщает о такой ситуации |

Результаты будут дополнены по завершении прогона и следующего прогона с исправлениями.
