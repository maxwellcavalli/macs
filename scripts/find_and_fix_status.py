#!/usr/bin/env python3
"""
Find (and optionally fix) code paths that write non-canonical task statuses.

Canonical: queued | running | done | error | canceled
Non-canonical hunted: succeeded, success, completed, complete, failed, failure, fail, cancelled

Usage:
  python scripts/find_and_fix_status.py                # report only
  python scripts/find_and_fix_status.py --diff         # show unified diffs
  python scripts/find_and_fix_status.py --fix          # apply conservative fixes (backs up *.bak)
"""
import argparse, pathlib, re, sys, difflib

ROOT = pathlib.Path(".")
EXTS = {".py",".ts",".tsx",".js",".jsx",".go",".sql",".yml",".yaml",".json"}
SKIP_DIRS = {"node_modules","venv",".venv","dist","build",".git",".tox",".pytest_cache"}

BAD_WORDS = r"\b(succeeded|success|completed|complete|failed|failure|fail|cancelled)\b"
NEAR_STATUS = re.compile(r"status", re.I)
BAD = re.compile(BAD_WORDS, re.I)

MAP = {
    "succeeded":"done", "success":"done", "completed":"done", "complete":"done",
    "failed":"error", "failure":"error", "fail":"error",
    "cancelled":"canceled",
}
SUB = re.compile(BAD_WORDS, re.I)

def files():
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        if p.suffix.lower() not in EXTS: continue
        if any(sd in p.parts for sd in SKIP_DIRS): continue
        # ignore backups like foo.py.bak / foo.json.bak12
        if any(s.lower().startswith(".bak") for s in p.suffixes): continue
        yield p

def line_is_status_write(line: str) -> bool:
    if not NEAR_STATUS.search(line): return False
    if not BAD.search(line): return False
    # assignment/comparison/SQL-ish contexts
    return bool(re.search(r"(=|:=|==|\bin\b|\bSET\b|\bVALUES\b|\bUPDATE\b|\bINSERT\b|\bjson_build_object\b|\bjsonb_set\b)", line, re.I))

def sql_window_has_status_update(block: str) -> bool:
    if re.search(r"\bUPDATE\b[^\n]*\btasks\b[^\n]*\bSET\b[^\n]*\bstatus\b", block, re.I) and BAD.search(block):
        return True
    if re.search(r"\bINSERT\b[^\n]*\bINTO\b[^\n]*\btasks\b.*\bstatus\b.*\bVALUES\b", block, re.I|re.S) and BAD.search(block):
        return True
    return False

def propose_fix(line: str) -> str:
    if not line_is_status_write(line): return line
    def repl(m):
        w = m.group(0)
        return MAP.get(w.lower(), w)
    return SUB.sub(repl, line)

def fix_file(path: pathlib.Path):
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines(True)
    changed = 0
    out = []
    for i, ln in enumerate(lines):
        new = ln
        win = "".join(lines[max(0, i-3): i+4])  # small SQL window
        if line_is_status_write(ln) or (path.suffix.lower()==".sql" and sql_window_has_status_update(win)):
            n2 = propose_fix(ln)
            if n2 != ln:
                changed += 1
                new = n2
        out.append(new)
    return changed, "".join(out), src

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    total_hits = 0
    total_changed = 0

    for p in files():
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        hits = []
        for i, ln in enumerate(src.splitlines(True), 1):
            if line_is_status_write(ln):
                hits.append((i, ln.rstrip("\n")))
        if hits:
            total_hits += len(hits)
            print(f"\n==> {p}")
            for lnno, txt in hits:
                print(f"  {lnno:>5}: {txt}")

        if args.fix or args.diff:
            changed, newsrc, oldsrc = fix_file(p)
            if changed:
                total_changed += changed
                if args.diff:
                    diff = difflib.unified_diff(oldsrc.splitlines(True), newsrc.splitlines(True),
                                                fromfile=str(p), tofile=str(p))
                    sys.stdout.writelines(diff)
                if args.fix:
                    bak = p.with_suffix(p.suffix + ".bak")
                    if not bak.exists():
                        bak.write_text(oldsrc, encoding="utf-8")
                    p.write_text(newsrc, encoding="utf-8")

    if total_hits == 0:
        print("No obvious non-canonical status writes found.")
    if args.fix:
        print(f"\nApplied conservative fixes. Changed lines: {total_changed}")

if __name__ == "__main__":
    main()
