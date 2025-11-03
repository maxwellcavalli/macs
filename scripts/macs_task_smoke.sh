#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
[ -n "$KEY" ] || { echo "Missing API key: export API_KEY or put it in .api_key"; exit 1; }

read -r -d '' BODY <<'JSON'
{
  "type": "DOC",
  "input": {
    "goal": "Say hi in one short sentence.",
    "language": "en",
    "options": {
      "model": "llama3.1:8b",
      "temperature": 0.2,
      "max_tokens": 64
    }
  },
  "metadata": {"source":"smoke"}
}
JSON

echo "== Health =="
curl -sS "$BASE/health" | sed -e 's/.*/  &/'

echo "== Create =="
RESP="$(curl -sS -X POST "$BASE/v1/tasks" \
  -H "x-api-key: $KEY" -H "content-type: application/json" \
  -d "$BODY")"
echo "  $RESP"

# Extract task id (supports task_id|id|taskId)
TASK_ID="$(printf '%s' "$RESP" | \
  python3 - <<'PY' || true
import sys, json
d=json.load(sys.stdin)
print(d.get('task_id') or d.get('id') or d.get('taskId') or '')
PY
)"
if [ -z "$TASK_ID" ]; then
  TASK_ID="$(printf '%s' "$RESP" | sed -n 's/.*"task_\\?id"\\?\\s*:\\s*"\([^"]\+\)".*/\1/p' | head -n1)"
fi
[ -n "$TASK_ID" ] || { echo "Could not extract task id"; exit 1; }
echo "== Task ID =="
echo "  $TASK_ID"

echo "== Stream =="
curl -sS -N "$BASE/v1/tasks/$TASK_ID/sse?api_key=$KEY" \
  -H 'accept: text/event-stream' | \
awk '
  /^data:/ {
    j=substr($0,6)
    print j
    if (j ~ /"note":"artifacts-present"/ || j ~ /"status":"done"/) done=1
    if (j ~ /\\[DONE\\]/) done=1
    fflush()
  }
  done { exit 0 }
'

# Optional: try to fetch final result if your API supports it
echo "== Final (optional) =="
curl -sS "$BASE/v1/tasks/$TASK_ID" -H "x-api-key: $KEY" || true
