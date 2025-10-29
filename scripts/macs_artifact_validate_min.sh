#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
EXPECT="${EXPECT:-OK-HELLO-42}"   # substring to assert
TIMEOUT="${TIMEOUT:-45}"          # seconds total

[ -n "$KEY" ] || { echo "!! Missing API key (export API_KEY or put it in .api_key)"; exit 1; }

# --- Create deterministic DOC task ---
cat > /tmp/create_body.json <<EOF
{
  "type": "DOC",
  "input": {
    "goal": "Reply with exactly ${EXPECT}. No quotes, no punctuation, no code block, no extra text.",
    "options": { "temperature": 0.0, "max_tokens": 64 }
  }
}
EOF

curl -sSf -H "x-api-key: $KEY" -H "content-type: application/json" \
  -X POST "$BASE/v1/tasks" -d @/tmp/create_body.json \
  -o /tmp/create_resp.json

# --- Extract task_id robustly (no nested subshells) ---
cat > /tmp/get_task_id.py <<'PY'
import sys, json
d=json.load(open('/tmp/create_resp.json'))
print(d.get('task_id') or d.get('id') or d.get('taskId') or '')
PY
python3 /tmp/get_task_id.py > /tmp/task_id.txt
read -r TASK_ID < /tmp/task_id.txt || true
if [ -z "${TASK_ID:-}" ]; then
  echo "!! Could not extract task id"; echo "Response was:"; cat /tmp/create_resp.json; exit 1
fi
echo "Task: $TASK_ID"

# --- Wait for artifact & validate (inside container, no host-side parsing) ---
# Pass variables via env to avoid quoting issues.
docker compose exec -T \
  -e TID="$TASK_ID" -e EXP="$EXPECT" -e TO="$TIMEOUT" api sh -lc '
set -eu
root="${ARTIFACTS_DIR:-/data/artifacts}"
d="$root/$TID"
deadline=$(( $(date +%s) + TO ))

# wait for task dir to appear
while [ "$(date +%s)" -lt "$deadline" ]; do
  [ -d "$d" ] && break
  sleep 1
done
[ -d "$d" ] || { echo "❌ FAIL: No artifacts dir found: $d"; exit 2; }

# wait for first non-empty .md/.txt
f=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  f=$(find "$d" -type f \( -name "*.md" -o -name "*.txt" \) -size +0c 2>/dev/null | head -n1 || true)
  [ -n "$f" ] && break
  sleep 1
done
[ -n "$f" ] || { echo "❌ FAIL: No non-empty .md/.txt found under $d within timeout"; exit 3; }

echo "--- artifact file: $f ---"
sed -n "1,200p" "$f"

# assert substring
if grep -Fq -- "$EXP" "$f"; then
  echo "✅ PASS: Found expected substring: $EXP"
  exit 0
else
  echo "❌ FAIL: Expected substring not found: $EXP"
  exit 4
fi
'
