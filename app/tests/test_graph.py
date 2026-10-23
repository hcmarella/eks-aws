import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from graph import build
from dispatcher import job_spec


def test_graph_replay():
    out = build(lambda p: "ok").invoke({"case_id": "c1", "text": "Unauthorized charge"})
    assert out["label"] == "fraud" and out["answer"] == "ok"


def test_graph_other():
    assert build(lambda p: "x").invoke({"case_id": "c2", "text": "hello"})["label"] == "other"


def test_job_spec_limits():
    j = job_spec("C_1", 3, "img:abc", "fraudagent-dev")
    assert j["metadata"]["name"] == "agent-c-1-v3"
    assert j["spec"]["backoffLimit"] == 1 and j["spec"]["activeDeadlineSeconds"] > 0
    assert j["spec"]["template"]["spec"]["containers"][0]["securityContext"]["readOnlyRootFilesystem"]
