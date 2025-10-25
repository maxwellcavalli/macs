#!/usr/bin/env bash
set -euo pipefail
d=./data; f="$d/bandit.jsonl"
[[ -s "$f" ]] || exit 0
mv "$f" "$f.$(date +%Y%m%d-%H%M%S)"
: > "$f"
