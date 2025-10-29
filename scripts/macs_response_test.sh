#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
MODEL="${MODEL:-}"   # optional; leave empty if server has a default
EXPECT="${EXPECT:-OK-HELLO-42}"  # substring we require in the reply
TIMEOUT="${TIMEOUT:-45}"         # seconds to wait overall

[ -n "$KEY" ] || { echo "!! Missing API key (export API_KEY or put it in .api_key)"; exit 1; }

# ---------- Create a deterministic DOC task ----------
read -r -d '' BODY <<JSON
{
  "type": "DOC",
  "input": {
    "goal": "Reply with exactly ${EXPECT}. No quotes, no punctuation, no code block, no extra text.",
    "options": {
      "temperature": 0.0"$( [ -n "$MODEL" ] && printf ', "model": "%s"' "$MODEL" )"
    }
  }
}
JSON

RESP="$(curl -sS -X POST "$BASE/v1/tasks" \
  -H "x-api-key: $KEY" -H "content-type: application/json" -d "$BODY")" || true
TASK_ID="$(printf '%s' "$RESP" | python3 - <<'PY' || true
import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('task_id') or d.get('id') or d.get('taskId') or '', end='')
except: pass
PY
)"
[ -n "$TASK_ID" ] || { echo "!! Could not extract task id from: $RESP"; exit 1; }
echo "Task: $TASK_ID"

OUT="/tmp/task_${TASK_ID}.md"; : > "$OUT"

# ---------- Try SSE first ----------
SSE_OK=0
curl -sS -N --max-time "$TIMEOUT" \
  -H 'accept: text/event-stream' \
  "$BASE/v1/tasks/$TASK_ID/sse?api_key=$KEY" | \
awk '/^data:/ {print substr($0,6)}' | \
python3 -u - "$OUT" <<'PY'
import sys, json
out = open(sys.argv[1], 'a', encoding='utf-8')
any_token = False
for line in sys.stdin:
    line=line.strip()
    if not line: 
        continue
    if line == "[DONE]":
        break
    try:
        obj=json.loads(line)
    except Exception:
        # raw text frame
        print(line, end="")
        out.write(line); out.flush()
        any_token = True
        continue
    if obj.get("note")=="artifacts-present" or obj.get("status")=="done":
        break
    for k in ("delta","token","content","output"):
        if isinstance(obj.get(k), str):
            print(obj[k], end=""); out.write(obj[k]); out.flush(); any_token = True
    msg = obj.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        print(msg["content"], end=""); out.write(msg["content"]); out.flush(); any_token = True
out.close()
# communicate success via exit code
sys.exit(0 if any_token else 2)
PY
rc=$?
if [ "$rc" -eq 0 ]; then SSE_OK=1; fi

# ---------- If SSE produced nothing, poll final result ----------
if [ "$SSE_OK" -ne 1 ]; then
  echo; echo "(No SSE tokens; polling final result...)"
  deadline=$(( $(date +%s) + TIMEOUT ))
  STATUS="queued"
  while [ "$(date +%s)" -lt "$deadline" ]; do
    BODY="$(curl -sS -H "x-api-key: $KEY" "$BASE/v1/tasks/$TASK_ID" || true)"
    STATUS="$(printf '%s' "$BODY" | python3 - <<'PY' || True
import sys, json
try:
    d=json.load(sys.stdin)
    print((d.get("status") or "").lower(), end="")
except: pass
PY
)"
    # grab any text-ish fields into OUT (idempotent)
    printf '%s' "$BODY" | python3 - "$OUT" <<'PY'
import sys, json
path = sys.argv[1]
try:
    d = json.load(sys.stdin)
except:
    sys.exit(0)
texts=[]; seen=set()
def add(s):
    if isinstance(s,str):
        s=s.strip()
        if len(s)>0 and s not in seen:
            seen.add(s); texts.append(s)
def walk(x):
    if isinstance(x,dict):
        for k,v in x.items():
            kl=str(k).lower()
            if kl in ("result","output","text","content","answer","body"): 
                if isinstance(v,str): add(v)
            if kl=="message" and isinstance(v,dict) and isinstance(v.get("content"),str): add(v["content"])
            walk(v)
    elif isinstance(x,list):
        for v in x: walk(v)
walk(d)
if texts:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(texts))
PY
    case "$STATUS" in
      done|error|canceled) break ;;
    esac
    sleep 1
  done
  echo "Final status: $STATUS"
fi

echo
echo "---- Captured text ----"
sed -n '1,80p' "$OUT" || true
echo "-----------------------"

# ---------- Assert EXPECT is present ----------
if grep -Fq "$EXPECT" "$OUT"; then
  echo "✅ PASS: Found expected substring: $EXPECT"
  exit 0
else
  echo "❌ FAIL: Expected '$EXPECT' not found in $OUT"
  exit 2
fi
