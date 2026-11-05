"""PII guardrails. Mask before any model call, check after. Defense in depth, not a replacement for tokenizing
known structured fields (SSN, card, account, phone, email columns) upstream in dbt before data reaches the agent.

Tokens are deterministic per value (HMAC), so "same card appears in 3 transactions" is still visible to the model
without the real number. Free-text detection here is regex based and WILL miss things: treat it as a safety net.
"""
import hmac, hashlib, os, re

_KEY = os.getenv("PII_TOKEN_KEY", "dev-only-key-change-me").encode()

PATTERNS = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE": re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)"),
    "CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
}


class GuardrailViolation(Exception):
    """Raised when model output breaks a rule. The failure model treats it as a validation failure (guided retry, then BLOCKED)."""


def _luhn(num: str) -> bool:
    d = [int(c) for c in num if c.isdigit()]
    if not 13 <= len(d) <= 19:
        return False
    s = 0
    for i, x in enumerate(reversed(d)):
        if i % 2:
            x = x * 2 - 9 if x * 2 > 9 else x * 2
        s += x
    return s % 10 == 0


def _token(kind: str, value: str) -> str:
    return f"<{kind}_{hmac.new(_KEY, value.encode(), hashlib.sha256).hexdigest()[:8]}>"


def mask(text: str):
    """Return (masked_text, mapping token->original). Keep the mapping out of state, logs and traces."""
    mapping = {}

    def sub(kind):
        def f(m):
            v = m.group(0)
            if kind == "CARD" and not _luhn(v):
                return v
            t = _token(kind, v)
            mapping[t] = v
            return t
        return f

    for kind in ("SSN", "EMAIL", "CARD", "PHONE"):  # card before phone so long numbers are not split
        text = PATTERNS[kind].sub(sub(kind), text)
    return text, mapping


def find_pii(text: str):
    """Names of PII kinds still present in text (used on model output, logs, traces)."""
    hits = []
    for kind, rx in PATTERNS.items():
        for m in rx.finditer(text):
            if kind != "CARD" or _luhn(m.group(0)):
                hits.append(kind)
                break
    return hits


EVIDENCE_RX = re.compile(r"\bE-\d+\b")


def check_output(text: str, allowed_evidence_ids=None):
    """Raise GuardrailViolation for raw PII or for citing an evidence id that was never supplied."""
    pii = find_pii(text)
    if pii:
        raise GuardrailViolation(f"raw PII in output: {sorted(set(pii))}")
    if allowed_evidence_ids is not None:
        bad = set(EVIDENCE_RX.findall(text)) - set(allowed_evidence_ids)
        if bad:
            raise GuardrailViolation(f"unknown evidence ids cited: {sorted(bad)}")
    return text


def guarded(runner, allowed_evidence_ids=None):
    """Wrap a model runner: mask the prompt, call the model, check the answer."""
    def run(prompt):
        masked, _ = mask(prompt)
        return check_output(runner(masked), allowed_evidence_ids)
    return run


def enabled() -> bool:
    return os.getenv("GUARDRAILS", "on") != "off"
