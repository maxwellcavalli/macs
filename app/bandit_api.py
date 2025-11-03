from fastapi import APIRouter, HTTPException

try:
    from .bandit_store import record_event, get_stats
except Exception:  # pragma: no cover
    record_event = None
    get_stats = None

router = APIRouter()

@router.post("/v1/bandit/record")
async def bandit_record(payload: dict):
    """
    Record a bandit reward event.
    Accepts: {"model": "...", "reward": 0.8, "meta": {...}}
             {"model_id": "...", "reward": 0.8, "meta": {...}}
    """
    if record_event is None:
        raise HTTPException(status_code=503, detail="bandit_store unavailable")
    model = str(payload.get("model") or payload.get("model_id") or "unknown")
    try:
        # normalized: accept model_id when provided
        model = str(payload.get("model") or payload.get("model_id") or "unknown")
        # normalized: accept model_id when provided
        model = str(payload.get("model") or payload.get("model_id") or "unknown")
        reward = float(payload.get("reward"))
    except Exception:
        raise HTTPException(status_code=422, detail="reward must be a number")
    meta = payload.get("meta") or {}
    if payload.get("model_id") and not payload.get("model"):
        meta = {**meta, "model_id": str(payload["model_id"])}
    # Keep model_id in meta if provided (useful for later migrations)
    if "model_id" in payload and "model" not in payload:
        meta = {**meta, "model_id": str(payload["model_id"])}
    record_event(model, reward, meta)
    return {"ok": True, "resolved_model": model}

@router.get("/v1/bandit/stats")
async def bandit_stats():
    """Return per-model aggregated stats {model: {count,sum,avg,last_ts}}."""
    if get_stats is None:
        raise HTTPException(status_code=503, detail="bandit_store unavailable")
    return {"ok": True, "backend": "file", "stats": get_stats()}
