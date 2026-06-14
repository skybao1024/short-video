#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
DEV_COMPOSE_FILE="${ROOT_DIR}/docker-compose.dev.yml"
ENV_FILE="${ROOT_DIR}/.env"
BACKEND_ENV_FILE="${ROOT_DIR}/backend/.env"
BACKEND_LOG_DIR="${ROOT_DIR}/backend/logs"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
RESET=$'\033[0m'

info() {
  printf '%s[INFO]%s %s\n' "${GREEN}" "${RESET}" "$*"
}

warn() {
  printf '%s[WARN]%s %s\n' "${YELLOW}" "${RESET}" "$*"
}

error() {
  printf '%s[ERROR]%s %s\n' "${RED}" "${RESET}" "$*" >&2
}

usage() {
  cat <<'EOF'
Usage: ./deploy.sh <command> [options] [service]

Commands:
  dev, up        Start development services
  build          Build service images
  stop, down     Stop all services
  restart        Restart running services
  logs [service] Follow logs, optionally for one service
  status, ps     Show service status
  migrate        Run Alembic migrations in the backend container
  config         Validate Docker Compose config without printing secrets

Options:
  --no-build     With dev/up, do not rebuild images
  --skip-migrate With dev/up, skip Alembic migrations
  -h, --help     Show this help
EOF
}

compose_bin() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    printf 'docker compose'
    return
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    printf 'docker-compose'
    return
  fi

  error "Docker Compose is not installed"
  exit 1
}

compose() {
  local compose_command
  compose_command="$(compose_bin)"

  if [[ -f "${DEV_COMPOSE_FILE}" ]]; then
    # shellcheck disable=SC2086
    ${compose_command} -f "${COMPOSE_FILE}" -f "${DEV_COMPOSE_FILE}" "$@"
  else
    # shellcheck disable=SC2086
    ${compose_command} -f "${COMPOSE_FILE}" "$@"
  fi
}

service_container_id() {
  compose ps -q "$1" 2>/dev/null | tail -n 1
}

service_status() {
  local service="$1"
  local container_id
  container_id="$(service_container_id "${service}")"

  if [[ -z "${container_id}" ]]; then
    printf 'missing'
    return
  fi

  docker inspect \
    --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
    "${container_id}" 2>/dev/null || printf 'unknown'
}

wait_for_service() {
  local service="$1"
  local timeout_seconds="${2:-60}"
  local elapsed=0
  local status

  info "Waiting for ${service} to be ready"
  while [[ "${elapsed}" -lt "${timeout_seconds}" ]]; do
    status="$(service_status "${service}")"
    if [[ "${status}" == "healthy" || "${status}" == "running" ]]; then
      info "${service} is ${status}"
      return 0
    fi

    sleep 2
    elapsed=$((elapsed + 2))
  done

  error "${service} did not become ready within ${timeout_seconds}s (last status: ${status})"
  return 1
}

run_with_retry() {
  local description="$1"
  local attempts="$2"
  local delay_seconds="$3"
  shift 3

  local attempt=1
  local status=0
  while [[ "${attempt}" -le "${attempts}" ]]; do
    if "$@"; then
      return 0
    fi

    status=$?
    if [[ "${attempt}" -eq "${attempts}" ]]; then
      error "${description} failed after ${attempts} attempts"
      return "${status}"
    fi

    warn "${description} failed (attempt ${attempt}/${attempts}), retrying in ${delay_seconds}s"
    sleep "${delay_seconds}"
    attempt=$((attempt + 1))
  done
}

prepare_runtime_files() {
  mkdir -p "${BACKEND_LOG_DIR}"

  if [[ ! -f "${ENV_FILE}" ]]; then
    warn "Root .env not found; Docker Compose defaults from docker-compose.yml will be used"
    return
  fi

  if [[ -L "${BACKEND_ENV_FILE}" && -e "${BACKEND_ENV_FILE}" ]]; then
    return
  fi

  if [[ -e "${BACKEND_ENV_FILE}" && ! -L "${BACKEND_ENV_FILE}" ]]; then
    warn "backend/.env already exists and is not a symlink; leaving it untouched"
    return
  fi

  if [[ -L "${BACKEND_ENV_FILE}" && ! -e "${BACKEND_ENV_FILE}" ]]; then
    rm "${BACKEND_ENV_FILE}"
  fi

  ln -s ../.env "${BACKEND_ENV_FILE}"
  info "Created backend/.env -> ../.env"
}

