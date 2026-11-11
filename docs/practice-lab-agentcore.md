# Practice lab: run the LangGraph agent in AgentCore Runtime, with memory, across environments

Status: **local steps (Part A) were run and pass. AWS steps (Part B onward) were not run** by the author, because there is no AWS access from the build sandbox. Console page names can differ from what is written here, so trust the screen over this guide. Use synthetic data only.

## What "memory" means here (three different things)

| Name | What it is | Use it for |
|---|---|---|
| **Checkpointer** (`MEMORY_BACKEND=postgres`) | LangGraph saves graph state after each step so a case can resume | **The design.** Production target is Lakebase (Postgres). |
| **In-process** (`MEMORY_BACKEND=memory`) | State lives in the session only and is lost at the end | First runtime smoke test |
| **AgentCore Memory** (`MEMORY_BACKEND=agentcore`) | AWS managed memory: `AgentCoreMemorySaver` (short-term) and `AgentCoreMemoryStore` (long-term) | **Practice only.** Your platform allows the Runtime but not the rest of AgentCore, so do not design around it. |

Cross-case learning (lessons, personas) is **not** agent memory. It lives in the knowledge base (Delta, synced to Lakebase) and is approved by a person.

## Part A. Local practice (done, passes)

```bash
cd app
pip install -r requirements.txt
# 1. unit tests (8 pass; the Postgres one is skipped unless TEST_DATABASE_URL is set)
python -m pytest -q
# 2. run the runtime wrapper exactly as AgentCore will
MODEL_RUNNER=replay MEMORY_BACKEND=memory python agentcore_app.py &
curl localhost:8080/ping
curl -X POST localhost:8080/invocations -H 'Content-Type: application/json' \
     -d '{"case_id":"c1","text":"unauthorized card charge"}'
# 3. Postgres memory: start Postgres (Docker or local), then
export DATABASE_URL=postgresql://fa:fa@localhost:5432/fa MEMORY_BACKEND=postgres DB_SETUP=1
python agentcore_app.py     # DB_SETUP=1 creates the checkpoint tables; set it once per database
```

Resume test: call `/invocations` with `"thread_id":"t-1"`, stop the process, start it again, and read the state for `t-1`. The same `thread_id` continues from the saved checkpoint. The test suite proves this with a new saver object.

Build the image (needs Docker with buildx; **not yet built by the author**):
```bash
docker buildx build --platform linux/arm64 -f Dockerfile.agentcore -t fraudagent-agent:local .
```

## Part B. AWS practice account, in order

For each step, take the screenshot named in Part C.

1. **Budget alarm first.** Billing, Budgets: set a small monthly budget with email alerts. A budget only alerts; it does not stop spending.
2. **Region.** Pick one region where Bedrock and AgentCore are available. Use it everywhere.
3. **Bedrock model access.** Enable the model you will use. Note the exact model ID for the parameter sheet.
4. **ECR repository.** Create `fraudagent-agent` (private). Turn on scan on push and immutable tags.
5. **Push the image.** Tag with the git commit SHA, not `latest`.
6. **Execution role (IAM).**
   - Trust policy principal: `bedrock-agentcore.amazonaws.com` (not the Bedrock service principal).
   - Permissions: pull from your ECR repo, write CloudWatch Logs, X-Ray write, `bedrock:InvokeModel` / `InvokeModelWithResponseStream` on your model, and the workload-identity token actions (`bedrock-agentcore:GetWorkloadAccessToken*`) scoped to your agent. A wildcard that does not match your agent's name causes 403 errors.
   - Add `bedrock-agentcore:CreateEvent`, `ListEvents`, `RetrieveMemories` **only** if you practise with AgentCore Memory.
   - Start from the AWS tutorial's template and cut it down; do not write it from memory.
