#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8080}"
JQ="${JQ:-jq}"

# Unique suffix so we don't clash with prior runs
TS="$(date +%s)"
LEGACY_MODEL="unify-legacy-${TS}"
NEW_MODEL="unify-new-${TS}"

echo "==> Hitting $API_BASE"
curl -fsS "$API_BASE/v1/ollama/health" >/dev/null && echo "Health: OK" || { echo "Health check failed"; exit 1; }

echo "==> Record legacy payload"
curl -fsS -X POST "$API_BASE/v1/bandit/record" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$LEGACY_MODEL\",\"reward\":0.42}" \
  | $JQ -r '.ok' | grep -q true && echo "Legacy record: OK"

echo "==> Record unified payload"
curl -fsS -X POST "$API_BASE/v1/bandit/record" \
  -H 'content-type: application/json' \
  -d "{\"model_id\":\"$NEW_MODEL\",\"reward\":0.84,\"won\":true,\"task_type\":\"duel\"}" \
  | $JQ -r '.ok' | grep -q true && echo "Unified record: OK"

echo "==> Read stats"
STATS_JSON="$(curl -fsS "$API_BASE/v1/bandit/stats")"
echo "$STATS_JSON" | $JQ . >/dev/null # validate JSON

# Normalize both possible shapes:
# - PG backend: .stats is an array of rows {model_id, n, sum_reward, ...}
# - File backend: .stats is a dict { model -> {count, sum, ...} }
has_legacy=$(
  echo "$STATS_JSON" | $JQ -r --arg m "$LEGACY_MODEL" '
    if (.stats|type)=="array"
      then (.stats[]|select(.model_id==$m)|.model_id)
      else (.stats|has($m)) | tostring
    end' || true
)

has_new=$(
  echo "$STATS_JSON" | $JQ -r --arg m "$NEW_MODEL" '
    if (.stats|type)=="array"
      then (.stats[]|select(.model_id==$m)|.model_id)
      else (.stats|has($m)) | tostring
    end' || true
)

ok_legacy="no"; ok_new="no"
if [[ "$has_legacy" == "$LEGACY_MODEL" || "$has_legacy" == "true" ]]; then ok_legacy="yes"; fi
if [[ "$has_new" == "$NEW_MODEL" || "$has_new" == "true" ]]; then ok_new="yes"; fi

echo "==> Verification"
echo "  - legacy event present: $ok_legacy ($LEGACY_MODEL)"
echo "  - unified event present: $ok_new ($NEW_MODEL)"

if [[ "$ok_legacy" == "yes" && "$ok_new" == "yes" ]]; then
  echo "PASS: Bandit persistence is unified (both payload shapes accepted & persisted)."
  exit 0
else
  echo "FAIL: Could not find both events in stats. Check API logs/backends."
  exit 2
fi
