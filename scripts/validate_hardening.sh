#!/usr/bin/env bash
set -euxo pipefail
API_URL="${API_URL:-http://localhost:8080}"
SERVICE="${SERVICE:-api}"
LIMIT_BYTES="${MACS_MAX_BODY_BYTES:-1024}"   # tiny limit for test
TOO_BIG=$((LIMIT_BYTES + 512))
API_KEY="${API_KEY:-$("./scripts/resolve_api_key.sh" 2>/dev/null || true)}"
: "${API_KEY:=dev-local}"

# Compose stack: base + any locals + our asgi-limit overlay
CF="docker-compose.yml"
[ -f docker-compose.override.yml ] && CF="$CF:docker-compose.override.yml"
[ -f docker-compose.local.yml ]    && CF="$CF:docker-compose.local.yml"
CF="$CF:docker-compose.local.asgilimit.yml"
export COMPOSE_FILE="$CF"
export MACS_MAX_BODY_BYTES="$LIMIT_BYTES"

echo "==> Rebuild & start $SERVICE (MACS_MAX_BODY_BYTES=$LIMIT_BYTES, factory serve)"
docker compose build "$SERVICE"
docker compose up -d "$SERVICE"

echo "==> Wait for health"
for i in {1..60}; do curl -sf "$API_URL/v1/ollama/health" >/dev/null && break; sleep 1; done

# Build a schema-valid but oversized body; limiter should 413 before validation
PAY="$(mktemp)"
python3 - <<PY >"$PAY"
n = $TOO_BIG
pad = "a" * max(n - 220, 0)
body = {"type":"CODE","input":{"language":{"name":"python"},"repo":{"url":"dummy"},"constraints":{"list":[]},"goal":{"text":"test"},"pad": pad}}
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

if [ "$CODE" != "413" ]; then
  echo "Expected 413, got $CODE"
  echo "--- response headers ---"; sed -n '1,80p' "$HDR" || true
  echo "--- last logs ---"; docker compose logs --no-color "$SERVICE" | tail -n 200 || true
  exit 1
fi
grep -q '"request_too_large"' "$BODY"
echo "✔ 413 enforced by ASGI wrapper via factory"
rm -f "$PAY" "$HDR" "$BODY"
