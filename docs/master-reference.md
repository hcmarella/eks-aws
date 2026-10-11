# Agent Deployment Master Reference

Local (minikube) -> Pure AgentCore -> ECR + EKS. One agent codebase, deployed either way.

**Status legend:** [V] = well-known, standard. [U] = NOT tested by the author against a real account; verify against the current AWS/AgentCore docs before relying on it. Commands use placeholders such as `<acct>`, `<region>`, `<agent>`.

**Rules that apply everywhere**
1. Synthetic data only outside the approved bank environment. Never put real case data in a personal account, a public tool or an unapproved sandbox.
2. Run `kubectl config current-context` before any `apply` or `delete`.
3. Tag every image with the git SHA, never `latest`.
4. Every step has a pass check. Do not move on until it passes.
5. Anything "projected" or "replayed" is labelled as such. Only real Bedrock runs are quoted as performance.

---

## 1. The three targets at a glance

| | Local (minikube) | Case B: pure AgentCore | Case A: ECR + EKS |
|---|---|---|---|
| Purpose | Prove logic, trigger, resume, metrics; demo | Fast managed hosting test | Production-like, full control |
| Needs AWS account | No | Yes | Yes |
| Hosting | Your Mac / Coder EC2 | AgentCore Runtime | Your pods on EKS |
| State | Postgres pod | AgentCore Memory + DynamoDB ledger (Postgres needs VPC) | Postgres (RDS) + optional AgentCore Memory |
| Idle cost | $0 | ~$0 | EKS control plane ~$73/month + nodes + NAT [U verify] |
| Long case (hours) | You control it | Must test session limits [U] | You control it |
| Setup effort | 1-2 days | Hours | ~1 day (more with bank approvals) |

AgentCore Runtime and EKS are alternative hosts. AgentCore Memory is a separate API and can be used from either.

## 2. One codebase, three entry points

```
repo/
  conductor/            # the LangGraph: nodes, ledger, contracts, registry
  entrypoints/
    cli.py              # python -m entrypoints.cli --case <id>      (K8s Job / local)
    worker.py           # queue worker loop                          (EKS worker pool)
    agentcore_app.py    # BedrockAgentCoreApp wrapper                (AgentCore)
  deploy/
    k8s/                # base + overlays/local + overlays/dev-aws
    terraform/          # modules/app, envs/local, envs/dev-aws
    agentcore/          # config notes, IAM policy
  Dockerfile
  tests/
```

Rules for the shared core:
- The graph never knows where it runs. Storage (ledger, checkpointer) and model runner are injected.
- Settings come from environment variables only: `LEDGER_URL`, `CHECKPOINTER`, `MODEL_RUNNER` (`replay|bedrock`), `MODEL_ID`, `AWS_REGION`, `MAX_CV_ROUNDS`, `MAX_LOOPBACKS`, `TOKEN_BUDGET`.
- State holds small pointers only. Evidence and large outputs go to the ledger/S3.

### The BAU flow as graph nodes (order to be confirmed with your team)

```
intake -> router(PFS | tied | Mandarin | 4th) -> commander_plan
-> workers (parallel: forensic, OSI, OTP, Okta, device login, throttling, phones, PII)
-> data_quality -> log -> freeze (hash evidence snapshot)
-> census/voting (up to 23 personas, snapshot only)
-> red_team (min 3-4 routings from different personas)
-> confidence_gate
     high -> seal (SHA-256) -> publish to custodian
     low  -> derived_data -> commander_addendum -> workers (delta only) -> freeze -> census -> red_team -> gate
             (capped loops; no-new-evidence stop; then human review)
```
Make the node order a config list so a reorder is a one-line change.

---

## 3. Prerequisites checklist

### 3.1 Tools (Mac or Coder workspace)
```
brew install awscli kubectl helm minikube terraform
# Docker Desktop (or Docker Engine on EC2). Give Docker >= 10 GB memory.
python3.12 -m venv .venv && source .venv/bin/activate
pip install langgraph langchain-aws bedrock-agentcore bedrock-agentcore-starter-toolkit psycopg[binary] pydantic pytest
```
Check: `docker version`, `kubectl version --client`, `minikube version`, `helm version`, `terraform version`, `aws --version`.

