import os, sys, importlib, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _fresh(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import agentcore_app
    importlib.reload(agentcore_app)
    return agentcore_app


def test_invoke_returns_label_and_logs(monkeypatch):
    m = _fresh(monkeypatch, MODEL_RUNNER="replay", MEMORY_BACKEND="memory")
    out = m.invoke({"case_id": "t1", "text": "unauthorized charge"})
    assert out["label"] == "fraud" and out["thread_id"] == "t1"


def test_same_thread_keeps_state(monkeypatch):
    m = _fresh(monkeypatch, MODEL_RUNNER="replay", MEMORY_BACKEND="memory")
    m.invoke({"case_id": "t2", "text": "stolen card"})
    st = m.graph().get_state({"configurable": {"thread_id": "t2"}})
    assert st.values["label"] == "fraud"


def test_unknown_backend_fails_loudly(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "nope")
    from memory import get_checkpointer
    with pytest.raises(ValueError):
        get_checkpointer()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL for the Postgres check")
def test_postgres_checkpoint_survives_new_saver(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("DB_SETUP", "1")
    monkeypatch.setenv("MODEL_RUNNER", "replay")
    from graph import build
    from memory import get_checkpointer
    cfg = {"configurable": {"thread_id": "pg-t1"}}
    build(checkpointer=get_checkpointer()).invoke({"case_id": "pg-t1", "text": "stolen"}, config=cfg)
    again = build(checkpointer=get_checkpointer()).get_state(cfg)
    assert again.values["label"] == "fraud"
