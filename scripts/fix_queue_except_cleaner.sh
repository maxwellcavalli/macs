#!/usr/bin/env bash
set -euo pipefail

echo "== fix_queue_except_cleaner.sh : remove stray 'except Exception:' blocks =="

if [[ ! -f "app/queue.py" ]]; then
  echo "!! Run from repo root where app/queue.py exists."
  exit 1
fi

ts="$(date +%Y%m%d-%H%M%S)"
mkdir -p .patch_backups
cp app/queue.py ".patch_backups/queue.py.$ts.pre-clean.bak"

python3 - <<'PY'
from pathlib import Path

p = Path("app/queue.py")
lines = p.read_text(encoding="utf-8").splitlines(True)

def indent_of(s: str) -> int:
    return len(s) - len(s.lstrip(" "))

out = []
i = 0
removed = 0
L = len(lines)

while i < L:
    line = lines[i]
    # Match "except Exception:" exactly (with leading spaces allowed)
    stripped = line.strip()
    if stripped.startswith("except Exception:") and stripped.rstrip() == "except Exception:":
        cur_indent = indent_of(line)
        # Walk back to find a same-indent "try:" before a block boundary
        j = i - 1
        found_pair = False
        while j >= 0:
            prev = lines[j]
            if prev.strip() == "":
                j -= 1
                continue
            prev_indent = indent_of(prev)
            # stop if we hit a def/class or a line with less indent (block boundary)
            if prev_indent < cur_indent:
                break
            if prev_indent == cur_indent and prev.strip() == "try:":
                found_pair = True
                break
            j -= 1
        if not found_pair:
            # Remove this "except Exception:" and an immediate indented "pass" (optional)
            # Skip current line
            i += 1
            removed += 1
            # If next line exists and is 'pass' with greater indent, remove it too
            if i < L:
                nxt = lines[i]
                if nxt.strip() == "pass" and indent_of(nxt) > cur_indent:
                    i += 1
                    removed += 1
            # continue without appending the removed lines
            continue
    # default: keep line
    out.append(line)
    i += 1

if removed:
    p.write_text("".join(out), encoding="utf-8")
print(f"[ok] removed {removed} stray except/pass line(s)")
PY

echo "== done =="
