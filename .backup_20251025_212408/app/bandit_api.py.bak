from fastapi import APIRouter, HTTPException

try:
    from .bandit_store import record_event, get_stats
except Exception:  # pragma: no cover
    record_event = None
    get_stats = None

router = APIRouter()

@router.post("/v1/bandit/record")
async def bandit_record(payload: dict):
    """Record a bandit reward event: {model, reward, meta?}"""
    if record_event is None:
        raise HTTPException(status_code=503, detail="bandit_store unavailable")
    model = str(payload.get("model") or "unknown")
    try:
        reward = float(payload.get("reward"))
    except Exception:
        raise HTTPException(status_code=422, detail="reward must be a number")
    meta = payload.get("meta") or {}
    record_event(model, reward, meta)
    return {"ok": True}

@router.get("/v1/bandit/stats")
async def bandit_stats():
    """Return per-model aggregated stats {model: {count,sum,avg,last_ts}}."""
    if get_stats is None:
        raise HTTPException(status_code=503, detail="bandit_store unavailable")
    return {"ok": True, "stats": get_stats()}
