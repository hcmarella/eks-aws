# PII encryption lifecycle: protect at intake, reveal at delivery, destroy the key

Status: **local prototype built and tested with a fake model and a mocked Secrets Manager (24 tests pass).** Not run against real AWS, Databricks, Bedrock or real data. Run `python scripts/vault_demo.py` to see it end to end.

## Requirement (from the latest discussion)
No sensitive data may reach AgentCore, in production or elsewhere. That includes the orchestrator, checkpoints, logs and traces (LangSmith or Langfuse). Plan: encrypt before the agent starts, keep the key in Secrets Manager, and when the report has passed the golden-template and quality checks, decrypt for delivery and delete the key so keys do not pile up per case.

## Flow

```
 source (Databricks)
   │  1. PROTECT (trusted side: invoker / data job)  — new per-case key → key store; real values → encrypted vault; tokens replace PII
   ▼
 AgentCore runtime + LangGraph + checkpoints + Langfuse/LangSmith + CloudWatch   ← tokens only, no key, no vault access
   │  2. tokenized report (Excel / text) saved to S3
   ▼
 3. FINALIZE (trusted side: delivery worker)
      validate report (golden template, data quality)  → reveal tokens using the case key → deliver → ONLY THEN destroy key + vault
```

Code: `app/vault.py` (`protect`, `reveal`, `destroy`, `finalize`), swappable `LocalKeyStore` / `SecretsManagerKeyStore`, and `LocalVaultStore`.

## Design rules that matter

1. **Decrypt must run outside the runtime.** If the runtime can read the key or the vault, sensitive data reaches AgentCore at the end and the requirement is not met. Use separate IAM roles: the runtime role has no access to `fraudagent/*/case/*` secrets or to the vault; only the protect and delivery roles do. Raise this with the ARB/InfoSec reviewers.
2. **Encrypt the PII fields, not the whole case.** A model cannot investigate ciphertext. Fields like IP, amounts, timestamps and merchant stay readable. Names, account numbers, card numbers, SSN, email and phone become tokens. Free text is scanned for those patterns, which is a safety net and not complete.
3. **Tokens are deterministic**, using an HMAC with a long-lived `PII_TOKEN_KEY`, so the same account gets the same token in every case and the agent can still see "same account in three cases". If policy says tokens must not link across cases, use a per-case HMAC key instead (a one-line change). Decide this with InfoSec.
4. **Real values are encrypted with AES-256-GCM** under a fresh per-case key. The case ID and token are bound into each ciphertext, and any tampering fails an integrity check.
5. **Delete the key only after delivery succeeded.** `finalize()` keeps the key if validation or delivery fails, so a retry still works. Delete is safe to call twice. Resume after a crash and a HOLD re-run need the key until delivery, so do not delete earlier.
6. **After the key is deleted, the data is unrecoverable.** That also means you cannot re-deliver the same report later. If users may need a second copy, keep the delivered file in the secure delivery store, not the key.
7. **Validate the tokenized report**, then reveal. Check template structure and data quality on the tokenized version. Column widths and cell formats can change once real values are put back, so test the revealed Excel as well.

## Where the key lives: three options to decide

| Option | How "destroy" works | Notes |
|---|---|---|
| **A. Secrets Manager, one secret per case** (what the team discussed; built) | `delete_secret` with immediate deletion, or a 7 to 30 day recovery window | Simple. During a recovery window the key is not truly gone; ask security which they accept. Check cost and API limits for one secret per case at your volume (not verified). Your colleague's existing secret-injection script can plug into `KeyStore.put/delete`; I have not seen that script. |
| **B. KMS envelope encryption** (not built) | Per-case data key from KMS (`GenerateDataKey`); store only the encrypted data key next to the vault; "destroy" = delete that encrypted key and the vault | No per-case secrets to pile up and no Secrets Manager quotas. A usual way to do this on AWS; worth proposing. |
| **C. Databricks does the encryption** (not checked) | Depends on where Databricks stores the key | Databricks SQL has `aes_encrypt` / `aes_decrypt` functions and secret scopes, as far as I know; verify in your workspace. If encryption happens upstream in the dbt source view, the key lives in Databricks and the final decrypt must also run there. That removes the separate secret store and fits "tokenize upstream", but it moves the decrypt into the data platform. Needs Databricks access to confirm. |

Questions for the platform and security teams:
- Does Databricks support the encryption function you need, and where would it keep the key?
- Can Secrets Manager delete immediately, or must there be a recovery window?
- Where may the vault live (KMS-encrypted S3 or a Lakebase table), and who may read it?
- Must tokens be unlinkable across cases?
- Which role runs the protect and delivery steps (invoker Lambda, an EKS or ECS worker, or a Databricks job)?

## What is built vs not

| Item | Status |
|---|---|
| Protect, reveal, destroy, finalize, key and vault stores (local) | Built, tested |
| Secrets Manager key store | Built, tested only with a mock (`moto`), not real AWS |
| No raw PII in graph state, checkpoints or logs with the in-runtime guardrails off | Tested |
| Same card gets the same token whatever follows it | Tested (bug found and fixed by the demo) |
| Vault in S3 or Lakebase with a locked-down role | Not built |
| Reveal inside an Excel file (cell by cell with openpyxl) | Not built |
| IAM role split (runtime cannot read keys or vault) | Not built; put in the infra repo |
| Protect/finalize wired into the invoker and delivery worker | Not built |
| Langfuse/LangSmith token-only check | Not built; add to the canary test |
| Key rotation for `PII_TOKEN_KEY` | Not designed |

## ARB wording (suggested)
"Sensitive fields are tokenized before the case reaches AgentCore. Real values are held encrypted outside the runtime under a per-case key that the runtime cannot read. The key is destroyed after verified delivery."
