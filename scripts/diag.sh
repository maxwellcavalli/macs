#!/usr/bin/env bash
set -Eeuo pipefail

api_svc="${API_SVC:-api}"
ollama_svc="${OLLAMA_SVC:-ollama}"

say(){ printf "\n\033[1m==> %s\033[0m\n" "$*"; }

say "Health"
docker compose exec -T "$api_svc" sh -lc '
set -e; set +u
( apk add --no-cache curl jq >/dev/null 2>&1 || (apt-get update -y && apt-get install -y curl jq >/dev/null 2>&1) || true ) >/dev/null 2>&1 || true
API="${API_HOST_PORT:-8080}"; KEY="${API_KEY:-}"
BASE="http://127.0.0.1:${API}"
code=$(curl -sS -o /tmp/health.json -w "%{http_code}" -H "x-api-key: $KEY" -H "Authorization: Bearer $KEY" "$BASE/health" || true)
echo "health HTTP $code"; jq . </tmp/health.json 2>/dev/null || cat /tmp/health.json || true
'

say "Ollama reachable from API?"
docker compose exec -T "$api_svc" sh -lc '
set -e; set +u
( apk add --no-cache curl jq >/dev/null 2>&1 || (apt-get update -y && apt-get install -y curl jq >/div/null 2>&1) || true ) >/dev/null 2>&1 || true
curl -sS "http://ollama:11434/api/tags" | jq ".models | length" || echo "0"
'

say "Create tiny DOC task"
docker compose exec -T "$api_svc" sh -lc '
set -e; set +u
API="${API_HOST_PORT:-8080}"; KEY="${API_KEY:-}"
BASE="http://127.0.0.1:${API}"
read -r -d "" BODY << "JSON"
{
  "type":"DOC",
  "input":{
    "goal":"Say hello in one short sentence.",
    "language":"python",
    "repo":{"path":"."},
    "constraints":{"artifacts_required":false},
    "model":"qwen2.5-coder:7b-instruct-q4_K_M",
    "options":{"temperature":0.2,"top_p":0.9,"max_tokens":64,"seed":123}
  },
  "metadata":{"client":"diag","best_of":1}
}
JSON
code=$(curl -sS -o /tmp/create.json -w "%{http_code}" \
  -H "x-api-key: $KEY" -H "Authorization: Bearer $KEY" \
  -H "content-type: application/json" \
  -d "$BODY" "$BASE/v1/tasks" || true)
echo "create HTTP $code"
cat /tmp/create.json; echo
TID="$(jq -r ".task_id // .id // .taskId // empty" /tmp/create.json || echo)"
echo "TASK_ID=${TID:-<empty>}"
[ -n "${TID:-}" ] || exit 0
curl -sS -N -m 10 -H "x-api-key: $KEY" -H "Accept: text/event-stream" "$BASE/v1/tasks/$TID/sse" | sed -n "1,40p" || true
'
