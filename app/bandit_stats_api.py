from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.api_route("/v1/bandit/stats_unified", methods=["GET","HEAD"])
async def bandit_stats_unified():
    try:
        from .bandit_service import get_stats_unified
        backend, rows = get_stats_unified()
        return JSONResponse({"ok": True, "backend": backend, "stats": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
