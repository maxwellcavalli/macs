#!/usr/bin/env bash
set -euo pipefail
API="${API:-http://localhost:8080}"

post() {
  local payload="$1"
  echo "POST /v1/bandit/record  -> $(jq -c . <<<"$payload")"
  code=$(curl -s -o /tmp/bandit_resp.json -w "%{http_code}" \
    -X POST "$API/v1/bandit/record" -H 'content-type: application/json' -d "$payload" || true)
  echo "HTTP $code"; cat /tmp/bandit_resp.json; echo; echo
  if [ "$code" -ge 400 ] || ! jq -e '.ok==true' >/dev/null 2>&1 < /tmp/bandit_resp.json; then
    echo "Trying alias route /bandit/record..."
    code2=$(curl -s -o /tmp/bandit_resp2.json -w "%{http_code}" \
      -X POST "$API/bandit/record" -H 'content-type: application/json' -d "$payload" || true)
    echo "HTTP $code2"; cat /tmp/bandit_resp2.json; echo; echo
  fi
}

# Sample data
post '{"model_id":"mistral:7b-instruct-q4_K_M","task_type":"router","reward":0.70,"won":true}'
post '{"model_id":"qwen2.5-coder:7b-instruct-q4_K_M","task_type":"code","reward":0.90,"won":true}'
post '{"model_id":"gemma2:9b-instruct-q4_K_M","task_type":"docs","reward":0.85,"won":true}'
post '{"model_id":"deepseek-coder:6.7b-instruct-q4_K_M","task_type":"planner","reward":0.75,"won":true}'
post '{"model_id":"gemma2:9b-instruct-q4_K_M","task_type":"duel","reward":0.65,"won":false}'

echo "Current aggregated stats:"
curl -s "$API/v1/bandit/stats" | jq . || true
echo
echo "Alias stats (if prefix mismatch):"
curl -s "$API/bandit/stats" | jq . || true
