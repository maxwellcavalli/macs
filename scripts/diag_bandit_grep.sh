#!/usr/bin/env bash
set -euo pipefail
API_BASE="${API_BASE:-http://localhost:8080}"
LEGACY="${1:-unify-legacy}"
NEW="${2:-unify-new}"
curl -fsS "$API_BASE/v1/bandit/stats" \
 | jq -r 'if (.stats|type)=="array" then (.stats[]|.model_id // .model) else (.stats|keys[]) end' \
 | (grep -E "${LEGACY}|${NEW}" || true)
