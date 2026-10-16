#!/usr/bin/env bash
# Стадии CI. Один и тот же скрипт вызывают `make ci`, `make release` и GitHub Actions.
#
#   scripts/ci.sh [стадия ...]      стадии: lint test validate build scan push | all
#
# Параметры (окружение):
#   VERSION      версия сборки (по умолчанию INITIAL_VERSION из .env)
#   FAULT        учебный режим неисправности: none | not-ready | errors-behind-ingress
#   REGISTRY     куда публиковать (по умолчанию localhost:$REGISTRY_PORT — registry стенда)
#   IMAGE_NAME   имя образа (mts-api)
# Результаты: .local/artifacts/<tag>/ (provenance.json, trivy.json, trivy.txt).
# Последняя строка stdout стадии push — путь к provenance.json.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
load_env
# Весь вывод стадий — в stderr; в stdout только путь к provenance (его читает release.sh).
exec 3>&1 1>&2
cd "${ROOT_DIR}"

VERSION="${VERSION:-${INITIAL_VERSION:-v1}}"
FAULT="${FAULT:-none}"
REGISTRY="${REGISTRY:-localhost:${REGISTRY_PORT}}"
IMAGE_NAME="${IMAGE_NAME:-mts-api}"
GIT_SHA="$(git_sha)"
[[ "$(git_dirty)" == "true" ]] && GIT_SHA="${GIT_SHA}-dirty"
TAG="${GIT_SHA}-${VERSION}"
[[ "${FAULT}" != "none" ]] && TAG="${TAG}-fault-${FAULT}"
IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
ART="${LOCAL_DIR}/artifacts/${TAG}"
PY="$(venv_python)"
HELPER=("${PY}" "${ROOT_DIR}/scripts/cihelper.py")
mkdir -p "${ART}"

[[ "${VERSION}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$ ]] || die "некорректная VERSION=${VERSION}"
case "${FAULT}" in none|not-ready|errors-behind-ingress) ;; *) die "некорректный FAULT=${FAULT}";; esac

stage_begin() { STAGE="$1"; STAGE_T0=$(date +%s); log "━━ стадия ${STAGE} ━━"; }
stage_end() {
  local dt=$(( $(date +%s) - STAGE_T0 ))
  "${HELPER[@]}" stage "${ART}/stages.json" "${STAGE}" passed "${dt}"
  ok "стадия ${STAGE}: passed (${dt} с)"
}
on_exit() {
  local rc=$?
  if [[ -n "${STAGE:-}" && ${rc} -ne 0 ]]; then
    "${HELPER[@]}" stage "${ART}/stages.json" "${STAGE}" failed 0 || true
    err "стадия ${STAGE} не пройдена (код ${rc})"
  fi
}
trap on_exit EXIT

docker_secret_args() {
  if [[ -n "${EXTRA_CA_BUNDLE:-}" ]]; then printf '%s\n' --secret "id=extra_ca,src=${EXTRA_CA_BUNDLE}"; fi
}

