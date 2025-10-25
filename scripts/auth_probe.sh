#!/usr/bin/env bash
set -euo pipefail
API_BASE="${API_BASE:-http://localhost:8080}"
API_KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
[[ -n "$API_KEY" ]] || { echo "!! Missing API key"; exit 1; }

payload='{"type":"TEST","input":{"language":"java","goal":"probe","repo":{"path":"scaffold:maven"},"constraints":{"models":["a","b"]}}}'

try() {
  local label="$1"; shift
  local url="${API_BASE}/v1/tasks"
  echo "== $label"
  code=$(curl -sS -o /dev/null -w '%{http_code}' "$@" -H 'content-type: application/json' -d "$payload" "$url" || echo 000)
  echo "HTTP $code"
  [[ "$code" != 401 && "$code" != 403 && "$code" != 000 ]] && exit 0
}

# Authorization variants
try 'Authorization: Bearer <key>'          -H "Authorization: Bearer ${API_KEY}"
try 'Authorization: Api-Key <key>'         -H "Authorization: Api-Key ${API_KEY}"
try 'Authorization: <key>'                 -H "Authorization: ${API_KEY}"
try 'X-API-Key: <key>'                     -H "X-API-Key: ${API_KEY}"
try 'x-api-key: <key>'                     -H "x-api-key: ${API_KEY}"
try 'Api-Key: <key>'                       -H "Api-Key: ${API_KEY}"
try 'API-Key: <key>'                       -H "API-Key: ${API_KEY}"
try 'X-API-Token: <key>'                   -H "X-API-Token: ${API_KEY}"
try 'X-Auth-Token: <key>'                  -H "X-Auth-Token: ${API_KEY}"
try 'X-Authorization: Bearer <key>'        -H "X-Authorization: Bearer ${API_KEY}"

# query param fallback
echo "== ?api_key query"
code=$(curl -sS -o /dev/null -w '%{http_code}' -H 'content-type: application/json' -d "$payload" "${API_BASE}/v1/tasks?api_key=${API_KEY}" || echo 000)
echo "HTTP $code"; [[ "$code" != 401 && "$code" != 403 && "$code" != 000 ]] && exit 0

# cookie fallback
echo "== Cookie api_key=<key>"
code=$(curl -sS -o /dev/null -w '%{http_code}' -H 'content-type: application/json' -H "Cookie: api_key=${API_KEY}" -d "$payload" "${API_BASE}/v1/tasks" || echo 000)
echo "HTTP $code"; [[ "$code" != 401 && "$code" != 403 && "$code" != 000 ]] && exit 0

echo "!! All auth styles failed."
exit 2
