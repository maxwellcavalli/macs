from __future__ import annotations
import os, time
from typing import Dict, Any
import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
# simple heuristic to mirror Ollama's "low vram mode" threshold we saw (<20 GiB)
GPU_VRAM_GB = float(os.getenv("GPU_VRAM_GB", "0") or 0.0)

async def get_ollama_health() -> Dict[str, Any]:
    start = time.time()
    async with httpx.AsyncClient(timeout=5.0) as cx:
        # version
        ver = "unknown"
        try:
            r = await cx.get(f"{OLLAMA_HOST}/api/version")
            r.raise_for_status()
            jd = r.json()
            ver = jd.get("version") or jd.get("data") or "unknown"
        except Exception as e:
            return {
                "ok": False,
                "error": f"version: {e}",
                "latency_ms": int((time.time()-start)*1000),
                "version": ver,
                "tags_count": 0,
                "low_vram_mode": (GPU_VRAM_GB > 0 and GPU_VRAM_GB < 20.0),
            }

        # tags
        tags_count = 0
        try:
            r2 = await cx.get(f"{OLLAMA_HOST}/api/tags")
            r2.raise_for_status()
            data = r2.json()
            models = data.get("models") or []
            tags_count = len(models)
        except Exception as e:
            return {
                "ok": False,
                "error": f"tags: {e}",
                "latency_ms": int((time.time()-start)*1000),
                "version": ver,
                "tags_count": tags_count,
                "low_vram_mode": (GPU_VRAM_GB > 0 and GPU_VRAM_GB < 20.0),
            }

    return {
        "ok": True,
        "latency_ms": int((time.time()-start)*1000),
        "version": ver,
        "tags_count": tags_count,
        # heuristic: if you provided GPU_VRAM_GB and it's < 20 we mark low_vram
        "low_vram_mode": (GPU_VRAM_GB > 0 and GPU_VRAM_GB < 20.0),
    }
