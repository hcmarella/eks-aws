import os, sys, importlib, logging, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import guardrails
from evals import metrics
from evals.run_golden import main as run_golden

SSN, CARD, EMAIL, PHONE = "123-45-6789", "4111 1111 1111 1111", "jane.doe@example.com", "404-555-0187"
RAW = [SSN, CARD, EMAIL, PHONE]
TEXT = f"stolen card {CARD} used; customer {EMAIL} phone {PHONE} ssn {SSN} reported unauthorized charge"


def test_mask_removes_all_and_is_deterministic():
    a, m1 = guardrails.mask(TEXT)
    b, _ = guardrails.mask(TEXT)
    assert a == b and not guardrails.find_pii(a) and len(m1) == 4
    assert all(r not in a for r in RAW)


def test_non_luhn_number_is_not_treated_as_card():
    assert guardrails.mask("order 1234 5678 9012 3456")[0] == "order 1234 5678 9012 3456"


def test_output_with_raw_pii_is_blocked():
    run = guardrails.guarded(lambda p: f"customer ssn is {SSN}")
    with pytest.raises(guardrails.GuardrailViolation):
        run("anything")


def test_unknown_evidence_id_is_blocked():
    with pytest.raises(guardrails.GuardrailViolation):
        guardrails.check_output("supported by E-1 and E-9", allowed_evidence_ids={"E-1", "E-2"})
    assert guardrails.check_output("supported by E-1", allowed_evidence_ids={"E-1"})


def test_canary_pii_never_reaches_state_checkpoints_logs_or_answer(monkeypatch, caplog):
    monkeypatch.setenv("MODEL_RUNNER", "replay"); monkeypatch.setenv("MEMORY_BACKEND", "memory")
    import agentcore_app
    importlib.reload(agentcore_app)
    with caplog.at_level(logging.INFO):
        out = agentcore_app.invoke({"case_id": "canary", "text": TEXT})
    saver = agentcore_app.graph().checkpointer
    haystack = repr(out) + repr(saver.storage) + repr(saver.blobs) + caplog.text
    for raw in RAW:
        assert raw not in haystack, f"raw PII leaked: {raw}"
    assert out["label"] == "fraud"  # masking must not break the detection logic


def test_metrics_retrieval():
    assert metrics.precision_at_k(["a", "b", "c"], {"a", "c"}, 2) == 0.5
    assert metrics.recall(["a"], {"a", "b"}) == 0.5
    assert metrics.ndcg(["b", "a"], {"a": 3, "b": 1}) < 1.0
    assert metrics.ndcg(["a", "b"], {"a": 3, "b": 1}) == 1.0


def test_metrics_agent_scores():
    runs = [{"status": "ok", "expected": "fraud", "got": "fraud", "tool_calls": 4, "tool_errors": 1, "tokens": 100, "latency_ms": 10},
            {"status": "error", "tool_calls": 0, "latency_ms": 30}]
    s = metrics.agent_scores(runs)
    assert s["completion_rate"] == 0.5 and s["tool_error_rate"] == 0.25 and s["tokens_per_completed"] == 100


def test_golden_cases_pass():
    assert run_golden() == 0


def test_card_token_does_not_depend_on_trailing_character():
    a = guardrails.mask("card 4111 1111 1111 1111 used")[0]
    b = guardrails.mask("card 4111 1111 1111 1111.")[0]
    assert a.split()[1] == b.split()[1].rstrip(".") and a == "card " + a.split()[1] + " used"
