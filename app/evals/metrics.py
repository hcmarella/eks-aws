"""Eval metrics for the three layers: retrieval (RAG), LLM calls, and the agent as a whole. Pure functions, no model needed."""
import math
from statistics import median


# ---- 1. Retrieval: personas / rules / evidence / similar past cases -------------------------------------------
def precision_at_k(retrieved, relevant, k=None):
    r = retrieved[:k] if k else retrieved
    return sum(1 for x in r if x in relevant) / len(r) if r else 0.0


def recall(retrieved, relevant):  # "completeness": did we get everything needed?
    return sum(1 for x in relevant if x in retrieved) / len(relevant) if relevant else 1.0


def ndcg(retrieved, gains, k=None):
    """gains: dict item -> graded relevance (0 = noise). Are the most useful items at the top?"""
    r = retrieved[:k] if k else retrieved
    dcg = sum(gains.get(x, 0) / math.log2(i + 2) for i, x in enumerate(r))
    ideal = sorted(gains.values(), reverse=True)[: len(r)]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


# ---- 2. LLM call: grounding, rules, format -----------------------------------------------------------------------
def grounded_rate(cited_ids_per_answer, supplied_ids_per_answer):
    ok = sum(1 for c, s in zip(cited_ids_per_answer, supplied_ids_per_answer) if set(c) <= set(s))
    return ok / len(cited_ids_per_answer) if cited_ids_per_answer else 1.0


def schema_valid_rate(flags):
    return sum(flags) / len(flags) if flags else 1.0


# ---- 3. Agent: did it finish the job, how well, at what cost -------------------------------------------------------
def agent_scores(runs):
    """runs: list of dicts {status, expected, got, tool_calls, tool_errors, retries, tokens, latency_ms}."""
    n = len(runs)
    if not n:
        return {}
    done = [r for r in runs if r["status"] == "ok"]
    calls = sum(r.get("tool_calls", 0) for r in runs)
    lat = sorted(r["latency_ms"] for r in runs)
    return {
        "cases": n,
        "completion_rate": len(done) / n,
        "verdict_accuracy": sum(1 for r in done if r.get("expected") == r.get("got")) / len(done) if done else 0.0,
        "tool_error_rate": sum(r.get("tool_errors", 0) for r in runs) / calls if calls else 0.0,
        "avg_retries": sum(r.get("retries", 0) for r in runs) / n,
        "tokens_per_completed": sum(r.get("tokens", 0) for r in done) / len(done) if done else 0.0,
        "latency_p50_ms": median(lat),
        "latency_p95_ms": lat[min(n - 1, math.ceil(0.95 * n) - 1)],
    }
