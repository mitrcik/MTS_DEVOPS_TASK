# Удалённый CD: GitHub Actions → постоянный стенд по SSH

> **Статус: реализовано в конфигурации, не проверено.** У команды на момент сдачи нет постоянного
> Ubuntu-хоста, доступного из GitHub. Job `deploy` в `.github/workflows/ci.yml` пропускается
> (`skipped`), пока не заданы переменные репозитория. Успешный ephemeral E2E в runner — это
> интеграционная проверка, а **не** доставка на постоянный стенд.

## Почему SSH, а не kubeconfig в workflow

GitHub-hosted runner не имеет сетевого доступа к кластеру на ноутбуке или в закрытой сети, а
передавать admin-kubeconfig в публичный workflow нельзя. Поэтому runner не управляет кластером
напрямую: он передаёт **проверенный артефакт** (provenance с digest и результатом Trivy) на
выделенный Ubuntu-хост, где работает тот же release controller (`bgctl release`) с ограниченными
правами в namespace `mts-app`.

```mermaid
sequenceDiagram
  participant GA as GitHub Actions (main)
  participant H as Ubuntu-стенд (deploy@host)
  participant K as k3s на стенде
  GA->>GA: image: build → Trivy → push в GHCR → provenance.json
  GA->>H: ssh -o StrictHostKeyChecking=yes deploy@host release < provenance.json
  H->>H: forced command deploy-gate.sh: только status|release, ≤64 КиБ JSON
  H->>H: bgctl: digest по схеме, trivy.result=passed, ALLOWED_IMAGE_REPOSITORY
  H->>K: blue-green релиз (Lease, preview, gate, откат) с deploy.kubeconfig
  H-->>GA: код решения (0 promoted, 2 rejected, 3 rolled_back …) → статус job
```

## Подготовка стенда (однократно, администратор хоста)

1. Ubuntu 24.04, Docker Engine, `git make curl python3-venv` (как в README).
2. Клонировать репозиторий в `/opt/mts-devops`, создать `.env`:
   ```bash
   CLUSTER_NAME=mts-devops
   ALLOWED_IMAGE_REPOSITORY=ghcr.io/<owner>/<repo>/mts-api
   ```
   и выполнить `make up` (поднимет стенд, создаст секреты и ограниченный `deploy.kubeconfig`).
3. Доступ узла k3s к GHCR: если пакет приватный — read-only токен (`read:packages`) в
   `registries.yaml` k3s (`configs."ghcr.io".auth`), либо сделать пакет публичным.
4. Пользователь `deploy` без пароля и shell-доступа, владелец только `.local/` проекта:
   `~deploy/.ssh/authorized_keys`:
   ```
   restrict,command="/opt/mts-devops/scripts/remote/deploy-gate.sh" ssh-ed25519 AAAA… github-actions-deploy
   ```
   `restrict` запрещает port-forwarding, X11, agent и PTY; forced command разрешает только
   `status` и `release < provenance.json`.
5. Отпечаток ключа хоста для `known_hosts`: `ssh-keyscan -t ed25519 host` — **сверить** с
   `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` на самом хосте.
6. Публичный доступ к UI не открывается: ingress остаётся на loopback; для внешнего доступа
   нужен TLS (Traefik `websecure` + сертификат) и отдельное решение по аутентификации.

## Настройка GitHub (однократно)

| Где | Имя | Значение |
|---|---|---|
| Settings → Environments | `production` | желательно required reviewers |
| Variables | `DEPLOY_HOST` | адрес стенда |
| Variables | `DEPLOY_USER` | `deploy` |
| Secrets (environment `production`) | `DEPLOY_SSH_KEY` | закрытый ключ ed25519 только для деплоя |
| Secrets (environment `production`) | `DEPLOY_KNOWN_HOSTS` | строка из шага 5 |

## Границы полномочий

- Runner: `contents: read`; не получает kubeconfig и не видит секреты приложения.
- `deploy@host`: одна forced command; release controller работает с `deploy.kubeconfig`
  (Role в `mts-app`, без exec, узлов и других namespace).
- Конкурирующие запуски: `concurrency: deploy-production` (cancel-in-progress: false) в GitHub
  и Lease-блокировка в самом кластере (защищает и от одновременного ручного релиза на стенде).
- Начатое переключение не прерывается новым коммитом.