### 3.2 Accounts and approvals (start now; these set your timeline)
- [ ] AWS dev account (bank-sanctioned) and region
- [ ] SSO role with ECR, EKS, Bedrock, AgentCore, CloudWatch permissions
- [ ] Bedrock: the exact Claude models enabled; quota values noted; quota-increase request filed
- [ ] ECR repository and policy (CI-only or developer push?)
- [ ] EKS namespace/cluster and node type (Graviton arm64 or x86)
- [ ] VPC endpoints: Bedrock runtime, ECR (api+dkr), S3, CloudWatch Logs, STS
- [ ] RDS Postgres (or approval to run Postgres in-cluster for dev)
- [ ] Security review for AgentCore (new service)
- [ ] Data classification ruling for logs/traces (Langfuse retention)

### 3.3 Personal-account rehearsal (optional)
Only if bank policy allows. Synthetic data only. Set an AWS Budgets alert at $20 before creating anything.

---

## 4. Phase 1 - Local environment (minikube)

### 4.1 Cluster
```
minikube start --driver=docker --cpus=4 --memory=8192 --profile conductor
minikube addons enable metrics-server -p conductor
kubectl config use-context conductor
kubectl create namespace conductor
```
Pass: `kubectl get nodes` shows Ready; `kubectl top nodes` works after ~1 minute.

Note on Docker Desktop Kubernetes: `kubectl scale` works if Kubernetes is enabled and the context is `docker-desktop`. It is single node. Use minikube/kind/k3d for multi-node demos.

### 4.2 Postgres and Langfuse
```
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install pg bitnami/postgresql -n conductor \
  --set auth.database=conductor --set auth.username=app --set auth.password=<local-only>
```
Langfuse: install per the current Langfuse self-host docs (Helm or compose). [U: chart values change; follow their docs.]
Pass: `kubectl exec -n conductor pg-postgresql-0 -- psql -U app -d conductor -c 'select 1'`.

### 4.3 Schema (ledger, events, source, outbox)
```sql
CREATE TABLE ledger (
  case_id text NOT NULL, step text NOT NULL, payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (case_id, step));            -- INSERT ... ON CONFLICT DO NOTHING = idempotent

CREATE TABLE step_events (
  id bigserial PRIMARY KEY, run_id text NOT NULL, run_type text NOT NULL,  -- 'bau' | 'langgraph' | 'replay'
  case_id text NOT NULL, node text NOT NULL, status text NOT NULL,
  started_at timestamptz, ended_at timestamptz, duration_ms bigint,
  attempts int DEFAULT 1, model_id text, tokens_in int, tokens_out int);

CREATE TABLE source_cases (case_id text PRIMARY KEY, category text NOT NULL,
  payload jsonb NOT NULL, version int NOT NULL DEFAULT 1);
CREATE TABLE case_outbox (id bigserial PRIMARY KEY, case_id text NOT NULL,
  category text NOT NULL, data_version int NOT NULL,
  status text NOT NULL DEFAULT 'new', UNIQUE (case_id, data_version));
-- triggers: bump version on UPDATE; insert into case_outbox + pg_notify on INSERT/UPDATE
```
(Trigger bodies: bump_version() sets NEW.version := OLD.version + 1; emit_case() inserts into case_outbox ON CONFLICT DO NOTHING and calls pg_notify('new_case', case_id).)
Pass: update a row in `source_cases` and see one new `case_outbox` row; a second identical update adds none.

### 4.4 Image
```
eval $(minikube -p conductor docker-env)
docker build -t conductor:dev .
```
Dockerfile essentials: python:3.12-slim, non-root user, `pip install -r requirements.txt`, `CMD ["python","-m","entrypoints.cli"]`. For AgentCore, a second target runs `entrypoints.agentcore_app` on port 8080 (arm64).

### 4.5 Dispatcher and Job-per-case
Dispatcher (a small deployment): loops on `SELECT ... FROM case_outbox WHERE status='new' FOR UPDATE SKIP LOCKED`, creates a Kubernetes Job `case-<id>-v<version>`, sets status `running`, later `done|failed`. Needs a ServiceAccount with Role to create/get/list Jobs in `conductor`.

