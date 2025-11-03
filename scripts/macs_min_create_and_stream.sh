#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
[ -n "$KEY" ] || { echo "!! Missing API key (export API_KEY or put it in .api_key)"; exit 1; }

echo "== Create task =="
read -r -d '' BODY <<'JSON'
{
  "type": "DOC",
  "input": { "goal": "Say hi in one short sentence." }
}
JSON

curl -sS -D /tmp/create.h -o /tmp/create.json \
  -H "x-api-key: $KEY" -H "content-type: application/json" \
  -X POST "$BASE/v1/tasks" -d "$BODY"

echo "--- create headers ---"; sed -n '1,25p' /tmp/create.h
echo "--- create body ---"; cat /tmp/create.json; echo

TASK_ID="$(
  python3 - <<'PY' /tmp/create.json 2>/dev/null || true
import sys, json
try:
  d=json.load(open(sys.argv[1]))
  print(d.get("task_id") or d.get("id") or d.get("taskId") or "", end="")
except Exception: pass
PY
)"
[ -n "$TASK_ID" ] || { echo "!! Could not extract task id"; exit 1; }
echo "Task ID: $TASK_ID"

echo
echo "== Stream SSE =="
# -N disables curl buffering;  --max-time avoids hanging forever
curl -sS -N --max-time 45 \
  -H 'accept: text/event-stream' \
  "$BASE/v1/tasks/$TASK_ID/sse?api_key=$KEY" | sed -n '1,80p'

echo
echo "== Final (fallback) =="
curl -sS -H "x-api-key: $KEY" "$BASE/v1/tasks/$TASK_ID" | sed -n '1,120p' || true
