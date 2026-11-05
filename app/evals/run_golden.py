"""Run golden cases through the graph and print agent scores. Fails (exit 1) below the thresholds."""
import os, sys, time, yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from graph import build
from evals.metrics import agent_scores

THRESH = {"completion_rate": 1.0, "verdict_accuracy": 1.0}


def main(path=os.path.join(os.path.dirname(__file__), "golden.yaml")):
    g, runs = build(), []
    for c in yaml.safe_load(open(path)):
        t0 = time.time()
        try:
            out = g.invoke({"case_id": c["case_id"], "text": c["text"]})
            runs.append({"status": "ok", "expected": c["expected"], "got": out.get("label"),
                         "latency_ms": int((time.time() - t0) * 1000)})
        except Exception:
            runs.append({"status": "error", "expected": c["expected"], "latency_ms": int((time.time() - t0) * 1000)})
    s = agent_scores(runs)
    print(s)
    return 0 if all(s[k] >= v for k, v in THRESH.items()) else 1


if __name__ == "__main__":
    sys.exit(main())
