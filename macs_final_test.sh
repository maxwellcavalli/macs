#!/usr/bin/env bash
set -Eeuo pipefail
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
EXPECT="${EXPECT:-OK-HELLO-42}"
TIMEOUT="${TIMEOUT:-45}"

[ -n "$KEY" ] || { echo "!! Missing API key"; exit 1; }

# Create a deterministic DOC task
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

# Poll /final until it exists and is JSON
deadline=$(( $(date +%s) + TIMEOUT ))
STATUS=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  curl -sS -D /tmp/h -o /tmp/b -H "x-api-key: $KEY" "$BASE/v1/tasks/$TASK_ID/final" >/dev/null || true
  CODE="$(awk 'NR==1{print $2}' /tmp/h)"
  CT="$(awk 'BEGIN{IGNORECASE=1}/^Content-Type:/{print $2}' /tmp/h | tr -d '\r')"
  if [ "$CODE" = "200" ] && echo "$CT" | grep -qi 'application/json'; then
    break
  fi
  sleep 1
done

echo "--- headers ---"; sed -n '1,20p' /tmp/h
echo "--- body ---"; sed -n '1,120p' /tmp/b

# Extract text and status
TEXT="$(python3 - <<'PY'
import sys, json
d=json.load(open('/tmp/b'))
print(d.get('result') or d.get('output') or (d.get('message') or {}).get('content') or '')
PY
)"
STATUS="$(python3 - <<'PY'
import sys, json
d=json.load(open('/tmp/b'))
print((d.get('status') or '').lower())
PY
)"

echo "Final status: ${STATUS:-unknown}"
echo "Text: $TEXT"

if [ -n "$TEXT" ] && [ "$STATUS" != "error" ] && [ "$STATUS" != "canceled" ] && echo "$TEXT" | grep -Fq "$EXPECT"; then
  echo "✅ PASS"
  exit 0
else
  echo "❌ FAIL (expected substring not found or bad status)"
  exit 2
fi
