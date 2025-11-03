#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

exec docker compose -f "${ROOT_DIR}/docker-compose.yml" run --rm flyway \
  -url=jdbc:postgresql://postgres:5432/agent \
  -user=agent \
  -password=agent \
  -locations=filesystem:/flyway/sql \
  -connectRetries=60 \
  migrate