# ---------------------------------------------------------------- стадии
stage_lint() {
  stage_begin lint
  "${LOCAL_DIR}/venv/bin/ruff" check "${ROOT_DIR}/app" "${ROOT_DIR}/scripts"
  "${LOCAL_DIR}/venv/bin/ruff" format --check "${ROOT_DIR}/app" "${ROOT_DIR}/scripts"
  (cd "${ROOT_DIR}" && "${LOCAL_DIR}/venv/bin/yamllint" -c .yamllint.yml .)
  docker run --rm -v "${ROOT_DIR}:/src:ro" -w /src "${SHELLCHECK_IMAGE}" -x -P SCRIPTDIR -S warning \
    scripts/*.sh scripts/remote/*.sh
  # секреты и ключи не должны попадать в Git
  "${HELPER[@]}" check-tracked-files "${ROOT_DIR}"
  trivy fs --quiet --skip-version-check --disable-telemetry --cache-dir "${LOCAL_DIR}/cache/trivy" --scanners secret --exit-code 1 \
    --skip-dirs .local --skip-dirs .git "${ROOT_DIR}"
  stage_end
}

stage_test() {
  stage_begin test
  local build=(docker build --quiet --pull --target test -t "mts-api-test:${TAG}" -f "${ROOT_DIR}/app/Dockerfile"
               --build-arg "PYTHON_IMAGE=${PYTHON_IMAGE}")
  mapfile -t sec < <(docker_secret_args)
  "${build[@]}" "${sec[@]}" "${ROOT_DIR}/app" >/dev/null
  docker run --rm --read-only --tmpfs /tmp --user 10001 -e PYTHONDONTWRITEBYTECODE=1 \
    "mts-api-test:${TAG}" pytest -p no:cacheprovider -q
  # unit-тесты логики gate release controller'а (stdlib unittest)
  "${PY}" -m unittest discover -s "${ROOT_DIR}/scripts/tests" -t "${ROOT_DIR}/scripts" -q
  stage_end
}

stage_validate() {
  stage_begin validate
  helm lint --strict "${ROOT_DIR}/charts/app" -f "${ROOT_DIR}/charts/app/ci/lint-values.yaml"
  helm lint --strict "${ROOT_DIR}/charts/traffic" -f "${ROOT_DIR}/charts/traffic/ci/lint-values.yaml"
  helm lint --strict "${ROOT_DIR}/charts/platform"
  helm lint --strict "${ROOT_DIR}/observability"
  # схема values не пропускает тег вместо digest и неизвестный слот
  if helm template x "${ROOT_DIR}/charts/app" -f "${ROOT_DIR}/charts/app/ci/lint-values.yaml" \
       --set image.digest=latest >/dev/null 2>&1; then
    die "values.schema.json чарта app пропустил образ без digest"
  fi
  local render="${ART}/render"
  mkdir -p "${render}"
  helm template mts-observability "${ROOT_DIR}/observability" -n monitoring > "${render}/observability.yaml"
  "${HELPER[@]}" extract-configmap "${render}/observability.yaml" prometheus-config prometheus.yml > "${render}/prometheus.yml"
  cp "${ROOT_DIR}/observability/files/rules/"*.yml "${render}/"
  docker run --rm -v "${render}:/etc/prometheus:ro" --entrypoint promtool "${PROMETHEUS_IMAGE}" \
    check config --syntax-only /etc/prometheus/prometheus.yml
  docker run --rm -v "${ROOT_DIR}/observability:/w:ro" --entrypoint promtool "${PROMETHEUS_IMAGE}" \
    check rules /w/files/rules/mts-api.rules.yml
  docker run --rm -v "${ROOT_DIR}/observability:/w:ro" -w /w/tests --entrypoint promtool "${PROMETHEUS_IMAGE}" \
    test rules rules.test.yml
  docker run --rm -v "${ROOT_DIR}/observability/files:/w:ro" --entrypoint amtool "${ALERTMANAGER_IMAGE}" \
    check-config /w/alertmanager.yml
  "${HELPER[@]}" check-dashboards "${ROOT_DIR}/observability/files/dashboards"
  "${HELPER[@]}" check-trivyignore "${ROOT_DIR}/.trivyignore.yaml"
  "${HELPER[@]}" check-tools-file "${ROOT_DIR}/infra/tools/tools.yml"
  stage_end
}

stage_build() {
  stage_begin build
  local build_time
  build_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker pull --quiet "${PYTHON_IMAGE}" >/dev/null
  local base_digest
  base_digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "${PYTHON_IMAGE}" 2>/dev/null || echo "${PYTHON_IMAGE}")"
  mapfile -t sec < <(docker_secret_args)
  docker build --quiet --target runtime -f "${ROOT_DIR}/app/Dockerfile" \
    --build-arg "PYTHON_IMAGE=${PYTHON_IMAGE}" \
    --build-arg "APP_VERSION=${VERSION}" \
    --build-arg "GIT_SHA=${GIT_SHA}" \
    --build-arg "BUILD_TIME=${build_time}" \
    --build-arg "APP_FAULT_MODE=${FAULT}" \
    "${sec[@]}" -t "${IMAGE}" "${ROOT_DIR}/app" >/dev/null
  local image_id
  image_id="$(docker image inspect --format '{{.Id}}' "${IMAGE}")"
  "${HELPER[@]}" build-record "${ART}/build.json" image_tag="${IMAGE}" local_id="${image_id}" \
    build_time="${build_time}" base_image="${base_digest}" version="${VERSION}" git_sha="${GIT_SHA}" \
    fault_mode="${FAULT}" docker="$(docker version --format '{{.Server.Version}}')"
  ok "собран ${IMAGE} (${image_id:0:19}…)"
  stage_end
}

stage_scan() {
  stage_begin scan
  local image_id
  image_id="$("${HELPER[@]}" get "${ART}/build.json" local_id)"
  [[ "$(docker image inspect --format '{{.Id}}' "${IMAGE}")" == "${image_id}" ]] \
    || die "тег ${IMAGE} указывает не на собранный образ — сканирование отменено"
  # Сканер и база обязательны: ошибка Trivy (нет базы, нет сети) = провал стадии, а не «чисто».
  trivy image --quiet --skip-version-check --disable-telemetry --cache-dir "${LOCAL_DIR}/cache/trivy" \
    --scanners vuln,secret --ignorefile "${ROOT_DIR}/.trivyignore.yaml" \
    --format json --output "${ART}/trivy.json" --exit-code 0 "${IMAGE}"
  trivy convert --scanners vuln,secret --format table --output "${ART}/trivy.txt" "${ART}/trivy.json"
  trivy version --cache-dir "${LOCAL_DIR}/cache/trivy" --format json > "${ART}/trivy-version.json"
  # Политика: блокируют HIGH/CRITICAL с доступным исправлением и любые найденные секреты.
  "${HELPER[@]}" trivy-policy "${ART}/trivy.json" "${ART}/trivy-version.json" "${ART}/trivy-summary.json"
  stage_end
}

stage_push() {
  stage_begin push
  local image_id
  image_id="$("${HELPER[@]}" get "${ART}/build.json" local_id)"
  [[ "$(docker image inspect --format '{{.Id}}' "${IMAGE}")" == "${image_id}" ]] \
    || die "тег ${IMAGE} изменился после сканирования — публикация отменена"
  "${HELPER[@]}" require-passed "${ART}/trivy-summary.json"
  if [[ "${REGISTRY}" == localhost:* ]] \
     && ! curl -fsS -o /dev/null --max-time 5 --noproxy '*' "http://127.0.0.1:${REGISTRY#localhost:}/v2/"; then
    die "registry стенда ${REGISTRY} недоступен: стадии push нужен работающий стенд (make up); без стенда — scripts/ci.sh lint test validate build scan"
  fi
  docker push --quiet "${IMAGE}" >/dev/null
  local digest
  digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "${IMAGE}" \
            | grep "^${REGISTRY}/${IMAGE_NAME}@" | head -1 | cut -d@ -f2)"
  [[ "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]] || die "не удалось получить digest после push"
  if [[ "${REGISTRY}" == localhost:* ]]; then
    # перекрёстная проверка: что реально отдаёт registry по этому тегу
    local remote
    remote="$(curl -fsS -o /dev/null -D - --noproxy '*' \
      -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json' \
      "http://127.0.0.1:${REGISTRY#localhost:}/v2/${IMAGE_NAME}/manifests/${TAG}" \
      | tr -d '\r' | awk -F': ' 'tolower($1)=="docker-content-digest"{print $2}')"
    [[ "${remote}" == "${digest}" ]] || die "registry отдаёт ${remote}, ожидался ${digest}"
  fi
  "${HELPER[@]}" provenance "${ART}" "${REGISTRY}/${IMAGE_NAME}@${digest}" "${digest}"
  ok "опубликован ${REGISTRY}/${IMAGE_NAME}@${digest}"
  stage_end
  echo "${ART}/provenance.json" >&3
}

stages=("$@")
[[ ${#stages[@]} -eq 0 || "${stages[0]}" == "all" ]] && stages=(lint test validate build scan push)
log "CI: версия ${VERSION}, git ${GIT_SHA}, образ ${IMAGE}, неисправность ${FAULT}"
# новый артефакт начинается со сборки: прежний учёт стадий для этого тега сбрасывается
if [[ " ${stages[*]} " == *" build "* || " ${stages[*]} " == *" lint "* ]]; then rm -f "${ART}/stages.json"; fi
for s in "${stages[@]}"; do
  case "${s}" in
    lint|test|validate|build|scan|push) "stage_${s}" ;;
    *) die "неизвестная стадия ${s}" ;;
  esac
done
STAGE=""
