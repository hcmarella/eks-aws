variable "name" { type = string }
variable "subnet_ids" { type = list(string) }
variable "vpc_id" { type = string }
variable "allowed_sg_ids" { type = list(string) }
variable "multi_az" { type = bool }
variable "instance_class" { type = string }
resource "aws_db_subnet_group" "this" { name = var.name, subnet_ids = var.subnet_ids }
resource "aws_security_group" "db" {
  name   = "${var.name}-db"
  vpc_id = var.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_sg_ids
  }
}
resource "aws_db_instance" "this" {
  identifier                  = var.name
  engine                      = "postgres"
  engine_version              = "16"
  instance_class              = var.instance_class
  allocated_storage           = 50
  storage_encrypted           = true
  multi_az                    = var.multi_az
  db_subnet_group_name        = aws_db_subnet_group.this.name
  vpc_security_group_ids      = [aws_security_group.db.id]
  username                    = "conductor"
  manage_master_user_password = true # password lives in Secrets Manager, not in state files or git
  backup_retention_period     = 7
  deletion_protection         = var.multi_az
  skip_final_snapshot         = !var.multi_az
}
output "endpoint" { value = aws_db_instance.this.address }
output "secret_arn" { value = aws_db_instance.this.master_user_secret[0].secret_arn }
