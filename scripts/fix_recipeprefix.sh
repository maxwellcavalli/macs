#!/usr/bin/env bash
set -euo pipefail
in="Makefile"; tmp="$in.tmp.$$"

# 1) normalize line endings (remove CR)
sed 's/\r$//' "$in" > "$tmp.1"

# 2) force '>' prefix on command lines under the two targets
awk '
  function is_target(l) { return l ~ /^[A-Za-z0-9_.-]+:([^=]|$)/ }
  BEGIN { sect=0 }
  {
    if ($0 ~ /^rag-gold-init:[[:space:]]*$/) { print; sect=1; next }
    if ($0 ~ /^rag-eval:[[:space:]]*$/)      { print; sect=2; next }
    if (is_target($0)) { print; sect=0; next }

    if (sect==1 || sect==2) {
      # If line is non-empty and not a comment, ensure it starts with RECIPEPREFIX
      if ($0 ~ /^[[:space:]]*[^#[:space:]].*$/) {
        sub(/^[[:space:]]+/,"> ");
        print; next
      }
    }
    print
  }' "$tmp.1" > "$tmp.2"

mv "$tmp.2" "$in"; rm -f "$tmp.1"
echo "Patched $in. Recipe lines under rag-* now start with '>'."
