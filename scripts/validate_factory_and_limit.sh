#!/usr/bin/env bash
set -euxo pipefail
API_URL="${API_URL:-http://localhost:8080}"
SERVICE="${SERVICE:-api}"
LIMIT_BYTES="${MACS_MAX_BODY_BYTES:-1024}"   # tiny limit to trigger
TOO_BIG=$((LIMIT_BYTES + 512))
API_KEY="${API_KEY:-$("./scripts/resolve_api_key.sh" 2>/dev/null || true)}"; : "${API_KEY:=dev-local}"

# Compose stack with the factory overlay
CF="docker-compose.yml"
[ -f docker-compose.override.yml ] && CF="$CF:docker-compose.override.yml"
[ -f docker-compose.local.yml ]    && CF="$CF:docker-compose.local.yml"
CF="$CF:docker-compose.local.asgilimit.yml"
export COMPOSE_FILE="$CF"
export MACS_MAX_BODY_BYTES="$LIMIT_BYTES"

echo "==> Build & run (factory mode, limit=$LIMIT_BYTES)"
docker compose build "$SERVICE"
docker compose up -d "$SERVICE"

echo "==> Check factory inside container"
CID="$(docker compose ps -q "$SERVICE")"
docker exec "$CID" sh -lc 'python3 - <<PY
import importlib; m=importlib.import_module("app.main")
print("has_create_app:", hasattr(m,"create_app"))
PY'

echo "==> Wait for health"
for i in {1..60}; do curl -sf "$API_URL/v1/ollama/health" >/dev/null && break; sleep 1; done

# Oversized but schema-valid body (fields shaped as objects to satisfy pydantic)
PAY="$(mktemp)"
python3 - <<PY >"$PAY"
n = $TOO_BIG
pad = "a" * max(n - 260, 0)
body = {
  "type": "CODE",
  "input": {
    "language": {"name": "python"},
    "repo": {"url": "dummy"},
    "constraints": {"list": []},
    "goal": {"text": "test"},
    "pad": pad
  }
}
import json; print(json.dumps(body))
PY
SZ=$(wc -c <"$PAY" | tr -d '[:space:]'); echo "Payload bytes: $SZ (limit: $LIMIT_BYTES)"

HDR="$(mktemp)"; BODY="$(mktemp)"; set +e
curl -sS -D "$HDR" -o "$BODY" \
  -H 'content-type: application/json' \
  -H "x-api-key: ${API_KEY}" \
  --data-binary @"$PAY" \
  -X POST "${API_URL}/v1/tasks"
CODE=$(awk 'BEGIN{IGNORECASE=1}/^HTTP/{c=$2}END{print c}' "$HDR")
set -e
echo "--- status: $CODE"; sed -n '1,120p' "$BODY" || true
test "$CODE" = "413" || { echo "Expected 413, got $CODE"; sed -n '1,80p' "$HDR" || true; exit 1; }
grep -q '"request_too_large"' "$BODY"
echo "✔ 413 enforced by outer ASGI limiter"
rm -f "$PAY" "$HDR" "$BODY"
