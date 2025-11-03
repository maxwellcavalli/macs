from __future__ import annotations
import os, time, re, json
from typing import List, Dict, Any, Tuple
import httpx
import yaml
import subprocess, shutil

# ---------- Config ----------
DEFAULT_CTX = 8192
DISCOVERY_REFRESH_SEC = int(os.getenv("OLLAMA_DISCOVERY_REFRESH_SEC", "60"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# ---------- Helpers ----------
_SIZE_RX = re.compile(r":\s*([0-9]+[bk])", re.IGNORECASE)  # e.g., ":8b", ":7b", ":70b"
_QUANT_RX = re.compile(r"-([qQ][0-9][\w_]*)$")              # e.g., "-q4", "-q4_K_M"

def _heuristic_min_vram_gb(size_tag: str) -> int:
    size_tag = size_tag.lower()
    if size_tag.endswith("7b"):  return 5
    if size_tag.endswith("8b"):  return 6
    if size_tag.endswith("13b"): return 10
    if size_tag.endswith("14b"): return 12
    if size_tag.endswith("33b"): return 24
    if size_tag.endswith("70b"): return 40
    return 4  # reasonable default

def _parse_name_size_quant(model_str: str) -> Tuple[str,str,str]:
    """
    model_str examples:
      "llama3.1:8b"
      "qwen2.5-coder:14b-q4_K_M"
      "mistral:7b-instruct" (quant may be absent)
    Returns (name, size_tag, quant)
    """
    if ":" not in model_str:
        return model_str, "", ""
    name, tag = model_str.split(":", 1)
    size_match = _SIZE_RX.search(":" + tag)  # keep ':' to match RX
    size_tag = size_match.group(1).lower() if size_match else ""
    quant_match = _QUANT_RX.search(tag)
    quant = quant_match.group(1).lower() if quant_match else ""
    return name, size_tag, quant

def _load_file_registry() -> Dict[str, Any]:
    path = os.getenv("MODEL_REGISTRY_PATH", "./config/models.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {"models": []}

def _probe_vram_gb() -> float:
    manual = os.getenv("GPU_VRAM_GB")
    if manual:
        try:
            return float(manual)
        except ValueError:
            pass
    try:
        if shutil.which("nvidia-smi"):
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                text=True
            )
            gb = max(int(x.strip()) for x in out.strip().splitlines()) / 1024.0
            return gb
    except Exception:
        pass
    return 0.0

# ---------- Discovery (cached) ----------
_DISC_CACHE: Dict[str, Any] = {"ts": 0.0, "models": []}

def _fetch_ollama_tags() -> List[Dict[str, Any]]:
    url = f"{OLLAMA_HOST.rstrip('/')}/api/tags"
    try:
        with httpx.Client(timeout=5.0) as cx:
            r = cx.get(url)
            r.raise_for_status()
            data = r.json()
            # Newer Ollama returns {"models":[{"model":"llama3.1:8b", ...}, ...]}
            models = data.get("models") or []
            out = []
            for m in models:
                # prefer "model", fallback to f"{name}:{tag}"
                model_str = m.get("model")
                if not model_str:
                    name = m.get("name")
                    tag = m.get("tag") or ""
                    model_str = f"{name}:{tag}" if name and tag else (name or "")
                if not model_str:
                    continue
                name, size, quant = _parse_name_size_quant(model_str)
                out.append({
                    "name": name,
                    "size": size or "",             # may be empty
                    "quant": quant or "",           # may be empty
                    "tag": model_str,               # keep the exact tag for downstream callers
                    "ctx_size": DEFAULT_CTX,
                    "min_vram_gb": _heuristic_min_vram_gb(size or "7b"),
                    "speed_rank": 5,                # mid default; config can override
                    "langs": ["java", "python", "docs", "planner"],
                    "_source": "ollama",
                })
            return out
    except Exception:
        return []

def _discovered_models() -> List[Dict[str, Any]]:
    now = time.time()
    if now - _DISC_CACHE["ts"] > DISCOVERY_REFRESH_SEC:
        _DISC_CACHE["models"] = _fetch_ollama_tags()
        _DISC_CACHE["ts"] = now
    return _DISC_CACHE["models"]

def _merge_models(config_models: List[Dict[str, Any]], discovered: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # key: name + size + quant
    def k(m): return f"{m.get('name','')}:{m.get('size','')}-{m.get('quant','')}".lower()
    merged: Dict[str, Dict[str, Any]] = {}
    for m in discovered:
        merged[k(m)] = m
    for m in config_models:
        key = k(m)
        # config wins for speed_rank / ctx_size / langs / min_vram if present
        if key in merged:
            base = merged[key]
            base.update({k2: v for k2, v in m.items() if v not in (None, "", [])})
            merged[key] = base
        else:
            merged[key] = m
    # produce list sorted by speed_rank
    items = list(merged.values())
    items.sort(key=lambda x: x.get("speed_rank", 999))
    return items

# ---------- Public API ----------
def available_models(language: str | None = None) -> List[Dict[str, Any]]:
    reg = _load_file_registry()
    discovered = _discovered_models()
    all_models = _merge_models(reg.get("models", []), discovered)
    vram = _probe_vram_gb()

    filtered: List[Dict[str, Any]] = []
    for m in all_models:
        vram_ok = True if vram <= 0 else (vram >= float(m.get("min_vram_gb", 0)))
        lang_ok = True if language is None else (language in m.get("langs", []))
        if vram_ok and lang_ok:
            filtered.append(m)
    filtered.sort(key=lambda x: x.get("speed_rank", 999))
    return filtered


def get_mode_defaults(mode: str, language: str | None = None) -> list[str]:
    reg = _load_file_registry()
    defaults = reg.get("defaults", {})
    keys = [mode]
    if language:
        lang = str(language).lower()
        keys.insert(0, f"{mode}:{lang}")
    out: list[str] = []
    for key in keys:
        raw = defaults.get(key)
        if not raw:
            continue
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            out.extend(str(item) for item in raw)
    return out
