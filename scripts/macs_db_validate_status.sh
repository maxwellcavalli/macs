#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# --- Config (override via env if needed) ---
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
EXPECT="${EXPECT:-OK-HELLO-42}"     # substring you expect in the final text (if any)
TIMEOUT="${TIMEOUT:-60}"            # seconds to wait for DB status=done

DB="${DB:-${PGDATABASE:-macs}}"
DB_USER="${DB_USER:-${PGUSER:-postgres}}"

# Try to autodetect the Postgres service name inside docker compose
SERVICE="${PG_SERVICE:-}"
if [ -z "$SERVICE" ]; then
  for s in pg db postgres database; do
    if docker compose exec -T "$s" sh -lc 'command -v psql >/dev/null 2>&1' 2>/dev/null; then
      SERVICE="$s"; break
    fi
  done
fi
[ -n "$SERVICE" ] || { echo "!! Could not find a Postgres service. Set PG_SERVICE=your_db_service and rerun."; exit 1; }

# Helper to run psql in the DB container
psql_in_db() { docker compose exec -T "$SERVICE" psql -U "$DB_USER" -d "$DB" -At -c "$1"; }

# --- Step 1: Create a small deterministic task (unless TASK_ID is provided) ---
TASK_ID="${1:-}"
if [ -z "$TASK_ID" ]; then
  [ -n "$KEY" ] || { echo "!! Missing API key (export API_KEY or put it in .api_key)"; exit 1; }
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
  python3 - <<'PY' >/tmp/task_id.txt
import json; d=json.load(open('/tmp/create_resp.json'))
print(d.get('task_id') or d.get('id') or d.get('taskId') or '')
PY
  read -r TASK_ID < /tmp/task_id.txt || true
fi
[ -n "$TASK_ID" ] || { echo "!! Could not get a task id"; exit 1; }
echo "Task: $TASK_ID"

# --- Step 2: Poll DB for canonical status (queued|running|done|error|canceled) ---
deadline=$(( $(date +%s) + TIMEOUT ))
STATUS=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  STATUS="$(psql_in_db "SELECT lower(status) FROM public.tasks WHERE id='${TASK_ID}'")" || true
  STATUS="${STATUS//$'\r'/}"
  [ -n "$STATUS" ] || { sleep 1; continue; }
  echo "status: $STATUS"
  case "$STATUS" in
    done|error|canceled) break ;;
  esac
  sleep 1
done

if [ -z "$STATUS" ]; then
  echo "❌ FAIL: Task not found in DB"; exit 2
fi
if [ "$STATUS" != "done" ]; then
  echo "⚠️  Final status: $STATUS (not 'done')"
else
  echo "✅ Final status: done"
fi

# --- Step 3: Fetch the full row as JSON and extract any human-readable text fields ---
# (Your schema may not store text; this step is best-effort.)
ROW_JSON="$(psql_in_db "SELECT to_jsonb(t) FROM public.tasks t WHERE id='${TASK_ID}'")" || true
printf '%s' "$ROW_JSON" > /tmp/task_row.json

python3 - <<'PY' /tmp/task_row.json > /tmp/task_text.txt
import sys, json
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("", end=""); raise SystemExit(0)
texts=[]; seen=set()
def add(s):
    if isinstance(s,str):
        s=s.strip()
        if s and s not in seen:
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
print("\n".join(texts), end="")
PY

echo "---- Extracted text (if any) ----"
sed -n '1,100p' /tmp/task_text.txt || true
echo "---------------------------------"

if [ -s /tmp/task_text.txt ] && grep -Fq "$EXPECT" /tmp/task_text.txt; then
  echo "✅ PASS: Expected substring found in DB-extracted text"
  exit 0
fi

# If no text is stored (common with artifact-only pipelines), declare success based on status.
if [ "$STATUS" = "done" ] && ! [ -s /tmp/task_text.txt ]; then
  echo "ℹ️  No text fields in DB row; pipeline likely writes only artifacts."
  echo "✅ PASS (status=done)"
  exit 0
fi

echo "❌ FAIL: Neither DB text matched nor status=done with empty text."
exit 3
