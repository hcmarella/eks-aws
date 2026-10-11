# Test and migrate at each stage: local → dev → qa → prod

Rule: the code and image never change between stages. Only the items under **What to update** change. Commands for Helm, kubectl and Terraform are unvalidated in the authoring sandbox; run them once in dev and correct as needed.

Before any kubectl/helm command: `kubectl config current-context` and confirm it is the cluster you mean.

## Stage 1: LOCAL (laptop, synthetic data, no AWS)
**Goal:** the graph is correct and bounded.
**Setup:** `python -m venv .venv && pip install -r app/requirements.txt`; optional Docker/minikube.

| Test | How | Pass when |
|---|---|---|
| Unit + graph | `make test` | all green, no network |
| Run graph on replay | `make run` | JSON output, no model call |
| Container | `docker build -t fraudagent:local .` then `docker run --rm -e MODEL_RUNNER=replay fraudagent:local` | exits 0 |
| DB + schema | `docker compose up --build` | tables from `app/schema.sql` exist; rerun a case twice and see no duplicate ledger rows |
| Chart on minikube | `./scripts/local-up.sh` | pods Running; `helm lint helm/fraudagent -f helm/fraudagent/values-local.yaml` clean |
| Crash/resume | kill the agent mid-case, rerun | resumes from last ledger step |
| Loop caps | feed a case that always yields bugs | stops at `replan_max`, outcome HOLD |
| Real model (optional) | `MODEL_RUNNER=anthropic` with synthetic data only, approval needed | outputs pass schema validation |

**Exit to dev:** tests green, PR approved, merged to `main`, CI pushed `fraudagent:<sha>` to ECR.

## Stage 2: DEV (EKS, synthetic data, Bedrock, limited quota)
**Goal:** it works on AWS plumbing: IAM, network, RDS, Bedrock, Jobs.

**One-time update (infra):**
- `terraform/envs/dev/dev.tfvars`: `vpc_id`, `private_subnet_ids`
- `terraform/envs/dev/main.tf`: `backend` bucket and lock table, S3 artifact bucket name
- GitHub repo variables: `AWS_ECR_PUSH_ROLE_ARN`, `AWS_TF_PLAN_ROLE_ARN`
- `helm/fraudagent/values-dev.yaml`: `ACCOUNT_ID` in image repository, `bedrockModelId`
- Create secret `fraudagent-db` (key `url`) in the namespace from the RDS-managed secret; never commit it
- Run `app/schema.sql` against RDS (or add a migration job)
- `kubectl apply -f argocd/` (project + `app-dev.yaml`)

**Per release:** run the **promote** workflow (env=dev, sha) → merge the tag-bump PR → Argo auto-syncs.

| Test | How | Pass when |
|---|---|---|
| Terraform | `terraform -chdir=terraform/envs/dev plan -var-file=dev.tfvars` | clean plan, reviewed |
| Rollout | `kubectl -n fraudagent-dev get pods`; Argo app Healthy | dispatcher Running |
| Identity | agent pod calls Bedrock | no AccessDenied; role is least privilege |
| Network | pod reaches RDS and Bedrock endpoint only | other egress blocked |
| End-to-end | insert a synthetic row into `case_outbox` | Job created, ledger filled, outcome + seal written |
| Failure drills | kill pod, throttle Bedrock, stop RDS briefly | resume without duplicates; retries back off |
| Eval harness | run golden synthetic set | score ≥ agreed threshold |
| Cost | token and runtime per case | within budget |

**Exit to qa:** drills and eval pass; tag recorded.

## Stage 3: QA (EKS, masked or synthetic data, prod-like)
**Goal:** prove quality against BAU and behavior at prod-like scale.

**Update:**
- `terraform/envs/qa/*` (tfvars, backend, bucket name); Multi-AZ RDS
- `values-qa.yaml`: `bedrockModelId`, quota sized for load, replicas
- Bedrock quota raised to expected concurrency
- Databricks read access (masked source) and the poller implemented (`app/poller.py` is a stub)
- Tighten NetworkPolicy egress to VPC endpoint CIDRs
- Argo `app-qa.yaml` applied; sync is manual

**Per release:** promote workflow (env=qa, same sha as dev) → reviewer approves PR → manual sync in Argo.

| Test | How | Pass when |
|---|---|---|
| Shadow mode | run pipeline on the same cases as BAU, outputs not published | disagreement list reviewed and signed off |
| Load | N concurrent cases | no quota errors beyond retry budget; durations in target |
| Poller | change a source row; watch watermark and outbox | one outbox row per (case, data version) |
| Backup/restore | restore RDS snapshot to a scratch instance | restore verified |
| Rollback | `git revert` tag bump, sync | previous version running |
| Security | image scan, secrets scan, access review | no critical findings |
| Observability | alerts fire on a forced failure | on-call receives it |

**Exit to prod:** shadow-mode sign-off, eval gate, security and model-risk approvals recorded, runbook reviewed.

## Stage 4: PROD (real data, Bedrock only)
**Goal:** limited live use, then expansion.

**Update:**
- `terraform/envs/prod/*` (preferably a separate AWS account); deletion protection on RDS
- `values-prod.yaml`: model IDs, quota, replicas
- Real data access and retention rules in force; PII masking in logs
- Change ticket number in the promotion PR; named approvers
- Argo `app-prod.yaml` applied; sync is manual
- Alerts, on-call, budget alarm, DR targets in place

**Release:** promote workflow (env=prod, the sha already proven in qa) → approvers merge → manual sync during an agreed window.

| Test | How | Pass when |
|---|---|---|
| Smoke | one low-risk real case with a human reviewer | output matches reviewer's view |
| Limited live | small share of cases, human reviews every HOLD / CAVEAT | exit criteria in writing, met |
| Watch | duration, failures, tokens, queue depth, poller lag | within thresholds for the agreed period |
| Rollback ready | revert PR prepared | can restore in minutes |

## What migrates, in one table
| Item | local | dev | qa | prod |
|---|---|---|---|---|
| Image | `fraudagent:local` | `…/fraudagent:<sha>` | same sha | same sha |
| Values file | values-local | values-dev | values-qa | values-prod |
| Terraform env | none | envs/dev | envs/qa | envs/prod |
| DB | pod | RDS small | RDS Multi-AZ | RDS Multi-AZ, protected |
| Model runner | replay | bedrock | bedrock | bedrock |
| Data | synthetic | synthetic | masked/synthetic | real |
| Deploy | local-up.sh | Argo auto | Argo manual | Argo manual + change |
| Approval | none | PR | reviewer | approvers + ticket + model risk |

## Schema and data changes
Adding a column or table: write an additive migration (new file, no destructive change), apply to dev first, then qa, then prod in the same order as the image, and keep the old image compatible with the new schema for one release so rollback works.
