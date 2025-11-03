#!/usr/bin/env bash
set -euxo pipefail

API_URL="${API_URL:-http://localhost:8080}"
SERVICE="${SERVICE:-api}"

echo "==> Rebuild & start $SERVICE"
docker compose build "$SERVICE"
docker compose up -d "$SERVICE"

echo "==> Wait for health at $API_URL/v1/ollama/health"
for i in {1..60}; do
  if curl -sf "$API_URL/v1/ollama/health" >/dev/null; then
    echo "health: OK"
    break
  fi
  sleep 1
  if [ $i -eq 60 ]; then
    echo "health: FAIL (timeout)"; docker compose logs --no-color "$SERVICE" | tail -n 200; exit 1
  fi
done

echo "==> Check OTel headers"
HDR="$(mktemp)"
curl -sS -D "$HDR" -o /dev/null "$API_URL/v1/ollama/health"
echo "--- response headers ---"
sed -n '1,50p' "$HDR"
echo "------------------------"
grep -i '^x-otel-enabled:' "$HDR"
grep -i '^x-trace-id:' "$HDR"
TRACE_ID="$(awk -F': ' 'BEGIN{IGNORECASE=1}/^x-trace-id:/{print $2; exit}' "$HDR" | tr -d '\r')"
rm -f "$HDR"

echo "==> Show recent spans from ConsoleSpanExporter (last 10s)"
CID="$(docker compose ps -q "$SERVICE")"
docker logs "$CID" --since 10s 2>&1 | tail -n 200 || true

echo "==> Done. Trace ID: ${TRACE_ID:-<none>}"
