#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8080}"
API_KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
[[ -n "${API_KEY}" ]] || { echo "!! Missing API key. Set API_KEY or create .api_key"; exit 1; }

LANGUAGE="${1:-java}"
GOAL="${2:-Smoke duel scoring pipeline}"
MODEL_A="${3:-qwen2.5-coder}"
MODEL_B="${4:-llama3.1-70b}"

AUTH_JSON=(-H 'content-type: application/json')
AUTH_KEYS=(-H "Authorization: Bearer ${API_KEY}" -H "X-API-Key: ${API_KEY}")

echo ">> API_BASE=${API_BASE}"
echo ">> Using API_KEY=${API_KEY}"
echo ">> Payload base: TEST / $LANGUAGE / $MODEL_A vs $MODEL_B"

make_payload() {
  local repo_path="$1"
  jq -n \
    --arg lang "$LANGUAGE" \
    --arg goal "$GOAL" \
    --arg a "$MODEL_A" \
    --arg b "$MODEL_B" \
    --arg rpath "$repo_path" \
  '{
      type:"TEST",
      input:{
        language:$lang,
        goal:$goal,
        repo:{ path:$rpath },
        constraints:{ models:[$a,$b] }
      }
    }'
}

try_post() {
  local payload="$1" label="$2"
  echo ">> Try repo.path='${label}'"
  local resp code body
  resp="$(curl -sS -X POST "${AUTH_KEYS[@]}" "${AUTH_JSON[@]}" --data "$payload" \
           -w $'\n%{http_code}' "${API_BASE}/v1/tasks?api_key=${API_KEY}")" || true
  code="${resp##*$'\n'}"; body="${resp%$'\n'*}"
  echo ">> HTTP ${code}"
  printf '%s\n' "$body"
  echo "----"
  if [[ "$code" == "200" ]]; then
    jq -r '.task_id // .id // empty' <<<"$body" > .last_task_id
    echo ">> Task created: $(cat .last_task_id)"
    exit 0
  fi
}

# Most likely your build runner recognizes the scaffold keyword.
PATHS=( "scaffold:maven" "/app" "/app/project" "." )

for rp in "${PATHS[@]}"; do
  payload="$(make_payload "$rp")"
  try_post "$payload" "$rp"
done

echo "!! Submission failed with repo.path candidates: ${PATHS[*]}"
echo "   If your repo lives elsewhere, run: scripts/submit_task.sh <lang> <goal> <modelA> <modelB> and edit PATHS in the script."
exit 1
