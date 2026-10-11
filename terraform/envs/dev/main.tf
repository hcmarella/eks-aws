terraform {
  required_version = ">= 1.6"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
  backend "s3" {
    bucket         = "REPLACE-tfstate-bucket"   # created once by hand
    key            = "conductor/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "REPLACE-tf-lock"
    encrypt        = true
  }
}
provider "aws" { region = var.region }
variable "region" { default = "us-east-1" }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }

locals { name = "conductor-dev" }

module "ecr" {
  source = "../../modules/ecr"
  name   = "conductor" # one repo shared by all envs; promote by tag, never rebuild
}
module "eks" {
  source              = "../../modules/eks"
  name                = local.name
  vpc_id              = var.vpc_id
  subnet_ids          = var.private_subnet_ids
  node_instance_types = ["m6i.large"]
  node_min            = 2
  node_max            = 4
}
module "rds" {
  source         = "../../modules/rds"
  name           = local.name
  vpc_id         = var.vpc_id
  subnet_ids     = var.private_subnet_ids
  allowed_sg_ids = [module.eks.node_security_group_id]
  multi_az       = false
  instance_class = "db.t4g.small"
}
module "artifacts" {
  source = "../../modules/s3"
  bucket = "REPLACE-conductor-dev-artifacts"
}
