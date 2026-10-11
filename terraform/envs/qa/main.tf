terraform {
  required_version = ">= 1.6"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
  backend "s3" {
    bucket         = "REPLACE-tfstate-bucket"   # created once by hand
    key            = "conductor/qa/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "REPLACE-tf-lock"
    encrypt        = true
  }
}
provider "aws" { region = var.region }
variable "region" { default = "us-east-1" }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }

locals { name = "conductor-qa" }

module "eks" {
  source              = "../../modules/eks"
  name                = local.name
  vpc_id              = var.vpc_id
  subnet_ids          = var.private_subnet_ids
  node_instance_types = ["m6i.xlarge"]
  node_min            = 2
  node_max            = 6
}
module "rds" {
  source         = "../../modules/rds"
  name           = local.name
  vpc_id         = var.vpc_id
  subnet_ids     = var.private_subnet_ids
  allowed_sg_ids = [module.eks.node_security_group_id]
  multi_az       = true
  instance_class = "db.m6g.large"
}
module "artifacts" {
  source = "../../modules/s3"
  bucket = "REPLACE-conductor-qa-artifacts"
}
