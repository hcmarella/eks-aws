# Promotion flow: local → dev → qa → prod

![promotion](images/d9_promotion.png)

1. Develop in a branch. `make test` (replay runner, no model, no AWS).
2. Open a PR. CI runs tests and YAML lint.
3. Merge to `main`. CI builds `fraudagent:<git-sha>` and pushes to ECR (OIDC role; tags are immutable).
4. Run the **promote** workflow with env=`dev` and the SHA. It opens a PR that only changes `image.tag` in `values-dev.yaml`. Merge → Argo CD auto-syncs dev.
5. Dev gate: eval harness and failure drills pass. Run **promote** for `qa`. Merge needs a reviewer; sync in Argo CD is manual.
6. QA gate: shadow-mode comparison against BAU outputs. Run **promote** for `prod`. Merge needs approvers plus a change ticket; sync is manual.
7. Rollback: `git revert` the tag-bump commit and sync.

What differs per environment: `values-<env>.yaml` and `terraform/envs/<env>`. What never differs: the image and the chart.

| | local | dev | qa | prod |
|---|---|---|---|---|
| Cluster | minikube | EKS | EKS | EKS |
| DB | Postgres pod | RDS small | RDS Multi-AZ | RDS Multi-AZ |
| Model runner | replay | bedrock | bedrock | bedrock |
| Data | synthetic | synthetic | masked/synthetic | real |
| Deploy | `scripts/local-up.sh` | Argo auto | Argo manual | Argo manual |
