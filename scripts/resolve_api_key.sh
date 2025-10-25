#!/usr/bin/env bash
set -euo pipefail
# Priority: env API_KEY > /mnt/data/.api_key > ./.api_key
if [ -n "${API_KEY:-}" ]; then
  printf '%s' "$API_KEY"; exit 0
fi
for f in /mnt/d/agente/multi_agent_code_system_v24/.api_key .api_key; do
  if [ -f "$f" ]; then
    tr -d '\r\n' <"$f"; exit 0
  fi
done
printf ''
