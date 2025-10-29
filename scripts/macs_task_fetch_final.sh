#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://localhost:8080}"
KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
TASK_ID="${1:-e3d86bb8-3123-4a43-844e-59041033094f}"
OUT="/tmp/task_${TASK_ID}_final.md"

[ -n "$KEY" ] || { echo "Missing API key"; exit 1; }
JSON="$(curl -sS -H "x-api-key: $KEY" "$BASE/v1/tasks/$TASK_ID")"
printf '%s\n' "$JSON" | python3 - "$OUT" <<'PY'
import sys, json, re
doc=json.loads(sys.stdin.read())

# heuristic extraction of text fields
candidates=[]

def add(v):
    if isinstance(v,str):
        v=v.strip()
        if len(v)>=2: candidates.append(v)

def walk(x):
    if isinstance(x,dict):
        for k,v in x.items():
            kl=k.lower()
            if kl in ("result","output","text","message","content","answer","body"):
                add(v if isinstance(v,str) else (v.get("content") if isinstance(v,dict) else None))
            walk(v)
    elif isinstance(x,list):
        for v in x: walk(v)

walk(doc)

best = "\n\n".join(dict.fromkeys(candidates)) if candidates else ""
open(sys.argv[1],"w",encoding="utf-8").write(best)
print(best if best else "(no obvious text fields found)")
PY
echo
echo "Saved (if any): $OUT"
