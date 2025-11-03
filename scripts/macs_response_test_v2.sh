#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
EXPECT="${EXPECT:-OK-HELLO-42}"   # substring we require in the final text
TIMEOUT="${TIMEOUT:-45}"          # seconds
SLEEP="${SLEEP:-1}"
OUT="/tmp/task_test_output.md"

[ -n "$KEY" ] || { echo "!! Missing API key (export API_KEY or put it in .api_key)"; exit 1; }

# 1) Create a deterministic DOC task
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

# 2) Poll GET /v1/tasks/{id} until done|error|canceled, with strict header/body checks
: > "$OUT"
deadline=$(( $(date +%s) + TIMEOUT ))
last_status=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  HDR="/tmp/task_${TASK_ID}.hdr"
  BODY="/tmp/task_${TASK_ID}.body"
  curl -sS -D "$HDR" -o "$BODY" -H "x-api-key: $KEY" "$BASE/v1/tasks/$TASK_ID" || true

  http_code="$(awk 'NR==1{print $2}' "$HDR")"
  ct="$(awk 'BEGIN{IGNORECASE=1} /^Content-Type:/ {print tolower($0)}' "$HDR" | awk -F': ' '{print $2}' | tr -d '\r')"
  sz="$(wc -c < "$BODY" | tr -d ' ')"

  if [ -z "$http_code" ]; then
    echo "!! No HTTP status (connection issue)."; break
  fi
  if [ "$http_code" != "200" ]; then
    echo "!! Non-200: $http_code"; head -c 200 "$BODY"; echo; break
  fi
  if [ "$sz" -eq 0 ]; then
    # Empty body; keep polling
    sleep "$SLEEP"; continue
  fi
  if ! printf '%s' "$ct" | grep -q 'application/json'; then
    echo "!! Not JSON (Content-Type=$ct). Body head:"; head -c 200 "$BODY"; echo
    sleep "$SLEEP"; continue
  fi

  # Extract status + any human-readable text safely
  read -r last_status < <(python3 - <<'PY' "$BODY"
import sys, json
d=json.load(open(sys.argv[1]))
print((d.get("status") or "").lower(), end="")
PY
  )

  python3 - <<'PY' "$BODY" "$OUT"
import sys, json
src, out = sys.argv[1], sys.argv[2]
d=json.load(open(src))
keys={'result','output','text','content','answer','body'}
seen=set(); buf=[]
def add(s):
  if isinstance(s,str):
    s=s.strip()
    if s and s not in seen:
      seen.add(s); buf.append(s)
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
open(out,'w',encoding='utf-8').write("\n".join(buf))
PY

  case "$last_status" in
    done|error|canceled) break ;;
  esac

  sleep "$SLEEP"
done

echo "Final status: ${last_status:-unknown}"
echo "---- Captured text ----"
sed -n '1,80p' "$OUT" || true
echo "-----------------------"

if [ -s "$OUT" ] && grep -Fq "$EXPECT" "$OUT"; then
  echo "✅ PASS: Found expected substring: $EXPECT"
  exit 0
else
  echo "❌ FAIL: Expected '$EXPECT' not found (or body empty)."
  echo "Hint: If the body is consistently empty, your GET route may return 204/empty JSON. Check API logs for the task serializer."
  exit 2
fi