run_migrations() {
  info "Running database migrations"
  wait_for_service postgres 60
  wait_for_service backend 90

  if ! run_with_retry "Database migration" 3 5 compose exec -T backend alembic upgrade head; then
    error "Migration failed. Check the Alembic output above for the concrete error."
    return 1
  fi
}

get_first_published_port() {
  local service="$1"
  local container_id
  container_id="$(service_container_id "${service}")"
  if [[ -z "${container_id}" ]]; then
    return
  fi

  docker inspect \
    --format '{{range $containerPort, $bindings := .NetworkSettings.Ports}}{{range $bindings}}{{println .HostPort}}{{end}}{{end}}' \
    "${container_id}" 2>/dev/null | head -n 1
}

get_published_port() {
  local service="$1"
  local container_port="$2"
  local container_id
  container_id="$(service_container_id "${service}")"
  if [[ -z "${container_id}" ]]; then
    return
  fi

  docker inspect \
    --format "{{(index (index .NetworkSettings.Ports \"${container_port}/tcp\") 0).HostPort}}" \
    "${container_id}" 2>/dev/null || true
}

print_dev_urls() {
  local frontend_port
  local backend_port
  local minio_console_port

  frontend_port="$(get_first_published_port frontend)"
  backend_port="$(get_first_published_port backend)"
  minio_console_port="$(get_published_port minio 9001)"

  info "Development deployment complete"
  if [[ -n "${frontend_port}" ]]; then
    info "Frontend: http://localhost:${frontend_port}"
  fi
  if [[ -n "${backend_port}" ]]; then
    info "Backend API: http://localhost:${backend_port}/api/v1/"
    info "API health: http://localhost:${backend_port}/api/v1/config/health"
  fi
  if [[ -n "${minio_console_port}" ]]; then
    info "MinIO Console: http://localhost:${minio_console_port}"
  fi
}

deploy_dev() {
  local build=true
  local skip_migrate=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-build)
        build=false
        shift
        ;;
      --skip-migrate)
        skip_migrate=true
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        error "Unknown dev option: $1"
        usage
        exit 1
        ;;
    esac
  done

  info "Deploying development environment"
  prepare_runtime_files

  local up_args=(up -d --remove-orphans)
  if [[ "${build}" == "true" ]]; then
    up_args+=(--build)
  fi

  run_with_retry "Start development services" 3 10 compose "${up_args[@]}"

  if [[ "${skip_migrate}" != "true" ]]; then
    run_migrations
  fi

  print_dev_urls
}

main() {
  if [[ ! -f "${COMPOSE_FILE}" ]]; then
    error "Compose file not found: ${COMPOSE_FILE}"
    exit 1
  fi

  local command="${1:-}"
  if [[ -z "${command}" || "${command}" == "-h" || "${command}" == "--help" ]]; then
    usage
    exit 0
  fi
  shift || true

  case "${command}" in
    dev|up)
      deploy_dev "$@"
      ;;
    build)
      info "Building services"
      prepare_runtime_files
      compose build "$@"
      ;;
    stop|down)
      info "Stopping services"
      compose down "$@"
      ;;
    restart)
      info "Restarting services"
      compose restart "$@"
      ;;
    logs)
      compose logs -f "$@"
      ;;
    status|ps)
      info "Service status"
      compose ps "$@"
      ;;
    migrate)
      run_migrations
      ;;
    config)
      compose config --quiet "$@"
      ;;
    *)
      error "Unknown command: ${command}"
      usage
      exit 1
      ;;
  esac
}

main "$@"
