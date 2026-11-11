# Production-grade checklist for LangGraph agents on EKS
Use per agent. Status column: ☐ open, ◐ partial, ✔ done. "Gate" = must be done before the stated environment.
Items marked (bank) assume a regulated bank; confirm exact requirements with your risk, security and compliance teams.

## 1. Orchestration correctness
| # | Item | Gate | Status |
|---|---|---|---|
| 1.1 | Control flow in code (graph), not in model context | dev | ◐ skeleton |
| 1.2 | Every loop capped (re-plan, hold re-run, votes) | dev | ◐ in config |
| 1.3 | Per-step and per-case timeouts; Job `activeDeadlineSeconds` | dev | ✔ in job spec |
| 1.4 | Ledger-first idempotent writes; resume after crash | dev | ◐ schema only |
| 1.5 | Checkpointer in Postgres (LangGraph) | dev | ☐ |
| 1.6 | Frozen evidence set before voting; hashes recorded | dev | ☐ |
| 1.7 | Output schema validation on every model result; retry then fail closed | dev | ☐ |
| 1.8 | Parallel workers for independent segments | qa | ☐ |
| 1.9 | Watchdog: stuck step detection and alert | qa | ☐ |

## 2. Quality and evaluation
| 2.1 | Golden set of past cases with known outcomes | dev | ☐ |
| 2.2 | Eval harness run in CI (agreement with BAU, defect rate) | qa | ☐ |
| 2.3 | Prompt, persona and model versions recorded per run | dev | ☐ |
| 2.4 | Shadow mode vs BAU for an agreed period; sign-off on disagreements | prod | ☐ |
| 2.5 | Human review step for HOLD and PUBLISH WITH CAVEAT | prod | ☐ |
| 2.6 | Regression gate: no release if eval score drops | qa | ☐ |

## 3. Data and security
| 3.1 | Synthetic data only outside the approved environment | all | ✔ rule |
| 3.2 | Secrets in Secrets Manager; none in git, images or tfstate | dev | ◐ RDS managed pw |
| 3.3 | KMS encryption: RDS, S3, ECR, EKS secrets | dev | ◐ |
| 3.4 | Private EKS endpoint; VPC endpoints for Bedrock, ECR, S3, STS | dev | ◐ |
| 3.5 | Pod Identity / IRSA, least-privilege roles per service account | dev | ◐ |
| 3.6 | Default-deny NetworkPolicy; egress tightened to endpoint CIDRs | qa | ◐ 443 open |
| 3.7 | Non-root, read-only filesystem, no privilege escalation | dev | ✔ |
| 3.8 | Image scan on push; fail on critical CVEs; signed images | qa | ◐ scan only |
| 3.9 | PII masking in logs and prompts where not needed | qa | ☐ |
| 3.10 | Retention and deletion policy for cases, ledger, outputs (bank) | prod | ☐ |
| 3.11 | Audit trail: who ran, what data version, which model/prompt (bank) | prod | ◐ ledger |
| 3.12 | Bedrock only in production; model access and quota confirmed | dev | ☐ |

## 4. Platform and delivery
| 4.1 | Terraform for all infra; remote state with lock; plan in CI | dev | ◐ unvalidated |
| 4.2 | Immutable image tags = git SHA; promote by tag bump PR | dev | ◐ |
| 4.3 | Argo CD: dev auto, qa/prod manual sync | dev | ◐ |
| 4.4 | Branch protection, required reviews, CODEOWNERS | dev | ☐ |
| 4.5 | Separate AWS accounts or strong isolation for prod | qa | ☐ |
| 4.6 | Resource quotas, LimitRange, node autoscaling (Karpenter/CA) | qa | ◐ quota only |
| 4.7 | Rollback tested (git revert + sync) | qa | ☐ |
| 4.8 | Change tickets linked to prod promotions (bank) | prod | ☐ |

## 5. Reliability and operations
| 5.1 | RDS Multi-AZ, automated backups, restore tested | qa | ◐ configured |
| 5.2 | Bedrock throttling: retry with backoff, concurrency limits, quota raised | qa | ☐ |
| 5.3 | Metrics: case duration, step latency, token use, failures, queue depth | qa | ☐ |
| 5.4 | Central logs, trace IDs per case | qa | ☐ |
| 5.5 | Alerts and on-call route; runbook per alert | prod | ◐ starter runbook |
| 5.6 | Failure drills: kill pod, DB failover, Bedrock throttle, bad data | qa | ☐ |
| 5.7 | Cost budget and alarm; per-case cost reported | qa | ☐ |
| 5.8 | CDC poller lag alert; reprocess / replay procedure | qa | ☐ |
| 5.9 | Disaster recovery target (RPO/RTO) agreed | prod | ☐ |

## 6. Governance
| 6.1 | Model risk review and documentation (bank; confirm SR 11-7 applicability) | prod | ☐ |
| 6.2 | Security architecture review and pen test as required | prod | ☐ |
| 6.3 | Data owner approval for data use | prod | ☐ |
| 6.4 | Documented limits: what the agent may not decide | prod | ☐ |
| 6.5 | Limited live release before full cutover; exit criteria written | prod | ☐ |

## Tools list (what to have in place)
Terraform, Helm, kubectl, Argo CD, GitHub Actions with OIDC to AWS, ECR, EKS, RDS Postgres, S3, KMS, Secrets Manager, Bedrock, CloudWatch or your standard observability stack, an eval harness, an image scanner, a secrets scanner, a ticketing link for changes.
