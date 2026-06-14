#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-}"

case "$TARGET" in
  test)
    DEPLOY_DIR="/opt/scopeslab-api"
    COMPOSE_PROJECT="scopeslab-api-test"
    API_PORT="8110"
    ;;
  test-sg)
    DEPLOY_DIR="/opt/scopeslab-api-test-sg"
    COMPOSE_PROJECT="scopeslab-api-test-sg"
    API_PORT="8111"
    ;;
  prod-eu)
    DEPLOY_DIR="/opt/scopeslab-api"
    COMPOSE_PROJECT="scopeslab-api-prod-eu"
    API_PORT="8100"
    ;;
  prod-sg)
    DEPLOY_DIR="/opt/scopeslab-api"
    COMPOSE_PROJECT="scopeslab-api-prod-sg"
    API_PORT="8101"
    ;;
  *)
    echo "Usage: $0 test|test-sg|prod-eu|prod-sg" >&2
    exit 2
    ;;
esac

if [[ ! "$DEPLOY_DIR" == /opt/scopeslab-api* ]]; then
  echo "Refusing to deploy outside /opt/scopeslab-api*: $DEPLOY_DIR" >&2
  exit 3
fi

if [[ ! -d "$DEPLOY_DIR" ]]; then
  echo "Deploy directory does not exist: $DEPLOY_DIR" >&2
  exit 4
fi

if [[ ! -f "$DEPLOY_DIR/.env" ]]; then
  echo "Missing $DEPLOY_DIR/.env. Create it on the server before deploying." >&2
  exit 5
fi

echo "Deploying $TARGET to $DEPLOY_DIR"
echo "Compose project: $COMPOSE_PROJECT"
echo "Expected API port: $API_PORT"

rsync -az --delete \
  --exclude ".git/" \
  --exclude ".github/" \
  --exclude ".env" \
  --exclude ".env.*" \
  --exclude ".venv/" \
  --exclude ".pytest_cache/" \
  --exclude "__pycache__/" \
  --exclude "logs/" \
  --exclude "celerybeat-schedule.db" \
  ./ "$DEPLOY_DIR/"

mkdir -p "$DEPLOY_DIR/logs"

cd "$DEPLOY_DIR"

docker compose -p "$COMPOSE_PROJECT" --env-file .env config >/tmp/scopeslab-api-compose-"$TARGET".yaml
docker compose -p "$COMPOSE_PROJECT" --env-file .env up -d --build app
docker compose -p "$COMPOSE_PROJECT" --env-file .env ps

echo "Waiting for health check..."
for attempt in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/config/health" >/tmp/scopeslab-api-health-"$TARGET".json; then
    cat /tmp/scopeslab-api-health-"$TARGET".json
    echo
    echo "Deploy succeeded: $TARGET"
    exit 0
  fi
  sleep 2
done

echo "Health check failed for $TARGET on port $API_PORT" >&2
docker compose -p "$COMPOSE_PROJECT" --env-file .env logs --tail 100 app >&2
exit 6