Job spec essentials:
```yaml
apiVersion: batch/v1
kind: Job
metadata: {name: case-<id>-v<ver>, namespace: conductor}
spec:
  backoffLimit: 1
  activeDeadlineSeconds: 86400
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: graph
        image: conductor:dev
        imagePullPolicy: Never          # local image; use ECR URL later
        args: ["--case","<id>"]
        envFrom: [{secretRef: {name: conductor-env}}]
        resources: {requests: {cpu: 250m, memory: 512Mi}, limits: {memory: 1Gi}}
```
Pass: insert a case -> a pod appears (`kubectl get pods -n conductor -w`) -> Job completes -> outbox row `done` -> report file written.

### 4.6 Model runner for local
`MODEL_RUNNER=replay`: returns recorded BAU outputs and sleeps for scaled recorded durations. Label results "projected from recorded BAU timings". Switch to `bedrock` only where credentials and approvals exist.

### 4.7 Argo CD (platform deploys, not data triggers)
```
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```
Create one Application pointing at `deploy/k8s/overlays/local`. Argo CD keeps the dispatcher, portal and config in sync with git. Data changes trigger runs through the outbox/dispatcher, not Argo CD.

### 4.8 Portal and metrics
Portal reads `step_events` (per node), Job status and the report folder. Langfuse stays for trace drill-down. Metrics per case: wall-clock (total and per stage), model calls, tokens, retries, timeouts, loop-backs, human escalations, resume-after-kill result.

### 4.9 Local acceptance tests
- [ ] New case triggers exactly one Job
- [ ] Same data version does not trigger again; a new version does
- [ ] Kill the pod mid-run; Job restarts; finished steps are skipped (ledger)
- [ ] Forced bad persona output is isolated with one retry
- [ ] Loop-back stops at the cap
- [ ] Portal shows the run live

---

## 5. Phase 2 - Case B: pure AgentCore

Goal: learn quickly whether AgentCore can host the long case.

### 5.1 Wrapper
`entrypoints/agentcore_app.py`:
- `app = BedrockAgentCoreApp()`; `@app.entrypoint` handles `{"action": "start|status|resume|result", ...}`.
- `start` launches the graph in a background thread, registers an async task (so the runtime reports busy), and returns immediately with the case id.
- `status/result` read the ledger. Never block an invocation for hours.
- Listens on 8080 (`/invocations`, `/ping`). arm64 image. [U verify against current SDK]
- Local test: `python entrypoints/agentcore_app.py` then
  `curl -X POST localhost:8080/invocations -H 'Content-Type: application/json' -d '{"action":"start","case_id":"t1"}'`

### 5.2 Deploy
```
agentcore configure -e entrypoints/agentcore_app.py     # role, ECR repo, region
agentcore launch
agentcore invoke '{"action":"start","case_id":"t1"}'
```
[U] Exact flags and prompts vary by toolkit version; run `agentcore --help`.

### 5.3 State for this case
- Ledger: DynamoDB (`attribute_not_exists` conditional put) - no VPC needed.
- Checkpointer: `AgentCoreMemorySaver` (`langgraph-checkpoint-aws`) [U verify version/API].
- Postgres requires configuring the runtime in a VPC. Skip for the first test.

### 5.4 Tests (same 10 synthetic cases as Case A)
- [ ] Normal case completes; model answer returned
- [ ] Long-run: a node that waits 30 then 120 minutes. Does the session survive? Record the limit you observe.
- [ ] Resume: stop mid-run, call `resume`, finished steps are not repeated
- [ ] 10 concurrent cases with different session ids (session id >= 33 chars) [U]
- [ ] Throttling: observe Bedrock quota errors; confirm limiter + backoff works
- [ ] CloudWatch shows logs; cost visible next day

### 5.5 Cleanup
`agentcore destroy` (or delete runtime, ECR repo, roles, log groups). Verify the bill next day.

---

## 6. Phase 3 - Case A: ECR + EKS (+ optional AgentCore Memory)

### 6.1 ECR
```
aws ecr create-repository --repository-name <agent> --region <region> \
  --image-scanning-configuration scanOnPush=true --image-tag-mutability IMMUTABLE
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com
docker buildx build --platform linux/arm64 -t <acct>.dkr.ecr.<region>.amazonaws.com/<agent>:<git-sha> --push .
```
Match `--platform` to node CPU (arm64 Graviton or amd64). If unsure: `linux/amd64,linux/arm64`. In a bank this may be CI-only.

