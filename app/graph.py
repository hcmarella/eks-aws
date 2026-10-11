"""Minimal LangGraph. Same code runs local / dev / qa / prod; only the runner and DB URL change (env vars)."""
import os
from typing import TypedDict
from langgraph.graph import StateGraph, END


class State(TypedDict, total=False):
    case_id: str
    text: str
    label: str
    answer: str


def get_runner():
    """MODEL_RUNNER = replay (default, no model, local tests) | anthropic (local only) | bedrock (dev/qa/prod)."""
    kind = os.getenv("MODEL_RUNNER", "replay")
    if kind == "replay":
        return lambda prompt: "REPLAY:" + prompt[:40]
    if kind == "bedrock":
        import boto3, json
        client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        model_id = os.environ["BEDROCK_MODEL_ID"]
        def run(prompt):
            r = client.converse(modelId=model_id, messages=[{"role": "user", "content": [{"text": prompt}]}])
            return r["output"]["message"]["content"][0]["text"]
        return run
    if kind == "anthropic":  # synthetic data only; needs approval
        import anthropic
        c = anthropic.Anthropic()
        model_id = os.environ["ANTHROPIC_MODEL_ID"]
        return lambda p: c.messages.create(model=model_id, max_tokens=500,
                                           messages=[{"role": "user", "content": p}]).content[0].text
    raise ValueError(f"unknown MODEL_RUNNER {kind}")


def build(runner=None):
    runner = runner or get_runner()

    def classify(s: State) -> State:
        t = s["text"].lower()
        return {"label": "fraud" if any(w in t for w in ("chargeback", "unauthorized", "stolen")) else "other"}

    def answer(s: State) -> State:
        return {"answer": runner(f"Case {s['case_id']} labelled {s['label']}: {s['text']}")}

    g = StateGraph(State)
    g.add_node("classify", classify)
    g.add_node("answer", answer)
    g.set_entry_point("classify")
    g.add_edge("classify", "answer")
    g.add_edge("answer", END)
    return g.compile()
