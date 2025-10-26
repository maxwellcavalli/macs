from typing import Any, Mapping

CANON = {"queued","running","done","error","canceled"}
MAP = {
    "succeeded":"done", "success":"done", "completed":"done", "complete":"done",
    "failed":"error", "failure":"error", "fail":"error",
    "cancelled":"canceled",
}

def norm_status(s: Any) -> Any:
    if s is None: return s
    v = str(getattr(s, "value", s)).strip().lower()
    return MAP.get(v, v)

def norm_payload(obj: Any) -> Any:
    # Recursively rewrite {"status": "..."} anywhere in the object
    if isinstance(obj, Mapping):
        d = dict(obj)
        if "status" in d:
            d["status"] = norm_status(d["status"])
        for k, v in list(d.items()):
            d[k] = norm_payload(v)
        return d
    if isinstance(obj, list):
        return [norm_payload(x) for x in obj]
    return obj
