#!/usr/bin/env bash
set -Eeuo pipefail
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
TIMEOUT="${TIMEOUT:-90}"
[ -n "$KEY" ] || { echo "!! Missing API key"; exit 1; }

# Create task
curl -sSf -H "x-api-key: $KEY" -H "content-type: application/json" \
  -X POST "$BASE/v1/tasks" \
  -d '{"type":"DOC","input":{"goal":"Say ok","options":{"temperature":0}}}' \
  -o /tmp/create_resp.json

python3 - <<'PY' > /tmp/task_id.txt
import json; d=json.load(open("/tmp/create_resp.json"))
print(d.get("task_id") or d.get("id") or d.get("taskId") or "", end="")
PY
read -r TASK_ID < /tmp/task_id.txt || true
[ -n "$TASK_ID" ] || { echo "!! Could not extract task id"; cat /tmp/create_resp.json; exit 1; }
echo "Task: $TASK_ID"

# Stream + detect terminal
curl -sS -N --max-time "$TIMEOUT" -H 'accept: text/event-stream' \
  "$BASE/v1/tasks/$TASK_ID/sse?api_key=$KEY" \
| tee /tmp/sse_raw.txt > /dev/null

python3 - "$TASK_ID" <<'PY'
import json, sys
from pathlib import Path

task_id = sys.argv[1]
raw_path = Path("/tmp/sse_raw.txt")
seen = False

def _handle(payload: str) -> bool:
    payload = payload.strip()
    if not payload:
        return False
    if payload == "[DONE]":
        return True
    try:
        obj = json.loads(payload)
    except Exception:
        return False
    status = str(obj.get("status", "")).strip().lower()
    note = str(obj.get("note", "")).strip().lower()
    if status in ("done", "error", "canceled") or note == "artifacts-present":
        return True
    return False

if raw_path.exists():
    for raw_line in raw_path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line.startswith("data:"):
            continue
        payload = raw_line[5:].strip()
        if _handle(payload):
            seen = True
            break

print("SEEN_DONE" if seen else "NO_DONE")
sys.exit(0 if seen else 1)
PY
res=$?
echo "--- Last 30 raw SSE lines ---"; tail -n 30 /tmp/sse_raw.txt || true
[ $res -eq 0 ] && echo "✅ PASS: SSE produced a terminal marker (or was closed by middleware)" || echo "❌ FAIL: No terminal marker within ${TIMEOUT}s"
exit $res
