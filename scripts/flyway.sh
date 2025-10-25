#!/usr/bin/env bash
set -euo pipefail
[ -f .env.flyway ] && set -a && . ./.env.flyway && set +a

export FLYWAY_URL="jdbc:postgresql://${PGHOST:-db}:${PGPORT:-5432}/${PGDATABASE:-postgres}"
export FLYWAY_USER="${PGUSER:-postgres}"
export FLYWAY_PASSWORD="${PGPASSWORD:-postgres}"
export FLYWAY_LOCATIONS="filesystem:/flyway/sql"

CMD="${1:-info}"; shift || true

USE_NETWORK=""
if [[ -n "${FLYWAY_NETWORK:-}" ]]; then
  USE_NETWORK="--network ${FLYWAY_NETWORK}"
else
  if command -v docker compose >/dev/null 2>&1; then
    NET="$(docker compose ps -a --format '{{.Networks}}' 2>/dev/null | head -n1 | cut -d',' -f1)"
    [[ -n "$NET" ]] && USE_NETWORK="--network ${NET}"
  fi
fi

HOSTS_FLAG=""
if [[ "${OSTYPE:-}" == linux* ]]; then
  HOSTS_FLAG="--add-host=host.docker.internal:host-gateway"
fi

docker run --rm ${USE_NETWORK} ${HOSTS_FLAG} \
  -v "$(pwd)/db/migrations:/flyway/sql" \
  -e FLYWAY_URL -e FLYWAY_USER -e FLYWAY_PASSWORD -e FLYWAY_LOCATIONS \
  flyway/flyway:10.13 ${CMD} "$@"
