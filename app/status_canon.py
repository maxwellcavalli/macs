# Reusable helper for source code writes/reads
CANON = {"queued","running","done","error","canceled"}
MAP = {
    "succeeded":"done","success":"done","completed":"done","complete":"done",
    "failed":"error","failure":"error","fail":"error",
    "cancelled":"canceled",
}
def canon_status(s: str) -> str:
    v = (s or "").strip().lower()
    v = MAP.get(v, v)
    if v not in CANON:
        raise ValueError(f"Invalid status {s!r} (use one of {sorted(CANON)})")
    return v
