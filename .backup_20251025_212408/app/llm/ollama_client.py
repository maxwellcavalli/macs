from __future__ import annotations
import os, asyncio, json
from typing import Optional, AsyncIterator, Dict, Any
import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_AUTOPULL = os.getenv("OLLAMA_AUTOPULL", "true").lower() in ("1","true","yes")

class OllamaError(RuntimeError):
    pass

async def _tags() -> set[str]:
    url = f"{OLLAMA_HOST}/api/tags"
    async with httpx.AsyncClient(timeout=10.0) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        data = r.json()
        models = data.get("models") or []
        out = set()
        for m in models:
            s = m.get("model") or ""
            if s:
                out.add(s)
        return out

async def _pull(model: str) -> None:
    url = f"{OLLAMA_HOST}/api/pull"
    payload = {"model": model, "stream": False}
    async with httpx.AsyncClient(timeout=None) as cx:
        r = await cx.post(url, json=payload)
        r.raise_for_status()
        # returns {"status":"done"} on completion
        _ = r.json()

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
