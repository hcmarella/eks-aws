"""AgentCore Runtime entry point. The runtime calls POST /invocations and GET /ping on port 8080."""
import logging, os, time, json
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from graph import build
from memory import get_checkpointer
import guardrails

log = logging.getLogger("fraudagent")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")

app = BedrockAgentCoreApp()
_graph = None


def graph():
    global _graph
    if _graph is None:  # built once per session, not per request
        _graph = build(checkpointer=get_checkpointer())
    return _graph


@app.entrypoint
def invoke(payload, context=None):
    case_id = payload.get("case_id", "demo-1")
    text = payload.get("text", "")
    if guardrails.enabled():
        text, _ = guardrails.mask(text)  # raw PII never enters graph state, checkpoints, logs or traces
    thread_id = payload.get("thread_id") or case_id  # same thread_id = resume from the last checkpoint
    t0 = time.time()
    try:
        out = graph().invoke({"case_id": case_id, "text": text}, config={"configurable": {"thread_id": thread_id}})
        status = "ok"
    except Exception as e:  # one JSON line per outcome for CloudWatch Logs Insights
        log.error(json.dumps({"case_id": case_id, "thread_id": thread_id, "status": "error", "error": type(e).__name__}))
        raise
    log.info(json.dumps({"case_id": case_id, "thread_id": thread_id, "status": status,
                         "env": os.getenv("APP_ENV", "local"), "latency_ms": int((time.time() - t0) * 1000)}))
    return {"case_id": case_id, "thread_id": thread_id, "label": out.get("label"), "answer": out.get("answer")}


if __name__ == "__main__":
    app.run()
