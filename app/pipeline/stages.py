"""BAU stages as LangGraph nodes. SKELETONS: each reads state, calls the runner, returns a ledger-first result. Replace bodies per stage."""
from typing import TypedDict


class CaseState(TypedDict, total=False):
    case_id: str
    data_version: int
    segments: list
    findings: list
    frozen: bool
    votes: list
    bugs: list
    replans: int
    outcome: str
    seal: str


def plan_segments(s): return {"segments": s.get("segments", [])}
def segment_checks(s): return {"findings": s.get("findings", [])}
def census(s): return {}
def freeze(s): return {"frozen": True}
def vote(s): return {"votes": s.get("votes", [])}
def red_team(s): return {"bugs": s.get("bugs", [])}


def outcome(s):
    return {"outcome": "HOLD" if s.get("bugs") else "PUBLISH"}


def seal(s):
    import hashlib, json
    return {"seal": hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()}


def excel(s): return {}
def publish(s): return {}


STAGES = {f.__name__: f for f in (plan_segments, segment_checks, census, freeze, vote, red_team, outcome, seal, excel, publish)}
