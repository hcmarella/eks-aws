# Access and approvals to request (start day 1; these set the schedule)
See the Word runbook (`Conductor_Infrastructure_Setup_Runbook.docx`) for fill-in sheets and request wording. Summary:
- AWS account(s) per env, region, VPC and private subnets (IDs go in `terraform/envs/*/*.tfvars`)
- Bedrock model access (which Claude models, quotas) in the region
- ECR push role and Terraform plan role trusted for GitHub OIDC (set repo variables `AWS_ECR_PUSH_ROLE_ARN`, `AWS_TF_PLAN_ROLE_ARN`)
- Terraform state bucket and lock table (create once by hand, then fill `backend` blocks)
- Argo CD installed on the cluster; SSO for the portal
- Databricks read access (Delta Change Data Feed) for the poller
- Security approval for any non-bank environment use; model risk review (confirm whether SR 11-7 applies)
