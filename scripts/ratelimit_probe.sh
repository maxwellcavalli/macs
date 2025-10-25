#!/usr/bin/env bash
set -euo pipefail
API_BASE="${API_BASE:-http://localhost:8080}"
API_KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
if [[ -z "${API_KEY}" ]]; then echo "need API_KEY or .api_key"; exit 1; fi
CURL_AUTH=(-H "Authorization: Bearer ${API_KEY}" -H "X-API-Key: ${API_KEY}")
echo ">> Probing ${API_BASE}/v1/ratelimit/check"
curl -sS "${CURL_AUTH[@]}" -D - -o /dev/null "${API_BASE}/v1/ratelimit/check?consume=0" | sed -n '1,20p'
