#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
TASK_ID="${1:-e3d86bb8-3123-4a43-844e-59041033094f}"

[ -n "$KEY" ] || { echo "Missing API key: export API_KEY or put it in .api_key"; exit 1; }
[ -n "$TASK_ID" ] || { echo "Missing TASK_ID"; exit 1; }

OUT="/tmp/task_${TASK_ID}.md"
: > "$OUT"

echo "== Streaming $TASK_ID =="
curl -sS -N -D /tmp/sse_${TASK_ID}.hdr \
  -H 'accept: text/event-stream' \
  "$BASE/v1/tasks/$TASK_ID/sse?api_key=$KEY" | \
awk '/^data:/ {print substr($0,6)}' | \
python3 -u - "$OUT" <<'PY'
import sys, json
out = open(sys.argv[1], 'a', encoding='utf-8')
for line in sys.stdin:
    line=line.strip()
    if not line: 
        continue
    if line == "[DONE]":
        print("\n[DONE]")
        break
    try:
        obj=json.loads(line)
    except Exception:
        print(line)
        continue
    # Early-exit markers (no tokens)
    if obj.get("note")=="artifacts-present" or obj.get("status")=="done":
        print(json.dumps(obj))
        break
    # Extract textual deltas
    for key in ("delta","token","content","output"):
        if isinstance(obj.get(key), str):
            print(obj[key], end="", flush=True)
            out.write(obj[key]); out.flush()
    msg=obj.get("message") or {}
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        print(msg["content"], end="", flush=True)
        out.write(msg["content"]); out.flush()
print()
out.close()
PY

echo
echo "--- SSE headers ---"
sed -n '1,40p' /tmp/sse_${TASK_ID}.hdr
echo
echo "Saved text (if any) to: $OUT"
