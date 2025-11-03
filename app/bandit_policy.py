from __future__ import annotations
import math, random
from typing import Dict, Iterable, List, Tuple

def aggregate_by_model(rows: List[dict]) -> Dict[str, dict]:
    agg: Dict[str, dict] = {}
    for r in rows:
        m = r.get("model_id") or "unknown"
        n = int(r.get("n") or 0)
        wins = int(r.get("wins") or 0)
        ssum = float(r.get("sum_reward") or 0.0)
        last_ts = int(r.get("last_ts") or 0)
        a = agg.setdefault(m, {"n": 0, "wins": 0, "sum_reward": 0.0, "last_ts": 0})
        a["n"] += n
        a["wins"] += wins
        a["sum_reward"] += ssum
        if last_ts > a["last_ts"]:
            a["last_ts"] = last_ts
    return agg

def select_ucb(agg: Dict[str, dict], candidates: Iterable[str], exploration: float = 1.0, use_wins: bool = True) -> Tuple[str, List[dict]]:
    keys = list(candidates)
    N = sum(int(agg.get(k, {}).get("n", 0)) for k in keys)
    if N <= 0:
        # No prior data: pick uniformly at random
        pick = random.choice(keys)
        return pick, [{"model": k, "n": 0, "mean": 0.0, "score": float("inf")} for k in keys]
    best_key = None
    best_score = float("-inf")
    details: List[dict] = []
    for k in keys:
        a = agg.get(k, {"n": 0, "wins": 0, "sum_reward": 0.0})
        n = int(a.get("n", 0))
        mean = (a["wins"]/n) if (use_wins and n > 0) else ((a["sum_reward"]/n) if n > 0 else 0.0)
        bonus = float("inf") if n == 0 else exploration * math.sqrt((2.0 * math.log(max(N,1))) / n)
        score = mean + bonus
        details.append({"model": k, "n": n, "mean": round(mean, 6), "score": (score if score != float("inf") else 1e9)})
        if score > best_score:
            best_score, best_key = score, k
    return best_key, details

def select_thompson(agg: Dict[str, dict], candidates: Iterable[str]) -> Tuple[str, List[dict]]:
    best_key = None
    best_sample = -1.0
    details: List[dict] = []
    for k in candidates:
        a = agg.get(k, {"n": 0, "wins": 0})
        n = int(a.get("n", 0))
        w = int(a.get("wins", 0))
        alpha = 1 + w
        beta = 1 + (n - w)
        sample = random.betavariate(alpha, beta)
        details.append({"model": k, "n": n, "wins": w, "alpha": alpha, "beta": beta, "sample": sample})
        if sample > best_sample:
            best_sample, best_key = sample, k
    return best_key, details
