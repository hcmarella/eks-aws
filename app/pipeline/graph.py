"""Builds the BAU graph from config/pipeline.yaml. Bug loop: red_team -> plan_segments, capped by limits.replan_max."""
import os, yaml
from langgraph.graph import StateGraph, END
from .stages import CaseState, STAGES

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config", "pipeline.yaml")))


def build():
    g = StateGraph(CaseState)
    names = CFG["stages"]
    for n in names:
        g.add_node(n, STAGES[n])
    g.set_entry_point(names[0])
    for a, b in zip(names, names[1:]):
        if a == "red_team" and "plan_segments" in names:
            cap = CFG["limits"]["replan_max"]
            g.add_conditional_edges(a, lambda s, b=b: "plan_segments" if s.get("bugs") and s.get("replans", 0) < cap else b,
                                    {"plan_segments": "plan_segments", b: b})
        else:
            g.add_edge(a, b)
    g.add_edge(names[-1], END)
    return g.compile()
