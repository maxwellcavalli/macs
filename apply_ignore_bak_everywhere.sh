#!/usr/bin/env bash
set -Eeuo pipefail

# 1) Update the scanner to skip *.bak*
python3 - "$PWD/scripts/find_and_fix_status.py" <<'PY'
import sys, pathlib, re
p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding="utf-8")
if "def files():" not in src:
    print("warn: scripts/find_and_fix_status.py not found or unexpected; skipping scanner patch")
    sys.exit(0)

pattern = r"def files\(\):\n\s+for p in ROOT\.rglob\(\"\\\*\"\):\n(?:.|\n)*?yield p"
new = re.sub(
    r"""
def\ files\(\):\n
\s+for\ p\ in\ ROOT\.rglob\("\*"\):\n
(\s+)if\ not\ p\.is_file\(\):\ continue\n
\1if\ p\.suffix\.lower\(\)\ not\ in\ EXTS:\ continue\n
\1if\ any\(sd\ in\ p\.parts\ for\ sd\ in\ SKIP_DIRS\):\ continue\n
\1yield\ p
""",
    r"""def files():
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        if p.suffix.lower() not in EXTS: continue
        if any(sd in p.parts for sd in SKIP_DIRS): continue
        # ignore backups like foo.py.bak / foo.json.bak12
        if any(s.lower().startswith(".bak") for s in p.suffixes): continue
        yield p""",
    src, flags=re.X
)
if new != src:
    p.write_text(new, encoding="utf-8")
    print("patched:", p)
else:
    print("scanner already skips .bak* or patch not needed")
PY

# 2) Update pre-commit to exclude backups (if present)
hook=".git/hooks/pre-commit"
if [ -f "$hook" ]; then
  tmp="$(mktemp)"
  awk '
    BEGIN{done=0}
    /git diff --cached/ && /name-only/ && /diff-filter=ACM/ && /grep -E/ && done==0 {
      # insert a filter to drop any path ending with .bak*
      print "files=$(git diff --cached --name-only --diff-filter=ACM | grep -Ev '\''\\.bak[^/]*$'\'' | grep -E '\''\\.(py|ts|tsx|js|jsx|go|sql)$'\'' || true)"; 
      # skip original line
      done=1; next
    }
    {print}
  ' "$hook" > "$tmp" && mv "$tmp" "$hook" && chmod +x "$hook"
  echo "patched: $hook"
else
  echo "note: no .git/hooks/pre-commit found (skipping hook patch)"
fi

echo "Done. Re-run the scanner as needed:"
echo "  python3 scripts/find_and_fix_status.py"
