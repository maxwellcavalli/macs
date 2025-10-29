from __future__ import annotations
from prometheus_client import Counter, Histogram

router_route_count = Counter("router_route_count", "Routes taken by router", ["model","language"])
compile_pass_total = Counter("compile_pass_total", "Compile successes")
test_smoke_pass_total = Counter("test_smoke_pass_total", "Smoke test successes")
duel_selection_decisions_total = Counter("duel_selection_decisions_total","Duel decisions",["winner","loser"])
# New: count decisions by rule version (doesn't break existing dashboards)
duel_rule_decisions_total = Counter("duel_rule_decisions_total","Duel decisions by rule",["rule_version"])

http_latency = Histogram("http_request_duration_seconds","HTTP latencies",["route","method"])
sse_terminated_total = Counter("sse_terminated_total","SSE terminations",["reason"])
llm_first_token_latency = Histogram(
    "llm_first_token_latency_seconds",
    "Latency from request start until first token is received",
    ["model"],
)
llm_generation_latency = Histogram(
    "llm_generation_latency_seconds",
    "Total time spent streaming model output per request",
    ["model"],
)
