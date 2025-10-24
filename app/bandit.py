from __future__ import annotations
import os, random, hashlib
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

BANDIT_EPSILON = float(os.getenv("BANDIT_EPSILON", "0.1"))
PRIOR_MEAN = 0.5     # optimistic prior
PRIOR_COUNT = 1.0    # Laplace smoothing

def feature_hash(features: Dict[str, Any]) -> str:
    # stable text key -> sha1
    key = f"{features.get('language','any')}|{features.get('repo_bucket','s')}|{int(bool(features.get('tests_present',False)))}|{features.get('ctx_bucket','8k')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()

def extract_features(job: dict) -> Dict[str, Any]:
    # language
    lang = job["input"].get("language", "any")

    # repo_bucket heuristic = number of include globs / size buckets
    inc = (job["input"].get("repo") or {}).get("include", []) or []
    repo_bucket = "s" if len(inc) <= 3 else ("m" if len(inc) <= 15 else "l")

    # tests_present if oracle.full or any "test" in goal/paths
    goal = (job["input"].get("goal") or "").lower()
    expected = ((job.get("output_contract") or {}).get("expected_files") or [])
    tests_present = "test" in goal or any("test" in p.lower() for p in expected)

    # ctx bucket from model ctx or constraints (we don’t know model yet → use constraint hint)
    constraints = (job["input"].get("constraints") or {})
    max_tokens = constraints.get("max_tokens", 2048)
    ctx_bucket = "4k" if max_tokens <= 4096 else ("8k" if max_tokens <= 8192 else "16k+")

    return dict(language=lang, repo_bucket=repo_bucket, tests_present=tests_present, ctx_bucket=ctx_bucket)

async def upsert_stat(conn: AsyncConnection, model: str, fhash: str, reward: float) -> None:
    await conn.execute(text("""
        INSERT INTO bandit_stats(model, feature_hash, runs, reward_sum, reward_sq_sum, last_updated)
        VALUES (:model, :fh, 1, :r, :r2, now())
        ON CONFLICT (model, feature_hash)
        DO UPDATE SET
            runs = bandit_stats.runs + 1,
            reward_sum = bandit_stats.reward_sum + EXCLUDED.reward_sum,
            reward_sq_sum = bandit_stats.reward_sq_sum + EXCLUDED.reward_sq_sum,
            last_updated = now()
    """), dict(model=model, fh=fhash, r=reward, r2=reward*reward))

async def get_stats_for_models(conn: AsyncConnection, models: List[str], fhash: str) -> Dict[str, Tuple[int, float]]:
    if not models:
        return {}
    rows = await conn.execute(text("""
        SELECT model, runs, reward_sum
        FROM bandit_stats
        WHERE feature_hash = :fh AND model = ANY(:models)
    """), dict(fh=fhash, models=models))
    out: Dict[str, Tuple[int, float]] = {}
    for model, runs, reward_sum in rows:
        out[model] = (int(runs or 0), float((reward_sum or 0.0)))
    return out

def estimate_mean(runs: int, reward_sum: float) -> float:
    return (reward_sum + PRIOR_MEAN * PRIOR_COUNT) / (runs + PRIOR_COUNT)

async def rank_models(conn: AsyncConnection, candidates: List[Dict[str, Any]], fhash: str, epsilon: Optional[float] = None) -> List[Dict[str, Any]]:
    """Return candidates ordered for selection, epsilon-greedy on bandit mean."""
    if epsilon is None:
        epsilon = BANDIT_EPSILON
    if not candidates:
        return []
    full_names = [_format_model_name(m) for m in candidates]
    stats = await get_stats_for_models(conn, full_names, fhash)

    # compute means
    annotated = []
    for m, name in zip(candidates, full_names):
        runs, rs = stats.get(name, (0, 0.0))
        mean = estimate_mean(runs, rs)
        annotated.append((m, name, runs, mean))

    # epsilon: with prob epsilon, shuffle randomly
    if random.random() < epsilon:
        random.shuffle(annotated)
    else:
        annotated.sort(key=lambda t: (-t[3], t[0].get("speed_rank", 999)))  # higher mean first, then speed_rank

    return [t[0] for t in annotated]

def _format_model_name(m: Dict[str, Any]) -> str:
    size = str(m.get("size","")).lower()
    size_tag = size if size.endswith("b") else (f"{size}b" if size else "")
    quant = m.get("quant","")
    return f"{m.get('name')}:{size_tag}-{quant}".strip("-")
