#!/usr/bin/env bash
set -euo pipefail
API_BASE="${API_BASE:-http://localhost:8080}"
ts="$(date +%Y%m%d-%H%M%S)"
curl -s "${API_BASE}/v1/bandit/export?fmt=csv&download=1" -o "bandit-${ts}.csv"
curl -s "${API_BASE}/v1/bandit/export?fmt=jsonl&download=1" -o "bandit-${ts}.jsonl"
echo "wrote bandit-${ts}.csv and bandit-${ts}.jsonl"
