#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8080}"
API_KEY="${API_KEY:-$(cat .api_key 2>/dev/null || true)}"
[[ -n "${API_KEY}" ]] || { echo "!! Missing API key. Set API_KEY or create .api_key"; exit 1; }
AUTH=(-H "Authorization: Bearer ${API_KEY}" -H "X-API-Key: ${API_KEY}")
ACCEPT=(-H 'Accept: text/event-stream')

TASK_ID="${1:-}"
[[ -n "${TASK_ID}" ]] || { [[ -f .last_task_id ]] && TASK_ID="$(cat .last_task_id)"; }
[[ -n "${TASK_ID}" ]] || { echo "Usage: $0 <TASK_ID>"; exit 1; }

echo ">> Streaming task ${TASK_ID} from ${API_BASE}"

try_stream() {
  local url="$1"
  echo ">> Trying ${url}"
  # probe
  code="$(curl -sS -o /dev/null -w '%{http_code}' "${AUTH[@]}" "${ACCEPT[@]}" "${url}")" || code=000
  echo ">> HTTP ${code}"
  if [[ "${code}" == "200" ]]; then
    echo "----- BEGIN STREAM (${url}) -----"
    curl -sS -N "${AUTH[@]}" "${ACCEPT[@]}" "${url}" || true
    echo
    echo "----- END STREAM (${url}) -----"
    return 0
  fi
  return 1
}

# 1) New compat route first
try_stream "${API_BASE}/v1/tasks/${TASK_ID}/sse" && exit 0
# 2) Existing paths
try_stream "${API_BASE}/v1/tasks/${TASK_ID}/stream" && exit 0
try_stream "${API_BASE}/v1/stream/${TASK_ID}" && exit 0
try_stream "${API_BASE}/v1/tasks/${TASK_ID}/events" && exit 0

echo "!! All SSE endpoints failed — falling back to status polling."
# Poll /status up to ~30s
for i in $(seq 1 30); do
  st="$(curl -s "${AUTH[@]}" "${API_BASE}/v1/tasks/${TASK_ID}/status" | jq -r .status 2>/dev/null || echo "")"
  echo ">> status: ${st:-unknown}"
  if [[ "$st" == "done" ]]; then
    path="./artifacts/${TASK_ID}/result.json"
    if [[ -f "$path" ]]; then
      echo ">> Artifact: ${path}"
      cat "$path"; echo
    else
      echo ">> Done but artifact not found on host. Check container /app/artifacts."
    fi
    exit 0
  fi
  sleep 1
done

echo "!! Timed out waiting for status=done."
exit 2
