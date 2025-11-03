#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
EXPECT="${EXPECT:-OK-HELLO-42}"   # required substring in the final text
TIMEOUT="${TIMEOUT:-45}"          # total seconds to wait
OUT="/tmp/task_test_output.md"

[ -n "$KEY" ] || { echo "!! Missing API key (export API_KEY or put it in .api_key)"; exit 1; }

# --- Create deterministic DOC task (force plain text output) ---
cat > /tmp/create_body.json <<EOF
{
  "type": "DOC",
  "input": {
    "goal": "Reply with exactly ${EXPECT}. No quotes, no punctuation, no code block, no extra text.",
    "options": { "temperature": 0.0, "max_tokens": 64 }
  }
}
EOF

RESP="$(curl -sSf -H "x-api-key: $KEY" -H "content-type: application/json" \
  -X POST "$BASE/v1/tasks" -d @/tmp/create_body.json)"

TASK_ID="$(
  printf '%s' "$RESP" | python3 - <<'PY'
import sys, json
d=json.load(sys.stdin)
print(d.get('task_id') or d.get('id') or d.get('taskId') or '')
PY
)"
[ -n "$TASK_ID" ] || { echo "!! Could not extract task id from: $RESP"; exit 1; }
echo "Task: $TASK_ID"

# --- Helper to extract any human-readable text fields from JSON ---
cat > /tmp/extract_text.py <<'PY'
import sys, json
raw = sys.stdin.read()
try:
  d = json.loads(raw)
except Exception:
  print("") ; sys.exit(0)
keys = {'result','output','text','content','answer','body'}
seen=set(); out=[]
def add(s):
  if isinstance(s,str):
    s=s.strip()
    if s and s not in seen:
      seen.add(s); out.append(s)
def walk(x):
  if isinstance(x,dict):
    for k,v in x.items():
      kl=str(k).lower()
      if kl in keys and isinstance(v,str): add(v)
      if kl=='message' and isinstance(v,dict) and isinstance(v.get('content'),str): add(v['content'])
      walk(v)
  elif isinstance(x,list):
    for v in x: walk(v)
walk(d)
print("\n".join(out))
PY

# --- Try SSE first (ok if nothing arrives due to early-exit) ---
: > "$OUT"
SSE_GOT=0
if { curl -sS -N --max-time "$TIMEOUT" \
       -H 'accept: text/event-stream' \
       "$BASE/v1/tasks/$TASK_ID/sse?api_key=$KEY" \
     | awk '/^data:/ {print substr($0,6)}' \
     | python3 - "$OUT" <<'PY'
import sys, json
out=open(sys.argv[1],'a',encoding='utf-8'); any_tok=False
for line in sys.stdin:
  line=line.strip()
  if not line: continue
  if line=='[DONE]': break
  try:
    o=json.loads(line)
  except Exception:
    print(line, end=""); out.write(line); out.flush(); any_tok=True; continue
  if o.get("note")=="artifacts-present" or o.get("status")=="done": break
  for k in ("delta","token","content","output"):
    if isinstance(o.get(k),str):
      print(o[k], end=""); out.write(o[k]); out.flush(); any_tok=True
  m=o.get("message")
  if isinstance(m,dict) and isinstance(m.get("content"),str):
    print(m["content"], end=""); out.write(m["content"]); out.flush(); any_tok=True
out.close()
# success exit if any tokens were printed
sys.exit(0 if any_tok else 2)
PY
   }; then
  SSE_GOT=1
fi

# --- If SSE empty, poll GET /v1/tasks/{id} until done|error|canceled ---
if [ "$SSE_GOT" -ne 1 ]; then
  deadline=$(( $(date +%s) + TIMEOUT ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    BODY="$(curl -sSf -H "x-api-key: $KEY" "$BASE/v1/tasks/$TASK_ID")"
    STATUS="$(
      printf '%s' "$BODY" | python3 - <<'PY'
import sys, json
d=json.load(sys.stdin)
print((d.get("status") or "").lower(), end="")
PY
    )"
    printf '%s' "$BODY" | python3 /tmp/extract_text.py > "$OUT" || true
    case "$STATUS" in
      done|error|canceled) break ;;
    esac
    sleep 1
  done
fi

echo "---- Captured text ----"
sed -n '1,80p' "$OUT" || true
echo "-----------------------"

if grep -Fq "$EXPECT" "$OUT"; then
  echo "✅ PASS: Found expected substring: $EXPECT"
  exit 0
else
  echo "❌ FAIL: Expected '$EXPECT' not found in $OUT"
  echo "Hint: if the output is empty, your task likely produced only artifacts or no textual fields."
  exit 2
fi
