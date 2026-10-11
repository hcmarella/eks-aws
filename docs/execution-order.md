# Order of execution: start to production
One ordered list. Each step names the doc with the detail. ☐ = tick as done. Calendar assumes a one-month target; approvals are what usually slip, so start them in step 1.

## Phase 0 — Day 0–2: approvals and decisions (start in parallel, they gate everything)
- ☐ 0.1 Request AWS accounts (dev/qa/prod), region, VPC + private subnets, Bedrock model access and quota, Databricks read access → [access-requests.md](access-requests.md), Word runbook
- ☐ 0.2 Security approval for tools/data paths; confirm model risk review requirement (SR 11-7 style; confirm) and change-ticket process → [prod-readiness-checklist.md](prod-readiness-checklist.md) §6
- ☐ 0.3 Confirm stage order (census / freeze / red team / vote), personas, voting rules, anatomy-file structure → `app/config/pipeline.yaml`, `app/personas/`
- ☐ 0.4 Rule: synthetic data only outside the approved bank environment

## Phase 1 — Week 1: local (no AWS)
- ☐ 1.1 `make test`, `make run` → [environment-testing-and-migration.md](environment-testing-and-migration.md) Stage 1
- ☐ 1.2 Implement stage bodies in `app/pipeline/stages.py` with ledger-first writes, schema validation, capped loops
- ☐ 1.3 Postgres checkpointer + ledger via `docker compose up`; crash/resume test
- ☐ 1.4 Build golden synthetic cases and eval harness
- ☐ 1.5 `docker build`, then `./scripts/local-up.sh` (minikube), `helm lint`
- ☐ 1.6 Implement `app/poller.py` (Databricks Delta Change Data Feed + watermark) against a test source
- ☐ Exit: tests green, PR merged to main

## Phase 2 — Week 1–2: AWS foundations (manual prerequisites)
- ☐ 2.1 Terraform state bucket + lock table; GitHub OIDC roles for ECR push and Terraform plan; repo variables → [aws-setup.md](aws-setup.md) §2
- ☐ 2.2 VPC endpoints: bedrock-runtime, ecr.api, ecr.dkr, s3, sts, secretsmanager, logs → aws-setup.md §4
- ☐ 2.3 Bedrock: confirm enabled model IDs, raise quota, test one call → aws-setup.md §1
- ☐ 2.4 Fill `terraform/envs/dev/dev.tfvars` and `main.tf` placeholders; fill `values-dev.yaml` (account id, model id)

## Phase 3 — Week 2: dev environment
- ☐ 3.1 `terraform validate` / `plan` / `apply` envs/dev → EKS, ECR, RDS, S3, IAM roles + Pod Identity
- ☐ 3.2 CI builds image `conductor:<sha>` → ECR
- ☐ 3.3 Install Argo CD; `kubectl apply -f argocd/project.yaml argocd/app-dev.yaml` (check kubectl context first)
- ☐ 3.4 `scripts/create-db-secret.sh dev …`, `scripts/init-db.sh dev` → aws-setup.md §3
- ☐ 3.5 Promote workflow env=dev → merge PR → Argo syncs
- ☐ 3.6 Verify identity, network, Bedrock call, end-to-end synthetic case, failure drills, eval → testing doc Stage 2
- ☐ Exit: drills + eval pass

## Phase 4 — Week 3: qa
- ☐ 4.1 Apply envs/qa (Multi-AZ RDS); fill qa values; raise Bedrock quota
- ☐ 4.2 Tighten NetworkPolicy egress to endpoint CIDRs
- ☐ 4.3 Promote same sha to qa (reviewer approves PR; manual Argo sync)
- ☐ 4.4 Shadow mode vs BAU; load test; poller test; backup restore; rollback drill; security scans; alert test → testing doc Stage 3
- ☐ Exit: shadow-mode sign-off, eval gate met

## Phase 5 — Week 3–4: governance and prod readiness
- ☐ 5.1 Model risk documentation and review; security review; data owner approval
- ☐ 5.2 Retention policy, PII masking, audit trail check, DR targets, on-call + alerts, budget alarm
- ☐ 5.3 Complete remaining items in the checklist for the prod gate

## Phase 6 — Week 4: prod, limited live
- ☐ 6.1 Apply envs/prod (separate account preferred); dedicated DB user; deletion protection
- ☐ 6.2 Promote the sha proven in qa (approvers + change ticket; manual sync in an agreed window)
- ☐ 6.3 Smoke test with one low-risk real case and human review
- ☐ 6.4 Limited live release: small share of cases, human review of every HOLD / CAVEAT; watch duration, failures, tokens, queue depth, poller lag
- ☐ 6.5 Expand only when written exit criteria are met; keep revert PR ready

## Every release afterwards
PR → CI (tests, scan, build, push) → promote dev → drills/eval → promote qa → shadow check → promote prod with ticket. Rollback = `git revert` the tag bump + sync. Schema changes: additive migration, dev → qa → prod in image order.

## Standing rules
Check `kubectl config current-context` before any apply/delete. No secrets in git or images. No real case data outside the approved environment. Preserve the stalled BAU run's evidence until the new pipeline is proven.

## Document map
| Doc | Use |
|---|---|
| [aws-setup.md](aws-setup.md) | IAM, Pod Identity/IRSA, RDS, Bedrock |
| [environment-testing-and-migration.md](environment-testing-and-migration.md) | test + what to update per stage |
| [prod-readiness-checklist.md](prod-readiness-checklist.md) | gates for prod |
| [promotion-flow.md](promotion-flow.md) | release mechanics |
| [runbook.md](runbook.md) | operations |
| [master-reference.md](master-reference.md) | targets, limits, costs |
| Conductor_Infrastructure_Setup_Runbook.docx | Word version with request texts and diagrams |
