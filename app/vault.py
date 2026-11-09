"""PII vault: tokenize at intake, reveal at delivery, destroy the per-case key afterwards.

RUN THIS MODULE OUTSIDE THE AGENT RUNTIME (invoker / delivery worker). The agent only ever sees tokens.
If the runtime could read the key or the vault, "no sensitive data reaches AgentCore" would be false.

Flow:  protect()  -> agent + traces see tokens only -> finalize(): validate report -> reveal -> deliver -> destroy key + vault

- Tokens are deterministic (HMAC with the long-lived PII_TOKEN_KEY), so the same value gets the same token across
  cases and linkage analysis still works. Remove that if policy says tokens must not link across cases.
- Real values are stored encrypted (AES-256-GCM) in a vault blob under a fresh random key per case.
  The case id and token are bound into the ciphertext, so a blob cannot be replayed on another case.
- The per-case key lives in a key store (Secrets Manager in AWS). It is deleted only AFTER delivery succeeded.
"""
import base64, os, re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import guardrails

TOKEN_RX = re.compile(r"<[A-Z_]+_[0-9a-f]{8}>")


class VaultError(Exception):
    pass


class KeyDestroyed(VaultError):
    """The per-case key no longer exists, so the data cannot be revealed."""


# ---------------- key stores ----------------
class LocalKeyStore:
    """Local practice only. Keys are held in memory."""
    def __init__(self): self._k = {}
    def put(self, case_id, key):
        if case_id in self._k: raise VaultError(f"key already exists for {case_id}")
        self._k[case_id] = key
    def get(self, case_id):
        if case_id not in self._k: raise KeyDestroyed(case_id)
        return self._k[case_id]
    def delete(self, case_id): self._k.pop(case_id, None)
    def exists(self, case_id): return case_id in self._k


class SecretsManagerKeyStore:
    """One secret per case, deleted when the case is delivered. Pass a boto3 'secretsmanager' client.
    recovery_days=None deletes immediately (ForceDeleteWithoutRecovery); otherwise 7-30 days of recovery.
    Ask security which they allow: with a recovery window the key is not truly gone for that long."""
    def __init__(self, client, env="dev", recovery_days=None):
        self.c, self.env, self.recovery_days = client, env, recovery_days
    def _name(self, case_id): return f"fraudagent/{self.env}/case/{case_id}"
    def put(self, case_id, key):
        try:
            self.c.create_secret(Name=self._name(case_id), SecretBinary=key)
        except self.c.exceptions.ResourceExistsException:
            raise VaultError(f"key already exists for {case_id}")
    def get(self, case_id):
        try:
            return self.c.get_secret_value(SecretId=self._name(case_id))["SecretBinary"]
        except (self.c.exceptions.ResourceNotFoundException, self.c.exceptions.InvalidRequestException):
            raise KeyDestroyed(case_id)  # InvalidRequest = scheduled for deletion
    def delete(self, case_id):
        kw = {"ForceDeleteWithoutRecovery": True} if self.recovery_days is None else {"RecoveryWindowInDays": self.recovery_days}
        try:
            self.c.delete_secret(SecretId=self._name(case_id), **kw)
        except self.c.exceptions.ResourceNotFoundException:
            pass  # already gone: deleting twice is fine


# ---------------- vault (encrypted token -> value map) ----------------
class LocalVaultStore:
    """Local practice only. In AWS use a KMS-encrypted S3 object or a Lakebase table that only the delivery role can read."""
    def __init__(self): self._v = {}
    def save(self, case_id, blob): self._v[case_id] = blob
    def load(self, case_id):
        if case_id not in self._v: raise VaultError(f"no vault for {case_id}")
        return self._v[case_id]
    def delete(self, case_id): self._v.pop(case_id, None)


# ---------------- operations ----------------
def _aad(case_id, token): return f"{case_id}|{token}".encode()


def protect(case_id, record, pii_fields, keys, vaults, free_text_fields=()):
    """Return a copy of record that is safe for the agent. pii_fields are replaced whole; free_text_fields are scanned."""
    mapping, out = {}, dict(record)
    for f in pii_fields:
        if f in out and out[f] is not None:
            v = str(out[f]); t = guardrails._token(f.upper(), v)
            mapping[t] = v; out[f] = t
    for f in free_text_fields:
        if isinstance(out.get(f), str):
            out[f], m = guardrails.mask(out[f]); mapping.update(m)
    key = AESGCM.generate_key(bit_length=256)
    keys.put(case_id, key)
    aes, blob = AESGCM(key), {}
    for t, v in mapping.items():
        nonce = os.urandom(12)
        blob[t] = base64.b64encode(nonce + aes.encrypt(nonce, v.encode(), _aad(case_id, t))).decode()
    vaults.save(case_id, blob)
    return out


def reveal(case_id, text, keys, vaults):
    """Swap tokens in text for the real values. Raises KeyDestroyed if the key is gone."""
    key = keys.get(case_id); blob = vaults.load(case_id); aes = AESGCM(key)

    def sub(m):
        t = m.group(0)
        if t not in blob: return t  # token not from this vault: leave it
        raw = base64.b64decode(blob[t])
        try:
            return aes.decrypt(raw[:12], raw[12:], _aad(case_id, t)).decode()
        except Exception:
            raise VaultError(f"vault entry {t} failed integrity check")
    return TOKEN_RX.sub(sub, text)


def destroy(case_id, keys, vaults):
    """Idempotent. Remove the key and the vault blob."""
    keys.delete(case_id); vaults.delete(case_id)


def finalize(case_id, report, validate, deliver, keys, vaults):
    """The last step of the graph run, executed by the delivery worker:
    1) validate the TOKENIZED report (golden template, data quality); 2) reveal; 3) deliver; 4) only then destroy the key.
    If validation or delivery fails, nothing is destroyed, so the step can be retried."""
    if not validate(report):
        raise VaultError("report failed validation; key and vault kept")
    revealed = reveal(case_id, report, keys, vaults)
    deliver(revealed)  # must raise on failure
    destroy(case_id, keys, vaults)
    return revealed
