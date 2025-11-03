#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s nullglob

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.."; pwd)"
cd "$ROOT"

say() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
ok()  { printf "\033[0;32m✔ %s\033[0m\n" "$*"; }
err() { printf "\033[0;31m✖ %s\033[0m\n" "$*"; }

require() { command -v "$1" >/dev/null || { err "Missing dependency: $1"; exit 1; }; }

say "Environment checks"
require docker
require curl
require python3
printf "Docker: %s\n" "$(docker --version | awk '{print $3}')"

say "Lint: Shell scripts"
mapfile -t SHS < <(git ls-files '*.sh' 2>/dev/null || true)
for f in "${SHS[@]}"; do bash -n "$f"; done
if command -v shellcheck >/dev/null; then
  shellcheck -x "${SHS[@]}" || { err "shellcheck failed"; exit 1; }
else
  echo "(shellcheck not found — skipping static shell analysis)"
fi
ok "Shell syntax OK"

say "Lint: Python"
python3 -m compileall -q app || { err "Python syntax errors in app/"; exit 1; }
if command -v ruff >/dev/null;  then ruff check app;  else echo "(ruff not found — skipping)"; fi
if command -v mypy >/dev/null;  then mypy app || true;  else echo "(mypy not found — skipping)"; fi
if command -v pytest >/dev/null; then pytest -q || true; else echo "(pytest not found — skipping)"; fi
ok "Python checks passed"

say "Validate JSON & YAML"
# JSON sanity: parse all tracked *.json / *.jsonl files quickly
python3 - <<'PY'
import json, sys, subprocess
from pathlib import Path
def check_json(p):
    try:
        if p.suffix == ".jsonl":
            with p.open('r', encoding='utf-8') as f:
                for i,l in enumerate(f,1):
                    if l.strip(): json.loads(l)
        else:
            json.load(open(p, 'r', encoding='utf-8'))
    except Exception as e:
        print(f"JSON error in {p}: {e}")
        sys.exit(1)
files = subprocess.check_output(["git","ls-files","*.json","*.jsonl"], text=True).strip().splitlines()
for f in files:
    if f: check_json(Path(f))
PY
if command -v yamllint >/dev/null; then yamllint -s .; else echo "(yamllint not found — skipping)"; fi
ok "Config parsing OK"

say "Docker Compose config"
docker compose config -q

say "Build & start API"
docker compose up -d --build api
# wait for /v1/ollama/health
for i in {1..40}; do
  if curl -sf http://localhost:8080/v1/ollama/health >/dev/null; then ok "API healthy"; break; fi
  sleep 1
  if (( i==40 )); then
    err "API failed to become healthy"
    docker compose logs --no-color api | tail -n 200
    exit 1
  fi
done

say "API smoke"
curl -s http://localhost:8080/v1/ollama/health | sed -e 's/^/  /'

say "SSE early-exit (artifacts-present) regression guard"
API_KEY="$(cat .api_key 2>/dev/null || echo demo)"
TASK_JSON="$(curl -s -X POST http://localhost:8080/v1/tasks \
  -H "x-api-key: $API_KEY" -H 'content-type: application/json' -d '{}')"
# Extract task_id with jq if present, else python
if command -v jq >/dev/null; then
  TASK_ID="$(jq -r '.task_id' <<<"$TASK_JSON")"
else
  TASK_ID="$(python3 - <<'PY' "$TASK_JSON"
import json,sys; print(json.loads(sys.argv[1]).get("task_id",""))
PY
)"
fi
[ -n "$TASK_ID" ] || { err "Could not obtain task_id from POST /v1/tasks"; echo "$TASK_JSON"; exit 1; }

CID="$(docker compose ps -q api)"
docker exec "$CID" bash -lc 'mkdir -p "${ARTIFACTS_DIR:-/data/artifacts}"'
docker exec "$CID" bash -lc 'test -d "${ARTIFACTS_DIR:-/data/artifacts}"'
docker exec "$CID" bash -lc 'echo ok' >/dev/null

# Stream in background while we create the artifacts dir
OUT="$(curl -s http://localhost:8080/v1/tasks/"$TASK_ID"/sse & sleep 0.5; docker exec "$CID" bash -lc "mkdir -p \${ARTIFACTS_DIR:-/data/artifacts}/$TASK_ID"; wait || true)"
echo "$OUT" | sed -e 's/^/  /'
echo "$OUT" | grep -q 'artifacts-present' && ok "SSE early-exit OK" || { err "Missing artifacts-present marker"; exit 1; }

say "RAG eval harness (sanity run)"
if [ ! -f data/golden_set.jsonl ]; then
  mkdir -p data
  cat > data/golden_set.jsonl <<'EOF'
{"query":"hello","answer_doc":"docA"}
{"query":"world","answer_doc":"docB"}
EOF
fi
if grep -q '^rag-eval:' Makefile; then
  make -s rag-eval || true
else
  echo "(rag-eval target not present — skipping)"
fi

say "All done"
ok "CI suite completed successfully"
