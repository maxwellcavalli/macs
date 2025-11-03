#!/usr/bin/env bash
set -euo pipefail
API_BASE="${API_BASE:-http://localhost:8080}"
echo "==> $API_BASE/v1/bandit/stats"
json="$(curl -fsS "$API_BASE/v1/bandit/stats")"
echo "$json" | jq -r '.backend as $b | "backend=\($b)"'
shape="$(echo "$json" | jq -r '.stats | type')"
echo "shape=$shape"
if [ "$shape" = "array" ]; then
  echo "$json" | jq '.stats | length as $n | "rows=\($n)" , ( .stats[] | {model_id,model,n,wins,sum_reward,avg_reward} )' | head -40
else
  echo "$json" | jq '.stats | to_entries | .[:10]'
fi
