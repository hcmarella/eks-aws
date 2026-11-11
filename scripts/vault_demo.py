"""Local walkthrough: protect -> agent run -> validate -> reveal -> deliver -> destroy key. No AWS needed."""
import os, sys
os.environ.update(MODEL_RUNNER="replay", MEMORY_BACKEND="memory", GUARDRAILS="off")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import vault, agentcore_app

keys, vaults = vault.LocalKeyStore(), vault.LocalVaultStore()
raw = {"case_id": "demo-1", "customer_name": "Jane Doe", "account": "000123456789", "ip": "203.0.113.77",
       "notes": "stolen card 4111 1111 1111 1111 used, ssn 123-45-6789, unauthorized charge"}

print("1. RAW (never leaves the trusted side):\n  ", raw)
safe = vault.protect("demo-1", raw, ["customer_name", "account"], keys, vaults, free_text_fields=["notes"])
print("2. WHAT THE AGENT, LANGFUSE AND LOGS SEE:\n  ", safe)
print("   key stored for case:", keys.exists("demo-1"))

text = f"{safe['customer_name']} {safe['account']} {safe['ip']} {safe['notes']}"
out = agentcore_app.invoke({"case_id": "demo-1", "text": text})
report = f"Verdict: {out['label']}. Customer {safe['customer_name']}, account {safe['account']}."
print("3. AGENT REPORT (tokens only):\n  ", report)

delivered = []
final = vault.finalize("demo-1", report, validate=lambda r: "Verdict:" in r, deliver=delivered.append, keys=keys, vaults=vaults)
print("4. DELIVERED TO USER (revealed):\n  ", final)
print("5. KEY STILL EXISTS AFTER DELIVERY:", keys.exists("demo-1"))
try:
    vault.reveal("demo-1", report, keys, vaults)
except vault.KeyDestroyed:
    print("6. REVEAL AFTER DESTROY -> refused (KeyDestroyed). Data is unrecoverable.")
