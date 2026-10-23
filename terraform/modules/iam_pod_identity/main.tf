variable "name" { type = string }
variable "cluster_name" { type = string }
variable "namespace" { type = string }
variable "service_account" { type = string }
variable "policy_json" { type = string }
data "aws_iam_policy_document" "trust" {
  statement {
    actions    = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "this" { name = var.name, assume_role_policy = data.aws_iam_policy_document.trust.json }
resource "aws_iam_role_policy" "this" { role = aws_iam_role.this.id, policy = var.policy_json }
resource "aws_eks_pod_identity_association" "this" {
  cluster_name    = var.cluster_name
  namespace       = var.namespace
  service_account = var.service_account
  role_arn        = aws_iam_role.this.arn
}
