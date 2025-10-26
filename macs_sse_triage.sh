#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
MODEL="${MODEL:-llama3.1:8b-instruct}"

echo "== Config =="
echo "BASE=$BASE"
[ -n "$KEY" ] || { echo "!! Missing API key (set API_KEY or put it in .api_key)"; exit 1; }

echo
echo "== 1) Health check =="
curl -sS -i "$BASE/health" | sed -n '1,20p' || true

echo
echo "== 2) Create task =="
read -r -d '' BODY <<JSON
{
  "type": "DOC",
  "input": {
    "goal": "Say hi in one short sentence.",
    "language": "en",
    "options": { "model": "$MODEL", "temperature": 0.2, "max_tokens": 64 }
  },
  "metadata": { "source": "triage" }
}
JSON

curl -sS -D /tmp/create.hdr -o /tmp/create.json \
  -H "x-api-key: $KEY" -H "content-type: application/json" \
  -X POST "$BASE/v1/tasks" -d "$BODY" || true

echo "--- create headers (top) ---"
sed -n '1,20p' /tmp/create.hdr
echo "--- create body ---"
cat /tmp/create.json; echo

TASK_ID="$(
  python3 - <<'PY' /tmp/create.json 2>/dev/null || true
import sys, json
try:
  d=json.load(open(sys.argv[1]))
  print(d.get("task_id") or d.get("id") or d.get("taskId") or "", end="")
except Exception: pass
PY
)"
[ -n "$TASK_ID" ] || { echo "!! Could not extract task id from create response"; exit 1; }
echo "Task ID: $TASK_ID"

echo
echo "== 3) Stream SSE =="
# Note: --no-buffer/-N to force immediate flush
curl -sS -N --max-time 45 \
  -H 'accept: text/event-stream' \
  -D /tmp/sse.hdr \
  "$BASE/v1/tasks/$TASK_ID/sse?api_key=$KEY" \
  -o /tmp/sse.raw || true

echo "--- sse headers ---"
sed -n '1,40p' /tmp/sse.hdr
echo "--- sse first lines ---"
sed -n '1,40p' /tmp/sse.raw

if grep -q '^data:' /tmp/sse.raw 2>/dev/null; then
  echo "OK: SSE data frames detected."
else
  sz=$(wc -c < /tmp/sse.raw | tr -d ' ')
  if [ "$sz" = "0" ]; then
    echo "!! SSE stream was empty or never established in 45s."
  else
    echo "!! SSE had no 'data:' lines (server may not emit SSE frames or proxy buffered them)."
  fi
fi

echo
echo "== 4) Fallback: fetch final task (if supported) =="
curl -sS -i -H "x-api-key: $KEY" "$BASE/v1/tasks/$TASK_ID" | sed -n '1,60p' || true

echo
echo "== Hints =="
echo "- If health is not 200: the API is down or BASE is wrong."
echo "- If create is 401/403: API key missing/invalid."
echo "- If SSE Content-Type is not 'text/event-stream': wrong route or proxy rewriting."
echo "- If SSE headers look fine but file is empty: a proxy is buffering (nginx/Traefik) or server never flushes frames."
