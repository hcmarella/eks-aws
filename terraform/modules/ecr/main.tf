variable "name" { type = string }
resource "aws_ecr_repository" "this" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "KMS" }
}
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name
  policy = jsonencode({ rules = [{ rulePriority = 1, description = "keep last 50",
    selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 50 }, action = { type = "expire" } }] })
}
output "repository_url" { value = aws_ecr_repository.this.repository_url }
