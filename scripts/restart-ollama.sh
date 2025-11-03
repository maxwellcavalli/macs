#!/usr/bin/env bash
set -Eeuo pipefail

# Use internal-only Ollama (no host port) so there's never a bind conflict.
# This file is created if it doesn't exist.
if [ ! -f docker-compose.ollama.nopublish.yml ]; then
  cat > docker-compose.ollama.nopublish.yml <<'YAML'
version: "3.9"
services:
  ollama:
    ports: []   # no host binding for 11434
  api:
    environment:
      - OLLAMA_HOST=http://ollama:11434
YAML
fi

# Compose files used by this project; add/remove as needed.
FILES=(
  -f docker-compose.yml
  -f docker-compose.override.yml
  -f docker-compose.local.yml
  -f docker-compose.local.hardening.yml
  -f docker-compose.local.asgilimit.yml
  -f docker-compose.ollama.nopublish.yml
)

# Profiles work across Compose v2 when set via env var.
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-core,pg}"

# Stop & remove ONLY the ollama container (volumes/images remain)
docker compose "${FILES[@]}" stop ollama || true
docker compose "${FILES[@]}" rm -f ollama || true

# Recreate api + ollama so env wiring takes effect
docker compose "${FILES[@]}" up -d --force-recreate api ollama

# Quick checks
docker compose "${FILES[@]}" ps
curl -fsS "http://127.0.0.1:${API_PORT:-8080}/v1/ollama/health" || true
