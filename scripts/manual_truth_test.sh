#!/usr/bin/env bash
set -euo pipefail
API="${API_BASE:-http://localhost:8080}"
TS="${TS:-$(date +%s)}"
echo "==> POST legacy"
curl -iSv -X POST "$API/v1/bandit/record" -H 'content-type: application/json' \
  -d "{\"model\":\"unify-legacy-$TS\",\"reward\":0.44}"
echo
echo "==> POST unified"
curl -iSv -X POST "$API/v1/bandit/record" -H 'content-type: application/json' \
  -d "{\"model_id\":\"unify-new-$TS\",\"reward\":0.88}"
echo
echo "==> GET stats (head)"
curl -s "$API/v1/bandit/stats" | jq '.backend, (.stats|type), (.stats | (if type=="array" then .[:5] else to_entries[:5] end))'
