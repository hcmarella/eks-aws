# Evals and PII guardrails for FraudAgent

Status: the code in `app/guardrails.py` and `app/evals/` runs and is tested locally with a fake model (15 tests pass). Nothing here has run against Bedrock, a real Lakebase, or real data. The three-layer eval idea comes from a LinkedIn post (RAG, LLM calls, agent); its resource links were not opened.

## Part 1. The three eval layers, mapped to our agent

| Layer | What the post says to measure | What it means in FraudAgent | Where in the code |
|---|---|---|---|
| **1. Retrieval (RAG)** | Precision, completeness, ranking (NDCG) | Did we load the right personas, rules and evidence, and nothing noisy? Our loader picks by key and pinned version, so this is mostly **precision/completeness of the selection**. Ranking (NDCG) matters only where we search by similarity (past cases, lessons). | `metrics.precision_at_k`, `recall`, `ndcg` |
| **2. LLM calls** | Fidelity, guardrails, instruction following, relevance | **Fidelity:** every cited evidence ID was actually supplied. **Guardrails:** no raw PII, no rule broken. **Instruction following:** output matches the schema. **Relevance:** answers the question asked (needs a judge model or a person to score). | `guardrails.check_output`, `metrics.grounded_rate`, `schema_valid_rate` |
| **3. Agent** | Completion rate, tool accuracy, cost, latency | Share of cases that finish; verdict matches the golden answer; tool error and retry rate; tokens per completed case; p50 and p95 time. | `metrics.agent_scores`, `evals/run_golden.py` |

**Extra measures specific to our design**
- Vote agreement and how often the weighted consensus differs from a simple majority.
- How often the red team finds a bug, and how often the re-plan loop hits its cap.
- Rate of HOLD, PUBLISH WITH CAVEAT and BLOCKED outcomes.
- Share of cases that needed a person.

### How to run the evals
- `python app/evals/run_golden.py` runs the golden cases in `app/evals/golden.yaml` and exits with an error if completion or accuracy falls below the thresholds. Today it uses the fake model, so it checks wiring, not model quality.
- **Next step:** run the same file with `MODEL_RUNNER=bedrock` in dev, add more synthetic golden cases, and compare the plain node against a deep-agent node.
- **Rule:** every real failure becomes a new golden case.
- Run the golden set in the pipeline on every change to code, prompts, or an approved knowledge version. Block the release if scores drop.
- Layer 2 relevance and a lot of layer 1 judgement need an LLM judge or human labels. Use a different model as judge, and spot-check the judge itself with people.

## Part 2. PII guardrails

**Where PII must not appear:** model prompts, graph state and checkpoints, logs, traces (LangSmith or Langfuse), error messages, and the model's answer.

| # | Control | Status |
|---|---|---|
| 1 | **Tokenize known fields upstream** (SSN, card, account, phone, email, name columns) in dbt before data reaches the agent. Deterministic tokens keep joins and "same card seen 3 times" analysis working. | **Not built.** Best protection; do it in the data repo. |
| 2 | **Mask free text at the runtime entry**, before graph state exists (`mask()` in `agentcore_app.invoke`). | Built, tested |
| 3 | **Mask again at the single model gateway** (`guarded()` wraps the model runner), in case something slipped through. | Built, tested |
| 4 | **Check every model answer** for raw PII and for evidence IDs that were never supplied; violation raises `GuardrailViolation`. | Built, tested |
| 5 | **Canary test:** a case containing fake SSN, card, email and phone must not appear in the answer, checkpoint storage or logs. It fails if guardrails are off (checked). | Built. Extend it to traces and the Postgres checkpoint tables. |
| 6 | **Restore real values only at delivery**, for an authorised viewer, from the source system, never from the checkpoint. | Not built |
| 7 | **Bedrock Guardrails** (AWS sensitive-information filters, applied to inputs and outputs) as a second, managed layer. | Not built. Verify it is available and approved in your account and region. |
| 8 | **Traces and logs:** send only masked text and IDs. Use a self-hosted or approved Langfuse or LangSmith. Keep Bedrock invocation logging off, or locked down, unless security agrees. | Policy; confirm per tool |
| 9 | **Least privilege and encryption:** per-environment roles and secrets, KMS-encrypted storage, no PII in S3 object names or URLs. | Part of the infra repo |

**Limits you should know**
- The built-in detection is regex based (SSN, email, phone, Luhn-checked card numbers). It will miss names, addresses, account numbers in odd formats and anything written in free text. It is a safety net, not the main control. Control 1 is the main control.
- `PII_TOKEN_KEY` must come from Secrets Manager in dev/QA/prod. The default in the code is for local use only.
- If a person needs to read the raw value during a review, that view must be a separate, audited path.

## Part 3. What to do next, in order
1. Add the PII column list to the data repo and tokenize those columns in the dbt source view.
2. Run the golden set against Bedrock in dev and record the baseline scores.
3. Extend the canary test to the Postgres checkpoint tables and to the trace tool.
4. Evaluate Bedrock Guardrails as the second layer.
5. Put the golden set and the canary test into the pipeline as release gates.
