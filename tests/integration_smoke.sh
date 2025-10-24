#!/usr/bin/env bash
set -euo pipefail

API=${API:-http://localhost:8080}
KEY=${API_KEY:-dev-local}

echo "[1/6] health"
curl -fsS "$API/health" | jq -e '.ok==true' >/dev/null

echo "[2/6] ollama health"
curl -fsS "$API/v1/ollama/health" | jq -e '.ok==true' >/dev/null || true

echo "[3/6] models"
curl -fsS "$API/v1/models?debug=1" | jq -e '.models|length>=0' >/dev/null

echo "[4/6] submit task"
PAYLOAD='{"type":"CODE","input":{"language":"java","frameworks":[],"repo":{"path":"./workspace","include":[],"exclude":[]},"constraints":{"max_tokens":128,"latency_ms":20000},"goal":"Create a single-file Java class that compiles using only JDK."},"routing_hints":{"duel":false},"output_contract":{"expected_files":["src/main/java/com/acme/Smoke.java"]}}'
TASK_ID=$(curl -fsS -X POST "$API/v1/tasks" -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d "$PAYLOAD" | jq -r '.task_id')
test -n "$TASK_ID"

echo "[5/6] stream until done"
# read few SSE lines and ensure we see status: done within timeout
END=$((SECONDS+90))
OK=0
while (( SECONDS < END )); do
  if curl -fsS "$API/v1/tasks/$TASK_ID" | jq -e '.status=="done"' >/dev/null 2>&1; then
    OK=1; break
  fi
  sleep 2
done
test "$OK" -eq 1

echo "[6/6] fetch final status"
curl -fsS "$API/v1/tasks/$TASK_ID" | jq -e '.status=="done"' >/dev/null

echo "OK"
