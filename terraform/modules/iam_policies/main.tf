# Least-privilege policy documents for the two service accounts.
variable "region" { type = string }
variable "bedrock_model_ids" { type = list(string) }       # e.g. foundation-model IDs or inference-profile IDs you enabled
variable "bedrock_inference_profile_arns" {
  type    = list(string)
  default = []
}
variable "artifacts_bucket_arn" { type = string }
variable "db_secret_arn" { type = string }

locals {
  model_arns = concat(
    [for m in var.bedrock_model_ids : "arn:aws:bedrock:*::foundation-model/${m}"],
    var.bedrock_inference_profile_arns
  )
}

data "aws_iam_policy_document" "agent" {
  statement {
    sid       = "BedrockInvoke"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = local.model_arns
  }
  statement {
    sid       = "ArtifactsRW"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${var.artifacts_bucket_arn}/*"]
  }
  statement {
    sid       = "ArtifactsList"
    actions   = ["s3:ListBucket"]
    resources = [var.artifacts_bucket_arn]
  }
  statement {
    sid       = "ReadDbSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }
}
data "aws_iam_policy_document" "dispatcher" {
  statement {
    sid       = "ReadDbSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }
}
output "agent_json" { value = data.aws_iam_policy_document.agent.json }
output "dispatcher_json" { value = data.aws_iam_policy_document.dispatcher.json }
