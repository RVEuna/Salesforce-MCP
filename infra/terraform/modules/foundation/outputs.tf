output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.mcp_server.repository_url
}

output "ecr_repository_arn" {
  description = "ECR repository ARN"
  value       = aws_ecr_repository.mcp_server.arn
}

output "agentcore_execution_role_arn" {
  description = "AgentCore execution role ARN"
  value       = aws_iam_role.agentcore_execution.arn
}

output "codebuild_role_arn" {
  description = "CodeBuild role ARN"
  value       = aws_iam_role.codebuild.arn
}

output "codebuild_source_bucket" {
  description = "S3 bucket for CodeBuild sources"
  value       = aws_s3_bucket.codebuild_source.bucket
}

output "secrets_arn" {
  description = "Secrets Manager secret ARN"
  value       = aws_secretsmanager_secret.api_keys.arn
}
