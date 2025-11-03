#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
TASK_ID="${1:-e3d86bb8-3123-4a43-844e-59041033094f}"
HDR="/tmp/task_${TASK_ID}.hdr"
BODY="/tmp/task_${TASK_ID}.body"
OUT="/tmp/task_${TASK_ID}_final.md"

[ -n "$KEY" ] || { echo "Missing API key"; exit 1; }

# Fetch with headers saved
curl -sS -D "$HDR" -o "$BODY" -H "x-api-key: $KEY" "$BASE/v1/tasks/$TASK_ID" || true

echo "--- response headers ---"; sed -n '1,40p' "$HDR"
CT=$(grep -i '^content-type:' "$HDR" | tr -d '\r' | awk '{print tolower($2)}' || true)
STATUS=$(awk 'NR==1{print $2}' "$HDR")

# Quick sanity checks
if [ -z "$STATUS" ]; then
  echo "!! No HTTP status (connection failed). Check BASE or server logs."
  exit 1
fi
if [ "$STATUS" != "200" ]; then
  echo "!! Non-200 status: $STATUS"
  echo "--- body (first 300 chars) ---"
  head -c 300 "$BODY"; echo
  exit 1
fi
if [ ! -s "$BODY" ]; then
  echo "!! Empty body from server."
  exit 1
fi

# If not JSON, show a snippet and save raw
if ! printf '%s' "$CT" | grep -q 'application/json'; then
  echo "!! Content-Type is not JSON: ${CT:-unknown}"
  echo "--- body (first 300 chars) ---"
  head -c 300 "$BODY"; echo
  echo "Raw saved at: $BODY"
  exit 1
fi

# Parse JSON and extract human-readable text fields
python3 - "$BODY" "$OUT" <<'PY'
import sys, json
body_path, out_path = sys.argv[1], sys.argv[2]
raw = open(body_path, 'rb').read().decode('utf-8', 'replace').strip()
try:
    doc = json.loads(raw)
except Exception as e:
    print("!! JSON parse error:", e)
    print(raw[:300])
    sys.exit(1)

keys = {'result','output','text','message','content','answer','body'}
seen = set(); out = []

def add(v):
    if isinstance(v, str):
        s = v.strip()
        if len(s) >= 2 and s not in seen:
            seen.add(s); out.append(s)

def walk(x):
    if isinstance(x, dict):
        for k, v in x.items():
            kl = str(k).lower()
            if kl in keys and isinstance(v, str): add(v)
            if kl == 'message' and isinstance(v, dict) and isinstance(v.get('content'), str): add(v['content'])
            walk(v)
    elif isinstance(x, list):
        for v in x: walk(v)

walk(doc)
text = "\n\n".join(out)
open(out_path, 'w', encoding='utf-8').write(text)
print(text if text else "(no obvious text fields found)")
PY

echo "Saved (if any) to: $OUT"
