import os, sys, importlib, logging, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import vault
from vault import LocalKeyStore, LocalVaultStore, KeyDestroyed, VaultError

REC = {"case_id": "c9", "customer_name": "Jane Doe", "account": "000123456789", "ip": "203.0.113.77",
       "notes": "stolen card 4111 1111 1111 1111 used; ssn 123-45-6789; unauthorized charge"}
PII = ["customer_name", "account"]
RAW = ["Jane Doe", "000123456789", "4111 1111 1111 1111", "123-45-6789"]


def setup():
    return LocalKeyStore(), LocalVaultStore()


def test_protect_hides_pii_and_keeps_analysis_fields():
    k, v = setup()
    safe = vault.protect("c9", REC, PII, k, v, free_text_fields=["notes"])
    assert safe["ip"] == "203.0.113.77" and "unauthorized charge" in safe["notes"]
    assert not any(r in repr(safe) for r in RAW)


def test_same_value_same_token_across_cases():
    k, v = setup()
    a = vault.protect("c1", REC, PII, k, v)["account"]
    b = vault.protect("c2", REC, PII, k, v)["account"]
    assert a == b


def test_roundtrip_reveal():
    k, v = setup()
    safe = vault.protect("c9", REC, PII, k, v, free_text_fields=["notes"])
    report = f"Account {safe['account']} for {safe['customer_name']}. Notes: {safe['notes']}"
    out = vault.reveal("c9", report, k, v)
    assert all(r in out for r in RAW)


def test_key_destroyed_means_unrecoverable():
    k, v = setup()
    safe = vault.protect("c9", REC, PII, k, v)
    vault.destroy("c9", k, v); vault.destroy("c9", k, v)  # twice is fine
    with pytest.raises(KeyDestroyed):
        vault.reveal("c9", safe["account"], k, v)


def test_ciphertext_cannot_be_moved_to_another_case():
    k, v = setup()
    vault.protect("c1", REC, PII, k, v); vault.protect("c2", {"case_id": "c2", "account": "999"}, PII, k, v)
    tok = vault.protect("c1", REC, PII, LocalKeyStore(), LocalVaultStore())["account"]  # same token, other store
    v.save("c2", {tok: v.load("c1")[tok]})  # copy c1's ciphertext into c2's vault
    with pytest.raises(VaultError):
        vault.reveal("c2", tok, k, v)


def test_finalize_destroys_only_after_successful_delivery():
    k, v = setup()
    safe = vault.protect("c9", REC, PII, k, v)
    rpt = f"acct {safe['account']}"
    with pytest.raises(VaultError):                       # validation fails: keep everything
        vault.finalize("c9", rpt, lambda r: False, lambda r: None, k, v)
    assert k.exists("c9")
    def boom(_): raise RuntimeError("S3 down")
    with pytest.raises(RuntimeError):                      # delivery fails: keep everything, retry possible
        vault.finalize("c9", rpt, lambda r: True, boom, k, v)
    assert k.exists("c9")
    got = []
    out = vault.finalize("c9", rpt, lambda r: True, got.append, k, v)  # success: delivered then destroyed
    assert "000123456789" in got[0] and not k.exists("c9")


def test_agent_traces_and_checkpoints_see_tokens_only(monkeypatch, caplog):
    """End to end: protect outside the runtime, run the graph, scan state, checkpoints and logs for raw values."""
    monkeypatch.setenv("MODEL_RUNNER", "replay"); monkeypatch.setenv("MEMORY_BACKEND", "memory")
    monkeypatch.setenv("GUARDRAILS", "off")  # prove the VAULT alone protects, not the in-runtime regex net
    import agentcore_app; importlib.reload(agentcore_app)
    k, v = setup()
    safe = vault.protect("c9", REC, PII, k, v, free_text_fields=["notes"])
    text = f"{safe['customer_name']} {safe['account']} {safe['notes']}"
    with caplog.at_level(logging.INFO):
        out = agentcore_app.invoke({"case_id": "c9", "text": text})
    saver = agentcore_app.graph().checkpointer
    hay = repr(out) + repr(saver.storage) + repr(saver.blobs) + caplog.text
    assert not any(r in hay for r in RAW)
    assert out["label"] == "fraud"


def test_secrets_manager_store_with_moto():
    boto3 = pytest.importorskip("boto3"); moto = pytest.importorskip("moto")
    with moto.mock_aws():
        c = boto3.client("secretsmanager", region_name="us-east-1")
        k, v = vault.SecretsManagerKeyStore(c, env="dev"), LocalVaultStore()
        safe = vault.protect("c9", REC, PII, k, v)
        assert vault.reveal("c9", safe["account"], k, v) == "000123456789"
        with pytest.raises(VaultError):  # a second protect for the same case must not silently re-key
            vault.protect("c9", REC, PII, k, v)
        vault.destroy("c9", k, v)
        with pytest.raises(KeyDestroyed):
            k.get("c9")
        assert c.list_secrets()["SecretList"] == []  # nothing piles up
