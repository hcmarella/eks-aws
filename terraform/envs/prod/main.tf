terraform {
  required_version = ">= 1.6"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
  backend "s3" {
    bucket         = "REPLACE-tfstate-bucket"   # created once by hand
    key            = "fraudagent/prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "REPLACE-tf-lock"
    encrypt        = true
  }
}
provider "aws" { region = var.region }
variable "region" { default = "us-east-1" }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }

locals { name = "fraudagent-prod" }

module "eks" {
  source              = "../../modules/eks"
  name                = local.name
  vpc_id              = var.vpc_id
  subnet_ids          = var.private_subnet_ids
  node_instance_types = ["m6i.xlarge"]
  node_min            = 3
  node_max            = 10
}
module "rds" {
  source         = "../../modules/rds"
  name           = local.name
  vpc_id         = var.vpc_id
  subnet_ids     = var.private_subnet_ids
  allowed_sg_ids = [module.eks.node_security_group_id]
  multi_az       = true
  instance_class = "db.m6g.xlarge"
}
module "artifacts" {
  source = "../../modules/s3"
  bucket = "REPLACE-fraudagent-prod-artifacts"
}

variable "bedrock_model_ids" {
  type        = list(string)
  description = "Bedrock model IDs enabled for this account/region (confirm in the Bedrock console)"
}
variable "bedrock_inference_profile_arns" {
  type    = list(string)
  default = []
}
variable "namespace" { default = "fraudagent-prod" }

module "iam_policies" {
  source                         = "../../modules/iam_policies"
  region                         = var.region
  bedrock_model_ids              = var.bedrock_model_ids
  bedrock_inference_profile_arns = var.bedrock_inference_profile_arns
  artifacts_bucket_arn           = module.artifacts.arn
  db_secret_arn                  = module.rds.secret_arn
}

# Default: EKS Pod Identity (no annotation on the ServiceAccount).
module "agent_identity" {
  source          = "../../modules/iam_pod_identity"
  name            = "${local.name}-agent"
  cluster_name    = module.eks.cluster_name
  namespace       = var.namespace
  service_account = "agent-sa"
  policy_json     = module.iam_policies.agent_json
}
module "dispatcher_identity" {
  source          = "../../modules/iam_pod_identity"
  name            = "${local.name}-dispatcher"
  cluster_name    = module.eks.cluster_name
  namespace       = var.namespace
  service_account = "dispatcher-sa"
  policy_json     = module.iam_policies.dispatcher_json
}

# IRSA alternative: replace the two Pod Identity modules with iam_irsa, then copy role_arn into values-<env>.yaml.
# module "agent_irsa" {
#   source            = "../../modules/iam_irsa"
#   name              = "${local.name}-agent"
#   oidc_provider_arn = module.eks.oidc_provider_arn
#   oidc_provider     = module.eks.oidc_provider
#   namespace         = var.namespace
#   service_account   = "agent-sa"
#   policy_json       = module.iam_policies.agent_json
# }
output "db_endpoint" { value = module.rds.endpoint }
output "db_secret_arn" { value = module.rds.secret_arn }
