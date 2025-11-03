#!/usr/bin/env bash
set -euo pipefail
in="Makefile"; tmp="$in.tmp.$$"

# 1) strip CRLF
sed 's/\r$//' "$in" > "$tmp.1"

awk '
  function is_target(l) { return l ~ /^[A-Za-z0-9_.-]+:([^=]|$)/ }

  BEGIN { sect=0; skip_ci=0 }

  # --- helper to emit a command line with RECIPEPREFIX ">" ---
  function emit_cmd(line) {
    sub(/^[[:space:]]+/, "", line);      # trim leading spaces
    if (line !~ /^>/) line="> " line;    # add recipe prefix
    print line;
  }

  {
    # replace entire ci-local block with a single safe one-liner
    if ($0 ~ /^ci-local:[[:space:]]*(#.*)?$/) {
      print $0;
      print "> API_URL=\"$(API_URL)\" API_KEY=\"$(API_KEY)\" bash tests/integration_smoke.sh";
      skip_ci=1; next;
    }
    if (skip_ci) {
      if (is_target($0)) { print $0; skip_ci=0; }
      next;
    }

    # enter RAG sections
    if ($0 ~ /^rag-gold-init:[[:space:]]*$/) { print; sect=1; next }
    if ($0 ~ /^rag-eval:[[:space:]]*$/)      { print; sect=2; next }

    # while inside a RAG section, force correct recipe prefix on non-empty, non-comment lines
    if (sect==1 || sect==2) {
      if (is_target($0)) { print; sect=0; next }
      if ($0 ~ /^[[:space:]]*$/) { print; next }
      if ($0 ~ /^[[:space:]]*#/) { print; next }
      emit_cmd($0); next
    }

    print
  }
' "$tmp.1" > "$tmp.2"

mv "$tmp.2" "$in"; rm -f "$tmp.1"
echo "✅ Patched $in"
