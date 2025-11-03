#!/usr/bin/env bash
set -euo pipefail
# Preview occurrences
echo "== Preview old literals =="
rg -n -S --hidden --glob '!node_modules' --glob '!venv' --glob '!dist' --glob '!build' \
   "('succeeded'|\"succeeded\"|'failed'|\"failed\"|'cancelled'|\"cancelled\")" || true
# Apply replacements in common source files
git ls-files | grep -E '\.(py|ts|tsx|js|jsx)$' | xargs sed -i -E \
  -e "s/'succeeded'/'done'/g"  -e 's/"succeeded"/"done"/g' \
  -e "s/'failed'/'error'/g"    -e 's/"failed"/"error"/g' \
  -e "s/'cancelled'/'canceled'/g" -e 's/"cancelled"/"canceled"/g'
echo "== Done. Review changes =="
git diff --name-only