7. **Create the runtime.** Point it at the ECR image URI and the execution role. Network mode: public to start. Set environment variables from `app/config/env-parameters.yaml` (`APP_ENV`, `MODEL_RUNNER=bedrock`, `BEDROCK_MODEL_ID`, `MEMORY_BACKEND`, `AWS_REGION`).
8. **Invoke.** Console test or the data-plane call `InvokeAgentRuntime` with payload `{"case_id": "...", "text": "..."}`.
9. **Check logs.** CloudWatch Logs group for the runtime: find your JSON line (`case_id`, `status`, `latency_ms`).
10. **Add Postgres.** Small RDS or Aurora Postgres in a VPC, load mock data, put the connection string in Secrets Manager, give the execution role read on that secret, and switch the runtime to VPC mode with private subnets and a security group that allows port 5432 from the runtime. Set `DB_SETUP=1` for the first start only. (Not yet confirmed: that VPC mode and the extra egress you need are allowed in your account.)
11. **Optional: AgentCore Memory.** Create a memory in the console, copy its ID into `AGENTCORE_MEMORY_ID`, set `MEMORY_BACKEND=agentcore`, add the three IAM actions. Compare behaviour with Postgres, then switch back.
12. **Tear down** every item you created when the session ends (runtime, ECR images, RDS, secrets, memory). Check Billing the next day.

## Part C. Screenshot checklist

I cannot take screenshots of your AWS account. Capture these yourself into `docs/screenshots/` with these names, **after blanking account IDs, ARNs and keys**.

| # | File name | What to capture |
|---|---|---|
| 1 | `01-budget.png` | Budget with alert email |
| 2 | `02-bedrock-model-access.png` | Model enabled in your region |
| 3 | `03-ecr-repo.png` | Repo settings (scan on push, tag immutability) |
| 4 | `04-ecr-image-tag.png` | Pushed image with the SHA tag, arm64 |
| 5 | `05-exec-role-trust.png` | Trust policy |
| 6 | `06-exec-role-permissions.png` | Attached policies |
| 7 | `07-runtime-config.png` | Runtime: image, role, network mode, env vars (no secrets) |
| 8 | `08-invoke-result.png` | Successful invocation response |
| 9 | `09-cloudwatch-log-line.png` | Your JSON log line |
| 10 | `10-logs-insights-latency.png` | Logs Insights query: latency by `case_id` |
| 11 | `11-postgres-checkpoints.png` | Rows in the checkpoint table for one `thread_id` |
| 12 | `12-resume-after-kill.png` | Same `thread_id` continuing after the session was stopped |
| 13 | `13-trace.png` | LangSmith or Langfuse trace with tokens and cost |
| 14 | `14-teardown-clean.png` | Resources removed / empty resource list |

Logs Insights example:
```
fields @timestamp, case_id, status, latency_ms
| filter ispresent(case_id)
| sort @timestamp desc
```

## Part D. Environments: dev, test, QA, prod

- **Best practice: one AWS account per environment.** If you only have one practice account, separate them by name (`fraudagent_dev`, `_test`, `_qa`, `_prod`), by ECR tag permissions, and by database. A runtime also supports named endpoints (like aliases) pointing at a version; that article was from the preview period, so confirm current behaviour before relying on it.
- **Build once.** The image tag is the git SHA. Promote the same digest from dev to prod. Only `app/config/env-parameters.yaml` values change.
- **Ladder:**

| Env | Memory | Model | Network | Gate to move on |
|---|---|---|---|---|
| local | postgres (Docker) or memory | replay | none | tests pass |
| dev | memory, then postgres | bedrock (small) | public, then VPC | one case runs end to end; logs and trace visible |
| test | postgres | bedrock | VPC | all golden cases; resume-after-kill passes |
| qa | postgres / Lakebase | bedrock (prod model) | VPC | load test; failure drills; security review |
| prod | Lakebase, scale-to-zero off | Bedrock only | VPC | manual approval; same digest as QA |

## Part E. What to show in a demo
Push to GitHub, image appears in ECR, invoke the runtime, show the CloudWatch log line, show the trace, show checkpoint rows, kill the session and resume.

## Sources
- [Integrate AgentCore Memory with LangChain or LangGraph (AWS docs)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-integrate-lang.html)
- [Getting started with Bedrock AgentCore Runtime (preview-era article: arm64, port 8080, role trust, endpoints)](https://heeki.substack.com/p/getting-started-with-bedrock-agentcore)
