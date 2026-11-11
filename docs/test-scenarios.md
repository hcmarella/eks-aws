# Test scenarios: fraud case pipeline on Lakebase (container Postgres first)

All data below is **synthetic**. IPs use documentation ranges (203.0.113.0/24, 198.51.100.0/24), phones use 555-01xx, domains use example.test. Never put real case data in fixtures, logs or this repo.

How to run each scenario: (1) local with container Postgres (same major version as Lakebase) and `MODEL_RUNNER=replay`; (2) dev with Lakebase and Bedrock once access exists. Same scenarios, same expected results; only `DATABASE_URL`, `SOURCE_MODE` and `MODEL_RUNNER` change.

Status of the repo today: the graph skeleton and ledger tables exist; the failure classes, state machine, validators, source readers and admin commands described here are **not built yet**. This document is the acceptance test for them.

## A. The base case (used by most scenarios)
Customer token `CUST-1001`, case `C-2026-0001`.

| Source | Time (UTC) | Fact |
|---|---|---|
| Okta | 10-20 08:02 | Login from device D-AAA, IP 198.51.100.10 (usual) |
| Okta | 10-21 02:14 | MFA factor reset requested |
| Okta | 10-21 02:16 | Login from new device D-ZZZ, IP 203.0.113.77 (new country) |
| Phone | 10-21 02:10 | Contact phone changed 555-0101 to 555-0177 |
| DNS | 10-21 02:12 | Lookups of `login-example-support.test`, registered 3 days ago |
| IP | 10-21 02:16 | 203.0.113.77 seen on 14 other customer tokens in 24h |
| Transfer | 10-21 02:31 | New payee added, outgoing transfer 24,900.00 (customer's usual max 1,200.00) |

Expected: account-takeover pattern. All voters say "fraud likely" with high confidence, red team finds no contradiction, outcome **PUBLISH**.

## B. Scenarios

| # | Scenario | Setup | Expected result |
|---|---|---|---|
| 1 | Clean positive | Base case, all sources | PUBLISH. 3 to 4 valid votes, Excel with all tabs, SHA-256 stored |
| 2 | Benign look-alike | Same, but new device is a known corporate laptop and the payee already exists | No fraud pattern. Outcome by your rules (not PUBLISH as fraud) |
| 3 | Required source down | Okta reader returns 503 for 2 hours | Retries 3 times, case BLOCKED, slot released, other cases proceed. When Okta returns, case resumes from checkpoint, no duplicate ledger rows |
| 4 | Required source down past deadline | Okta down beyond the deadline | INCOMPLETE with reason, ticket created, never PUBLISH |
| 5 | Optional source missing | DNS source empty | PUBLISH WITH CAVEAT naming DNS |
| 6 | Permission error | Okta reader returns 403 | One token refresh, then BLOCKED and platform alert. No agent workaround, no endless retry |
| 7 | Split vote | Voters split 2 to 2 | By the fixed rule: PUBLISH WITH CAVEAT or HOLD. Same result every run |
| 8 | Voter fails | One voter times out 3 times | Voter replaced. If quorum still impossible: HOLD |
| 9 | Red team contradiction | Transfer timestamp is before the login that "caused" it | One re-plan. If it persists, HOLD. Re-plan count never exceeds the cap |
| 10 | Impossible value | Transfer amount -24,900.00 or phone "555-01" | Validation gate fails closed. Source flagged, case not published |
| 11 | Empty result | IP source returns no rows for the customer | Caveat or BLOCKED per source config, never a silent continue |
| 12 | Malformed model output | Node returns invalid JSON twice | Guided retry with the error, then fallback or fail. Counted as a fixable failure |
| 13 | Hung tool | A query hangs, no error | Idle timeout fires, retry, then BLOCKED |
| 14 | Crash and resume | Kill the pod during the segment checks | Job restarts, resumes from last checkpoint, finished segments not re-run, no duplicate ledger rows |
| 15 | Many cases, one poison | 5 cases queued, case 3 always fails | Others finish on time, case 3 quarantined as NEEDS_MANUAL after N attempts |
| 16 | Backlog drain | 40 cases queued while Bedrock throttled | Concurrency cap and rate limit hold, oldest first, no stampede, no lost case |
| 17 | New data while running | New data version for C-2026-0001 arrives mid-run | Old run reaches stage end, marked SUPERSEDED, new run on latest snapshot, both audited |
| 18 | Late-arriving row | Row arrives later with an older timestamp | Caught when using the change-feed commit version. Shows that a timestamp watermark would miss it |
| 19 | Loop cap | Red team always finds a bug | Stops at the re-plan cap, outcome HOLD |
| 20 | No-progress loop | A node returns the same state repeatedly | No-progress check stops it |
| 21 | PII canary | Replace phone and IP with recognizable canary values | Raw canaries absent from logs, step events, checkpoints and stored model prompts (pseudonyms only) |
| 22 | Delivery with ServiceNow down | Ticket API returns 500 | Report still STORED and listed in the portal. Notification retried later |
| 23 | Developer fix | Break one node's code, let the case fail, fix, then use `resume` | Resumes from the last good checkpoint. Action audited with code version |

## C. Lakebase-specific checks
Run after the scenarios pass on the container:
1. **Authentication:** run a case that lasts longer than the credential lifetime. The pool must refresh credentials with no failure.
2. **Idle and scale to zero:** leave the instance idle, then submit a case. Measure the first-query delay. Turn scale to zero off for prod.
3. **Connections:** start 20 Jobs at once. No "too many connections". Pool size per Job is tuned.
4. **Failover:** force a failover mid-case. Connections recover and the case continues.
5. **Branching:** create a branch of dev for the test run, run scenarios, delete the branch. Prod data is never branched into dev.
6. **Network:** the EKS pod reaches Lakebase over the private path only.
7. **Delta sync:** results appear in the lakehouse tables within the agreed time. Preview features are marked as such.

## D. SQL checks (adapt names to the final data model)
```sql
-- no duplicate ledger rows after a crash or retry
SELECT case_id, step, count(*) FROM ledger GROUP BY 1,2 HAVING count(*) > 1;

-- one active run per case
SELECT case_id, count(*) FROM runs WHERE status IN ('RUNNING','QUEUED') GROUP BY 1 HAVING count(*) > 1;

-- every case ends in a defined state
SELECT status, count(*) FROM cases GROUP BY 1;

-- watermark never behind recorded outbox rows
SELECT * FROM cdc_watermark;
```

## E. Pass criteria
- Every scenario yields its expected state, with no manual table edits.
- No duplicate ledger rows, no lost case, no case stuck without an alert.
- One failed case never delays the others by more than the queue ordering allows.
- The canary test finds no raw PII outside the allowed place.
- Results are the same on the container and on Lakebase.

## F. Fixtures
Store the base case as small CSV or JSON files per source under `tests/fixtures/scenarios/<n>/`, one folder per scenario, so `SOURCE_MODE=fixture` can run them without Databricks.
