#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8080}"
PROMPT="${1:-Implement a function that returns the sum of two integers.}"
MODEL_A="${MODEL_A:-qwen2.5-coder}"
MODEL_B="${MODEL_B:-llama3.1-70b}"

API_KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
[[ -n "${API_KEY}" ]] || { echo "!! Missing API key. Set API_KEY or create .api_key"; exit 1; }

AUTH=(-H "Authorization: Bearer ${API_KEY}" -H "X-API-Key: ${API_KEY}")
JSON=(-H 'content-type: application/json')

echo ">> API_BASE=${API_BASE}"
echo ">> MODELS=${MODEL_A} vs ${MODEL_B}"
echo ">> PROMPT=${PROMPT}"
echo ">> Using API key: ${API_KEY}"

# Primary: simple duel endpoint (compat layer)
payload_duel="$(jq -n --arg p "$PROMPT" --arg a "$MODEL_A" --arg b "$MODEL_B" \
  '{prompt:$p, models:[$a,$b]}')"

echo ">> POST /v1/duel (compat)"
resp="$(curl -sS -X POST "${AUTH[@]}" "${JSON[@]}" --data "$payload_duel" -w $'\n%{http_code}' "${API_BASE}/v1/duel")" || true
code="${resp##*$'\n'}"; body="${resp%$'\n'*}"
echo ">> HTTP ${code}"; printf '%s\n' "$body"

if [[ "$code" != "200" ]]; then
  echo "!! /v1/duel not available; falling back to /v1/tasks shapes"
  # Shape A/B kept here in case you later wire duel through /v1/tasks
  payloadA="$(jq -n --arg p "$PROMPT" --arg a "$MODEL_A" --arg b "$MODEL_B" \
    '{type:"TEST", input:{language:"java", repo:"scaffold:maven", goal:$p, constraints:{duel:true, models:[$a,$b]}}}')"
  resp="$(curl -sS -X POST "${AUTH[@]}" "${JSON[@]}" --data "$payloadA" -w $'\n%{http_code}' "${API_BASE}/v1/tasks")" || true
  code="${resp##*$'\n'}"; body="${resp%$'\n'*}"
  echo ">> HTTP ${code}"; printf '%s\n' "$body"
fi

[[ "$code" == "200" ]] || { echo "!! Submission failed"; exit 1; }

task_id="$(jq -r '.task_id // .id // empty' <<<"$body")"
[[ -n "$task_id" && "$task_id" != "null" ]] || { echo "!! Could not parse task_id"; exit 1; }

echo ">> Task created: ${task_id}"
printf '%s' "$task_id" > .last_task_id
echo ">> Saved to .last_task_id"
echo ">> To stream: scripts/stream.sh ${task_id}"