### 6.2 EKS
Use the bank's provisioned cluster/namespace if one exists. Otherwise for a rehearsal:
```
eksctl create cluster --name conductor-dev --region <region> --nodes 2 --node-type t4g.large
```
(creates a control plane that bills ~$0.10/hour; delete when done) [U].
Then: namespace, ServiceAccount with IRSA or Pod Identity granting `bedrock:InvokeModel` (+ AgentCore Memory if used), metrics-server, and optional KEDA.

### 6.3 Deploy
- Point manifests at the ECR image (`imagePullPolicy: IfNotPresent`).
- Postgres: RDS in the VPC (security group allows the nodes), or in-cluster for rehearsal.
- Pattern 1: dispatcher + Job-per-case (same as local).
- Pattern 2 (throughput): worker Deployment polling a queue (SQS, or Postgres `FOR UPDATE SKIP LOCKED`), KEDA scaling on queue depth, Karpenter for nodes. Handle SIGTERM (finish or checkpoint step), visibility timeout + heartbeat.
- Argo CD tracks `deploy/k8s/overlays/dev-aws`.

### 6.4 Tests (identical to Case B)
Same 10 cases, same long-run, resume (delete pod), concurrency (10 at once), throttling. Add: node scale-up time, pod eviction handling.

### 6.5 Cleanup
`eksctl delete cluster ...`, delete RDS, NAT gateways, load balancers, ECR images, log groups. Check Cost Explorer next day.

---

## 7. Comparison scorecard (fill in from real runs)

| Metric | Local replay | Case B AgentCore | Case A EKS |
|---|---|---|---|
| 30-min step survives | | | |
| 2-hour step survives | | | |
| Resume skips finished steps | | | |
| 10 concurrent cases: wall-clock | | | |
| Bedrock throttling events | | | |
| Cold start to first node (s) | | | |
| Postgres reachable | | | |
| Setup effort (hours) | | | |
| Cost for the test ($) | 0 | | |
| Security review path | n/a | | |
| Ops burden | low | | |

Decision rule: choose AgentCore only if it survives the long step, handles concurrency, reaches Postgres in a VPC, and clears security review in time. Otherwise EKS (primary for the one-month target).

BAU-vs-new report: per case wall-clock, calls, tokens, retries, loop-backs, escalations. BAU rows come from the anatomy file (run_type='bau').

---

## 8. Requests to send the platform / security team (copy-paste)

1. Dev AWS account and region for the Conductor agent platform.
2. Bedrock model access: <model list>; current quotas; increase request for requests/min and tokens/min.
3. ECR repo `<agent>`; push policy (CI-only?); scan requirements.
4. EKS namespace (or cluster) with IRSA/Pod Identity; node architecture; ability to run Jobs.
5. RDS PostgreSQL (dev), private subnets, encryption at rest, backups.
6. VPC endpoints: bedrock-runtime, ecr.api, ecr.dkr, s3, logs, sts.
7. AgentCore: approval to use Runtime and Memory; VPC mode; data-retention terms.
8. Logging/trace retention rules for case-derived data (Langfuse, CloudWatch).
9. Change-control path for the new platform; who approves production.

---

## 9. Security and data rules

- Real case data stays inside the approved bank environment. Not in personal AWS, not in this chat sandbox, not in third-party tools.
- No secrets in git or images. Use Secrets Manager / K8s secrets.
- Pods run non-root with least-privilege roles (only the Bedrock model ARNs needed).
- Log scrubbing: prompts and evidence may contain PII. Decide what Langfuse/CloudWatch may store.
- The sealed bundle (SHA-256 over canonical JSON) and the ledger are the audit trail; keep them immutable.

## 10. Cost guide (rough, verify before quoting)

