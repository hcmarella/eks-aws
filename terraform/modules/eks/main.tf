variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "node_instance_types" { type = list(string) }
variable "node_min" { type = number }
variable "node_max" { type = number }
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"
  cluster_name                             = var.name
  cluster_version                          = "1.31"
  vpc_id                                   = var.vpc_id
  subnet_ids                               = var.subnet_ids
  cluster_endpoint_public_access           = false
  enable_cluster_creator_admin_permissions = true
  cluster_addons = { eks-pod-identity-agent = {}, coredns = {}, kube-proxy = {}, vpc-cni = {} }
  eks_managed_node_groups = {
    default = { instance_types = var.node_instance_types, min_size = var.node_min, max_size = var.node_max, desired_size = var.node_min }
  }
}
output "cluster_name" { value = module.eks.cluster_name }
output "node_security_group_id" { value = module.eks.node_security_group_id }
