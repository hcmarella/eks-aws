# Alternative to Pod Identity: IRSA (OIDC-trust role for a ServiceAccount).
variable "name" { type = string }
variable "oidc_provider_arn" { type = string }
variable "oidc_provider" { type = string } # issuer URL without https://
variable "namespace" { type = string }
variable "service_account" { type = string }
variable "policy_json" { type = string }
data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${var.service_account}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "this" { name = var.name, assume_role_policy = data.aws_iam_policy_document.trust.json }
resource "aws_iam_role_policy" "this" { role = aws_iam_role.this.id, policy = var.policy_json }
output "role_arn" { value = aws_iam_role.this.arn }  # put in values-<env>.yaml serviceAccounts.*RoleArn
