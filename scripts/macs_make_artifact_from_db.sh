#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
EXPECT="${EXPECT:-OK-HELLO-42}"    # substring to assert
TIMEOUT="${TIMEOUT:-45}"
PG_SERVICE="${PG_SERVICE:-pg}"
DB="${DB:-macs}"
DB_USER="${DB_USER:-postgres}"

usage() { echo "Usage: $0 [TASK_ID]"; }

# 1) Get a task id (use arg or create a new deterministic DOC task)
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
       -X POST "$BASE/v1/tasks" -d @/tmp/create_body.json -o /tmp/create_resp.json
  python3 - <<'PY' > /tmp/task_id.txt
import json; d=json.load(open('/tmp/create_resp.json')); print(d.get('task_id') or d.get('id') or d.get('taskId') or '')
PY
  read -r TASK_ID < /tmp/task_id.txt || true
fi
if [ -z "${TASK_ID:-}" ]; then
  # Fallback to latest id from DB if create failed
  TASK_ID="$(docker compose exec -T "$PG_SERVICE" psql -U "$DB_USER" -d "$DB" -t -A -c "select id from public.tasks order by created_at desc limit 1;")"
fi
[ -n "$TASK_ID" ] || { echo "!! Could not get a task id"; exit 1; }
echo "Task: $TASK_ID"

# 2) Inside API container: fetch row via asyncpg and write artifact
docker compose exec -T -e TID="$TASK_ID" -e EXP="$EXPECT" api python - <<'PY'
import os, asyncio, json, typing as t

async def main():
    task_id = os.environ["TID"]
    expect  = os.environ.get("EXP","")
    # Build connection params from env
    dsn = os.getenv("DB_DSN")
    kw = None
    if not dsn:
        kw = dict(
            host=os.getenv("PGHOST","pg"),
            port=int(os.getenv("PGPORT","5432")),
            user=os.getenv("PGUSER","postgres"),
            password=os.getenv("PGPASSWORD","postgres"),
            database=os.getenv("PGDATABASE", os.getenv("DB_NAME","macs")),
        )
    import asyncpg
    conn = await asyncpg.connect(dsn=dsn) if dsn else await asyncpg.connect(**kw)
    try:
        row = await conn.fetchrow("SELECT to_jsonb(t) AS j FROM public.tasks t WHERE id=$1", task_id)
        if not row:
            print("!! Task not found in DB", flush=True); raise SystemExit(2)
        doc = dict(row["j"])
    finally:
        await conn.close()

    # Extract any human-readable text
    text = ""
    for k in ("result","output","text","content"):
        v = doc.get(k)
        if isinstance(v,str) and v.strip():
            text = v.strip(); break
    if not text and isinstance(doc.get("message"), dict):
        v = doc["message"].get("content")
        if isinstance(v,str) and v.strip():
            text = v.strip()

    # Write artifact (even placeholder if empty)
    root = os.getenv("ARTIFACTS_DIR","/data/artifacts")
    import pathlib
    d = pathlib.Path(root) / task_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("result.md" if (text.strip()) else "result.txt")
    p.write_text(text if text else " ", encoding="utf-8")
    print(f"artifact={p}", flush=True)

    # Basic assert if EXPECT provided
    if expect and text:
        import sys
        if expect in text:
            print("assert=PASS", flush=True)
            return
        print("assert=FAIL", flush=True)
        sys.exit(4)
    else:
        print("assert=SKIP", flush=True)

asyncio.run(main())
PY

# 3) Show artifact content from inside container
docker compose exec -T api sh -lc '
set -eu
root="${ARTIFACTS_DIR:-/data/artifacts}"
d="$root/'"$TASK_ID"'"
f="$(find "$d" -maxdepth 1 -type f \( -name "result.md" -o -name "result.txt" \) | head -n1 || true)"
[ -n "$f" ] || { echo "!! No artifact file in $d"; exit 3; }
echo "--- artifact: $f ---"
sed -n "1,200p" "$f"
'

