import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline.graph import build


def test_pipeline_runs_and_seals():
    out = build().invoke({"case_id": "c1"})
    assert out["outcome"] == "PUBLISH" and len(out["seal"]) == 64
