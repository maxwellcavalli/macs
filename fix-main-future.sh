#!/usr/bin/env sh
set -euo pipefail

MAIN="app/main.py"
ROUTER_IMPORT="from app.routers.tasks_create_fix import router as tasks_create_fix_router"
INCLUDE_LINE="app.include_router(tasks_create_fix_router)"

[ -f "$MAIN" ] || { echo "File not found: $MAIN"; exit 1; }

# 1) Remove any existing occurrences of the router import to avoid duplicates
tmp1="$(mktemp)"; grep -vF "$ROUTER_IMPORT" "$MAIN" > "$tmp1"

# 2) Reinsert the router import immediately after the __future__ import line
tmp2="$(mktemp)"
awk -v add="$ROUTER_IMPORT" '
  BEGIN{done=0}
  {
    print $0
    if (!done && $0 ~ /^from[[:space:]]+__future__[[:space:]]+import[[:space:]]+annotations[[:space:]]*$/) {
      print add
      done=1
    }
  }
  END{
    if(!done){
      # If the file doesn’t have a __future__ import, append our import near the top
      print add
    }
  }
' "$tmp1" > "$tmp2"

# 3) Ensure the include_router() call exists (append once if missing)
if ! grep -qF "$INCLUDE_LINE" "$tmp2"; then
  # Try to place it right after the FastAPI app creation
  tmp3="$(mktemp)"
  awk -v inc="$INCLUDE_LINE" '
    BEGIN{done=0}
    {
      print $0
      if(!done && $0 ~ /app[[:space:]]*=[[:space:]]*FastAPI\(/){
        print inc
        done=1
      }
    }
    END{
      if(!done){ print inc }
    }
  ' "$tmp2" > "$tmp3"
  mv "$tmp3" "$tmp2"
fi

# 4) Write back
cp "$tmp2" "$MAIN"
rm -f "$tmp1" "$tmp2"

echo "Patched $MAIN. Showing first 15 lines for sanity:"
nl -ba "$MAIN" | sed -n '1,15p'
