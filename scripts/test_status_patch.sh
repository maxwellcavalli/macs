#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# ---- config (override via env) ----
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
PG_SERVICE="${PG_SERVICE:-pg}"   # your DB service name in docker compose
DB_USER="${DB_USER:-agent}"
DB="${DB:-agent}"
TIMEOUT="${TIMEOUT:-60}"         # seconds to wait for completion

# ---- helpers ----
db() { docker compose exec -T "$PG_SERVICE" psql -U "$DB_USER" -d "$DB" -At -c "$1"; }

CANON_RE='^(queued|running|done|error|canceled)$'
BAD_RE='^(succeeded|success|completed|complete|failed|failure|fail|cancelled)$'

# ---- (A) Create a fresh task unless TASK_ID provided ----
TASK_ID="${1:-}"
if [ -z "$TASK_ID" ]; then
  [ -n "$KEY" ] || { echo "!! Missing API key"; exit 1; }
  cat > /tmp/create_body.json <<EOF
{
  "type": "DOC",
  "input": { "goal": "Say OK-HELLO-42 only.", "options": { "temperature": 0.0, "max_tokens": 32 } }
}
EOF
  curl -sSf -H "x-api-key: $KEY" -H "content-type: application/json" \
       -X POST "$BASE/v1/tasks" -d @/tmp/create_body.json -o /tmp/create_resp.json
  python3 - <<'PY' >/tmp/task_id.txt
import json; d=json.load(open('/tmp/create_resp.json'))
print(d.get('task_id') or d.get('id') or d.get('taskId') or '')
PY
  read -r TASK_ID < /tmp/task_id.txt || true
fi
[ -n "$TASK_ID" ] || { echo "!! Could not get a task id"; exit 1; }
echo "Task: $TASK_ID"

# ---- (B) Poll DB status; fail immediately on any non-canonical value ----
deadline=$(( $(date +%s) + TIMEOUT ))
SEEN=()
while [ "$(date +%s)" -lt "$deadline" ]; do
  STATUS="$(db "SELECT lower(status) FROM public.tasks WHERE id='${TASK_ID}'")" || true
  STATUS="${STATUS//$'\r'/}"
  [ -n "$STATUS" ] || { sleep 1; continue; }

  # Record every status we see
  SEEN+=("$STATUS")
  echo "status: $STATUS"

  if [[ "$STATUS" =~ $BAD_RE ]]; then
    echo "❌ FAIL: saw non-canonical status: $STATUS"
    exit 2
  fi
  if [[ "$STATUS" =~ $CANON_RE ]]; then
    case "$STATUS" in
      done|error|canceled) break ;;
    esac
  fi
  sleep 1
done

# ---- (C) Final check on this task ----
FINAL="$(db "SELECT lower(status) FROM public.tasks WHERE id='${TASK_ID}'")" || true
echo "final: ${FINAL:-unknown}"

if ! [[ "$FINAL" =~ $CANON_RE ]]; then
  echo "❌ FAIL: final status not canonical: ${FINAL:-<none>}"
  exit 3
fi

# ---- (D) Safety net: ensure no recent rows still write synonyms ----
BAD_COUNT="$(db "SELECT count(*) FROM public.tasks WHERE lower(status) IN ('succeeded','success','completed','complete','failed','failure','fail','cancelled');")" || true
if [ "${BAD_COUNT:-0}" != "0" ]; then
  echo "❌ FAIL: found $BAD_COUNT row(s) in DB with non-canonical status"
  exit 4
fi

echo "✅ PASS: status patch OK (statuses seen: ${SEEN[*]})"