- AgentCore Runtime (published rates at time of writing): ~$0.0895/vCPU-hour + ~$0.00945/GB-hour (v1), per-second billing while running. Example: 1 vCPU/2 GB for 2 h ~ $0.22. Confirm whether model-wait time is billed.
- EKS control plane ~$0.10/hour; nodes, NAT gateway (~$32/month + data), RDS small instance (~$15-30/month) on top [U].
- Bedrock tokens are the main bill: calls/case x tokens/call x price. Measure from Langfuse, then extrapolate. Controls: cheapest-first tiering, per-case token budget with hard cap -> human review, prompt caching, smaller models for simple rows.

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `exec format error` in pod | arm64 image on x86 node (or reverse) | Rebuild with the right `--platform` |
| `ErrImagePull` locally | Not using minikube's Docker daemon | `eval $(minikube -p conductor docker-env)`; `imagePullPolicy: Never` |
| `ErrImagePull` on EKS | Node role lacks ECR read; wrong region/tag | Attach ECR read policy; check URL |
| Pod OOMKilled | Memory limit too low | Raise limit; check evidence size in state |
| Bedrock `ThrottlingException` | Quota / concurrency | Shared limiter + exponential backoff; request quota increase |
| `AccessDenied` on InvokeModel | Model not enabled or role lacks ARN | Enable model; fix IAM |
| Job restarts repeat work | Ledger not idempotent / wrong step keys | Check `ON CONFLICT DO NOTHING` and step ids |
| Trigger fires twice | No UNIQUE (case_id, data_version) | Add constraint |
| AgentCore call times out | Blocking invocation | Use start/status/result with async task |
| Cannot reach Postgres from AgentCore | Runtime not in VPC | Configure VPC mode or use DynamoDB for the test |
| `kubectl` acts on wrong cluster | Wrong context | `kubectl config use-context` before every apply |

## 12. Checklist to deploy ANY new agent with this reference

1. Define the contract: input schema, output schema (Pydantic, `extra="forbid"`), step ids.
2. Put capabilities in the registry table (rule / model / skill / persona rows) with weight, model_id, enabled, version, data_types.
3. Write the graph with injected ledger + runner. Unit tests with the stub runner: converge, cap, resume, bad output isolation.
4. Add timeouts, one retry on schema violation, token budget, loop caps.
5. Run local replay on synthetic data; record step_events.
6. Build the image; tag with git SHA; scan.
7. Deploy locally (Job-per-case); pass the acceptance tests in 4.9.
8. Deploy to the target (Case B or Case A); run the 10-case suite.
9. Fill the scorecard; get approvals; document rollback.
10. Production: alerts on stuck cases, spend caps, runbook, on-call owner.

## 13. Long-running cases (20+ hours)

Principle: no single pod, session or connection may need to live for the whole case. First shrink the run (parallel workers/voters, per-call timeouts, loop caps, early stops); then make what remains durable.

### 13.1 Durability design (all hosts)
- Every node writes its result to the ledger before the next starts. A step is either recorded or not done.
- Any worker can resume any case: load checkpoint, skip finished steps, continue.
- State holds pointers only; evidence and large outputs live in the ledger/S3.
- Per-step timeouts in minutes. A step running for hours is a bug to find, not something to host.
- Heartbeat: write `last_progress_at` on every step start/end. A watchdog flags cases with no progress for N minutes, retries the step once, then sends the case to human review with the reason. The portal shows "stalled".
- Human waits: save state, end the run, mark "awaiting review", start a new run on approval (LangGraph `interrupt`/resume or explicit Postgres state). Do not hold compute while waiting.

### 13.2 Host handling
| Host | Approach |
|---|---|
| EKS Job-per-case | `activeDeadlineSeconds` above max expected (24-30 h) as a safety net; `backoffLimit` 1-2; SIGTERM handler + `terminationGracePeriodSeconds`; on-demand nodes for long work (or accept spot interruptions because the ledger makes them cheap). |
| EKS worker pool | Lease a case with a visibility timeout and heartbeat extension; if a worker dies the lease expires and another resumes; KEDA on queue depth. |
| AgentCore | Never hold an invocation open. start/status/result + background thread + async task. Chain sessions: each session runs a bounded batch (e.g. up to ~6 h), saves to the ledger, ends; the orchestrator starts the next session which resumes from the ledger. |
| Local | Same as EKS Jobs; prove restart/resume here first. |

