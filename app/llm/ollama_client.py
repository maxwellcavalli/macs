from __future__ import annotations
import os, asyncio, json, time
from typing import Optional, AsyncIterator, Dict, Any, Set
import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_AUTOPULL = os.getenv("OLLAMA_AUTOPULL", "true").lower() in ("1","true","yes")
OLLAMA_TAG_CACHE_TTL = float(os.getenv("OLLAMA_TAG_CACHE_TTL", "30") or "30")

class OllamaError(RuntimeError):
    pass

_TAG_CACHE_LOCK = asyncio.Lock()
_TAG_CACHE: Dict[str, Any] = {"ts": 0.0, "data": set()}

async def _fetch_tags() -> Set[str]:
    url = f"{OLLAMA_HOST}/api/tags"
    async with httpx.AsyncClient(timeout=10.0) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        data = r.json()
        models = data.get("models") or []
        out: Set[str] = set()
        for m in models:
            s = m.get("model") or ""
            if s:
                out.add(str(s))
        return out

async def _tags() -> Set[str]:
    now = time.monotonic()
    async with _TAG_CACHE_LOCK:
        cached = _TAG_CACHE.get("data") or set()
        ts = float(_TAG_CACHE.get("ts") or 0.0)
        if cached and (now - ts) <= OLLAMA_TAG_CACHE_TTL:
            return set(cached)
    tags: Set[str] = set()
    try:
        tags = await _fetch_tags()
    except Exception:
        # best effort: fall back to cached snapshot if available, else re-raise
        async with _TAG_CACHE_LOCK:
            cached = _TAG_CACHE.get("data") or set()
            if cached:
                return set(cached)
        raise
    async with _TAG_CACHE_LOCK:
        _TAG_CACHE["data"] = set(tags)
        _TAG_CACHE["ts"] = time.monotonic()
    return tags

async def _pull(model: str) -> None:
    url = f"{OLLAMA_HOST}/api/pull"
    payload = {"model": model, "stream": False}
    async with httpx.AsyncClient(timeout=None) as cx:
        try:
            r = await cx.post(url, json=payload)
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                await exc.response.aread()
                detail = exc.response.text.strip()
            except Exception:
                detail = ""
            msg = f"Ollama pull failed (status={exc.response.status_code})"
            if detail:
                msg += f": {detail}"
            raise OllamaError(msg) from exc
        # returns {"status":"done"} on completion
        try:
            _ = r.json()
        except json.JSONDecodeError:
            detail = r.text.strip()
            msg = "Ollama pull returned unexpected response format"
            if detail:
                msg += f": {detail[:200]}"
            raise OllamaError(msg) from None

async def ensure_model(model: str) -> None:
    try:
        tags = await _tags()
        if model in tags:
            return
        if not OLLAMA_AUTOPULL:
            raise OllamaError(f"Model '{model}' not present and autopull disabled")
        await _pull(model)
    except httpx.HTTPError as e:
        raise OllamaError(f"Ollama error listing/pulling models: {e}") from e

async def generate_stream(
    model: str,
    prompt: str,
    *,
    num_ctx: Optional[int] = None,
    temperature: Optional[float] = 0.2,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Yields chunks from /api/generate stream:
      {"response": "<text>", "done": false}
      ...
      {"done": true, "total_duration": ..., "eval_count": ...}
    """
    await ensure_model(model)
    url = f"{OLLAMA_HOST}/api/generate"
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {}
    }
    if num_ctx:
        payload["options"]["num_ctx"] = int(num_ctx)
    if temperature is not None:
        payload["options"]["temperature"] = float(temperature)

    async with httpx.AsyncClient(timeout=None) as cx:
        try:
            async with cx.stream("POST", url, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        # sometimes blank/partial lines slip; skip quietly
                        continue
                    yield obj
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                await exc.response.aread()
                detail = exc.response.text.strip()
            except Exception:
                detail = ""
            msg = f"Ollama generate failed (status={exc.response.status_code})"
            if detail:
                msg += f": {detail[:200]}"
            raise OllamaError(msg) from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama generate request error: {exc}") from exc
