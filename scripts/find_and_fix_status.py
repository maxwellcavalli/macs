#!/usr/bin/env python3
"""
Find (and optionally fix) code paths that write non-canonical task statuses.

Canonical values: queued | running | done | error | canceled
Non-canonical we hunt: succeeded, success, completed, complete, failed, failure, fail, cancelled

Usage:
  python scripts/find_and_fix_status.py                # report only
  python scripts/find_and_fix_status.py --fix          # in-place fixes (conservative)
  python scripts/find_and_fix_status.py --diff         # show unified diffs of proposed fixes
"""
import argparse, pathlib, re, sys, difflib

ROOT = pathlib.Path(".")
FILES = [".py",".ts",".tsx",".js",".jsx",".go",".sql",".yml",".yaml",".json"]

BAD = r"\b(succeeded|success|completed|complete|failed|failure|fail|cancelled)\b"
NEAR_STATUS = re.compile(r"status", re.I)
BAD_WORD = re.compile(BAD, re.I)

# Only fix when 'status' is on the same line (or obvious SQL json/kv assignment)
FIX_MAP = {
    "succeeded":"done", "success":"done", "completed":"done", "complete":"done",
    "failed":"error", "failure":"error", "fail":"error", "cancelled":"canceled",
}
FIX_PAT = re.compile(BAD, re.I)

def candidate_files():
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        if p.suffix.lower() in FILES and "node_modules" not in p.parts and "venv" not in p.parts and "dist" not in p.parts and "build" not in p.parts:
            yield p

def line_has_status_write(line: str) -> bool:
    # looks like an assignment/comparison for a status field or column
    return bool(
        NEAR_STATUS.search(line)
        and re.search(r"(=|:=|:|==|\bin\b|\bSET\b|\bVALUES\b|\bUPDATE\b|\bINSERT\b|\bjson_build_object\b|\bjsonb_set\b)", line, re.I)
        and BAD_WORD.search(line)
    )

def sql_block_has_status_update(block: str) -> bool:
    # capture multi-line SQL updates/inserts
    if re.search(r"\bUPDATE\b[^\n]*\btasks\b[^\n]*\bSET\b[^\n]*\bstatus\b", block, re.I) and BAD_WORD.search(block):
        return True
    if re.search(r"\bINSERT\b[^\n]*\bINTO\b[^\n]*\btasks\b.*\bstatus\b.*\bVALUES\b", block, re.I|re.S) and BAD_WORD.search(block):
        return True
    return False

def propose_fix(line: str) -> str:
    if not line_has_status_write(line):
        return line
    def repl(m):
        w = m.group(0)
        return FIX_MAP.get(w.lower(), w)
    return FIX_PAT.sub(repl, line)

def fix_file(path: pathlib.Path) -> tuple[int, str]:
    src = path.read_text(encoding="utf-8", errors="replace")
    changed = 0
    lines = src.splitlines(True)
    out = []
    for i, ln in enumerate(lines):
        new = ln
        # SQL multi-line assistance (cheap): if previous line mentions UPDATE/INSERT on tasks, allow fix on this too
        window = "".join(lines[max(0, i-2):i+3])
        if line_has_status_write(ln) or (path.suffix.lower()==".sql" and sql_block_has_status_update(window)):
            new = propose_fix(ln)
            if new != ln: changed += 1
        out.append(new)
    return changed, "".join(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="apply conservative in-place fixes")
    ap.add_argument("--diff", action="store_true", help="show unified diffs for proposed fixes")
    args = ap.parse_args()

    total_hits, total_changed = 0, 0
    for p in candidate_files():
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        hits = []
        for i, ln in enumerate(src.splitlines(True), 1):
            if line_has_status_write(ln):
                hits.append((i, ln.rstrip("\n")))
        # also catch loose hits to guide manual review
        loose = []
        for i, ln in enumerate(src.splitlines(True), 1):
            if BAD_WORD.search(ln) and not NEAR_STATUS.search(ln):
                # skip 'successful' etc by word boundaries already, but keep as loose hints
                loose.append((i, ln.rstrip("\n")))
        if hits:
            total_hits += len(hits)
            print(f"\n==> {p}")
            for lnno, txt in hits:
                print(f"  {lnno:>5}: {txt}")
        if not args.fix and not args.diff:
            continue
        changed, newsrc = fix_file(p)
        if changed:
            total_changed += changed
            if args.diff:
                diff = difflib.unified_diff(src.splitlines(True), newsrc.splitlines(True), fromfile=str(p), tofile=str(p))
                sys.stdout.writelines(diff)
            if args.fix:
                # backup once per file
                bak = p.with_suffix(p.suffix + ".bak")
                if not bak.exists():
                    bak.write_text(src, encoding="utf-8")
                p.write_text(newsrc, encoding="utf-8")
    if total_hits == 0:
        print("No obvious problematic writes found.")
    if args.fix:
        print(f"\nApplied conservative fixes in-place. Changed lines: {total_changed}")
    elif args.diff:
        print("\n(Review diffs above; rerun with --fix to apply.)")

if __name__ == "__main__":
    main()
