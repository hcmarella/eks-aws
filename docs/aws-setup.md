# AWS preparation: IAM, IRSA / Pod Identity, Postgres (RDS), Bedrock access
Per environment (dev, qa, prod). Terraform in `terraform/` creates most of this; the manual steps are the ones Terraform cannot do. Unvalidated: run `terraform validate` and `plan` first and correct as needed. Replace every `REPLACE-*`.

## 0. Decide first
| Decision | Default here |
|---|---|
| Pod → AWS identity | **EKS Pod Identity** (add-on `eks-pod-identity-agent`, no ServiceAccount annotation). IRSA is the alternative (`modules/iam_irsa`, role ARN goes in `values-<env>.yaml`). |
| Accounts | Separate AWS account for prod recommended |
| Region | us-east-1 in files; change `region`, backend and endpoints together |
| Bedrock models | Whatever your account has enabled; confirm in step 1 |

## 1. Bedrock model access (manual, per account and region)
1. In the Bedrock console for your region, open the model catalog and check the Claude models you intend to use. Confirm they are available to you; some accounts must request access or submit Anthropic use-case details first, and an organization SCP can block it. Ask your cloud team if a model shows as unavailable.
2. Note the exact **model ID** (and the **inference profile ID/ARN** if the model is only callable through a cross-region profile).
3. Put them in `terraform/envs/<env>/<env>.tfvars` (`bedrock_model_ids`, optional `bedrock_inference_profile_arns`) and in `helm/fraudagent/values-<env>.yaml` (`bedrockModelId`).
4. Request quota (requests/min, tokens/min) for the expected concurrency; defaults are low. Quotas are per account, region and model.
5. Test from your terminal with a role that can call it: `aws bedrock-runtime converse --model-id <id> --messages '[{"role":"user","content":[{"text":"ping"}]}]' --region <region>`.
6. Cross-region inference profiles can route to other regions: confirm that is allowed by your data policy before using one.

## 2. IAM (Terraform: `modules/iam_policies`, `iam_pod_identity`, `iam_irsa`)
Two service accounts, two roles, least privilege:

| ServiceAccount | Role | Allowed |
|---|---|---|
| `agent-sa` | `fraudagent-<env>-agent` | `bedrock:InvokeModel*` on the listed model/profile ARNs only; S3 get/put on the artifacts bucket; read the DB secret |
| `dispatcher-sa` | `fraudagent-<env>-dispatcher` | read the DB secret (Kubernetes permission to create Jobs is a separate RBAC Role in the Helm chart) |

CI roles (create once, trust GitHub OIDC): ECR push role (`ecr:*` push actions on the `fraudagent` repo) and Terraform plan role (read-only). Store ARNs as repo variables `AWS_ECR_PUSH_ROLE_ARN`, `AWS_TF_PLAN_ROLE_ARN`. These two are **not** in Terraform here.

KMS: if RDS, S3 or the secret use a customer-managed key, add `kms:Decrypt`/`GenerateDataKey` for that key to the policies. The files use default AWS-managed keys.

### Pod Identity (default)
Applying `envs/<env>` creates the role and an `aws_eks_pod_identity_association` per ServiceAccount. Nothing to annotate. Verify:
`kubectl -n fraudagent-<env> run t --rm -i --restart=Never --serviceaccount=agent-sa --image=amazon/aws-cli -- sts get-caller-identity` → shows the agent role.

### IRSA (alternative)
Uncomment `agent_irsa` (and add the dispatcher equivalent) in `envs/<env>/main.tf`, remove the Pod Identity modules, apply, then set `serviceAccounts.agentRoleArn` and `dispatcherRoleArn` in `values-<env>.yaml` to the `role_arn` outputs. Trust is limited to `system:serviceaccount:<namespace>:<sa>`; a wrong namespace or SA name is the usual cause of AccessDenied.

## 3. Postgres (RDS, `modules/rds`)
Created: PostgreSQL 16, encrypted, private subnets, security group allowing 5432 only from the node security group, password managed by RDS in Secrets Manager (`manage_master_user_password`), 7-day backups, Multi-AZ and deletion protection in qa/prod.

Steps after `terraform apply`:
1. Note outputs `db_endpoint` and `db_secret_arn`.
2. Create the in-cluster secret (nothing goes to git): `scripts/create-db-secret.sh <env> <db_secret_arn> <db_endpoint>`
3. Create tables: `scripts/init-db.sh <env>` (runs `app/schema.sql` from a pod, since RDS is private; the SQL is idempotent).
4. Confirm: `kubectl -n fraudagent-<env> run q --rm -i --restart=Never --image=postgres:16 --env=... -- psql ...` or check the `ledger` table exists.
5. Prefer a dedicated application user (not the master user) for production; create it by SQL and point the secret at it. Not automated here.
6. Test a restore from a snapshot in qa before prod.
Note: the RDS master secret rotates only if you enable rotation; if it rotates, re-run step 2 or move to a secret-sync tool (External Secrets) before prod.

## 4. Networking prerequisites
- Private subnets in at least two AZs (IDs in tfvars)
- VPC endpoints: `bedrock-runtime`, `ecr.api`, `ecr.dkr`, `s3` (gateway), `sts`, `secretsmanager`, `logs`; the Terraform here does **not** create them
- Tighten the NetworkPolicy egress (currently port 443 to anywhere) to those endpoint CIDRs

## 5. Order of operations
1. Request access/approvals ([access-requests.md](access-requests.md)); Bedrock models and quota (step 1)
2. Create state bucket/lock table, CI OIDC roles, VPC endpoints (manual)
3. `terraform apply` envs/dev → EKS, RDS, S3, IAM
4. Install Argo CD; create DB secret; init DB; apply Argo app
5. Verify identity, Bedrock call and DB from a pod
6. Repeat for qa, then prod

## 6. What to update where
| File | Value |
|---|---|
| `terraform/envs/<env>/<env>.tfvars` | vpc_id, private_subnet_ids, bedrock_model_ids |
| `terraform/envs/<env>/main.tf` | backend bucket/table, S3 bucket name |
| `helm/fraudagent/values-<env>.yaml` | ECR repo (account id), bedrockModelId, role ARNs only if IRSA |
| GitHub repo variables | AWS_ECR_PUSH_ROLE_ARN, AWS_TF_PLAN_ROLE_ARN |