### 13.3 AgentCore Runtime limits (from AWS quotas page; read 2026-10-10; re-verify)
| Limit | Value | Adjustable |
|---|---|---|
| Max session duration (`maxLifetime`) | 8 hours | Yes (LifecycleConfiguration) |
| Async (long-running) job max | 8 hours | No |
| Idle session timeout | 15 min, then environment terminated and replaced | Yes (`idleRuntimeSessionTimeout`) |
| Synchronous request timeout | 15 min | No |
| Streaming / WebSocket max | 60 min | No |
| Hardware per session | 2 vCPU / 8 GB | No |
| Docker image | 2 GB | No |
| Payload | 100 MB | No |
| Concurrent sessions | 5,000 (us-east-1, us-west-2); 2,500 elsewhere | Yes |
| New session creation rate | 25 TPS | Yes |
| Data plane API rate | 1,000 TPS | Yes |

Consequences:
- A 20-hour case cannot run as one AgentCore session (8 h hard ceiling on async jobs). Use chained sessions or EKS.
- Anything only in memory or local disk is lost after 15 idle minutes; state must be in Postgres/DynamoDB.
- 2 vCPU / 8 GB per session: fine for orchestration, check heavy evidence parsing.
- Sources: AWS AgentCore quotas page and runtime lifecycle settings page (docs.aws.amazon.com/bedrock-agentcore/latest/devguide/).
- Researched 2026-10-10 (lifecycle settings + long-run pages): `idleRuntimeSessionTimeout` and `maxLifetime` accept 60 s to 28,800 s (8 h) on **microVM** runtimes (defaults 900 s / 28,800 s). On **Instances (capacity provider)** runtimes the maximum is 1,209,600 s (**14 days**), also capped by the provider's own `InstanceLifecycleConfiguration.maxLifetime`. Values above the max fail with ValidationException. `maxLifetime` starts at microVM creation and cannot be reset; the idle timer resets on each invocation of the same `runtimeSessionId`.
- Session resume: invoking the same `runtimeSessionId` after termination provisions a NEW microVM. The docs do not say in-memory or filesystem state survives, so assume it does not; keep all durable state in Postgres/DynamoDB.
- Keeping a session alive past 15 idle minutes requires `/ping` to return HealthyBusy (use `add_async_task`/`complete_async_task`). Blocking the entrypoint can block `/ping` and cause termination at 15 minutes. Do not set `time_of_last_update` to "now" on every ping (idle timeout never fires; sessions then run to maxLifetime and can exhaust the session quota).
- An updated runtime does not affect existing sessions; they keep the old code until they terminate.
- Pattern from Temporal's AgentCore guide: durable progress lives outside the session (a workflow engine); the runtime only hosts replaceable workers; activities use timeouts and heartbeats. Same principle as our ledger design. Treat as an architectural reference, not a requirement.
- Still untested: handoff time between chained sessions; Instances compute type pricing, VPC behavior and availability in your region/account.

### 13.4 Long-run tests (add to the 10-case suite)
- [ ] Step that waits 30 min; step that waits 2 h; (AgentCore) a session run to the 8 h boundary plus one chained handoff
- [ ] Kill pod/worker at a random step; case completes with no repeated steps
- [ ] Block a step forever; watchdog flags it within N minutes
- [ ] Rolling node drain during a run
- [ ] Wall-clock of the new parallel topology vs replayed BAU timings

### 13.5 Decision impact
AgentCore is viable if redesigned cases finish well under ~6-8 h or chained sessions are acceptable. If a meaningful share will exceed 8 h even after the redesign, EKS is simpler (no fixed session ceiling). Same ledger and resume code either way.

## 14. Open items / unverified

- AgentCore concurrency behavior at scale, and VPC/Postgres behavior [U].
- AgentCore starter-toolkit flags for the installed version [U].
- Langfuse SDK version (v2 vs v3 callback import path) and Helm chart values [U].
- BAU stage order (workers -> DQ -> red team -> freeze -> vote -> seal vs. freeze -> census -> red team -> confidence) - confirm with the team and set as config.
- Which of the ~460 control defects are platform-fixable: an outcome of triage, not an assumption.
- Databricks source: production trigger will poll a Delta view / Change Data Feed on a schedule; it is not instantaneous.
