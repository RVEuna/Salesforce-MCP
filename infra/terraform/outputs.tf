# =============================================================================
# Outputs
# =============================================================================

# ECR
output "ecr_repository_url" {
  description = "ECR repository URL for container images"
  value       = module.foundation.ecr_repository_url
}

# AgentCore
output "agentcore_runtime_id" {
  description = "AgentCore runtime ID"
  value       = module.agentcore.runtime_id
}

output "agentcore_runtime_arn" {
  description = "AgentCore runtime ARN"
  value       = module.agentcore.runtime_arn
}

# IAM
output "agentcore_execution_role_arn" {
  description = "IAM role ARN for AgentCore execution"
  value       = module.foundation.agentcore_execution_role_arn
}

# Secrets Manager
output "secrets_arn" {
  description = "Secrets Manager secret ARN"
  value       = module.foundation.secrets_arn
}

# Quick Start Instructions
output "next_steps" {
  description = "Next steps after deployment"
  value       = <<-EOT

    Deployment complete! Next steps:

    1. Build and push your container:
       aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${module.foundation.ecr_repository_url}
       docker build -t ${module.foundation.ecr_repository_url}:${var.container_image_tag} .
       docker push ${module.foundation.ecr_repository_url}:${var.container_image_tag}

    2. Secrets Manager has been populated by Terraform with your
       Salesforce and MCP credentials. Verify with:
       aws secretsmanager get-secret-value --secret-id ${module.foundation.secrets_arn} --query SecretString --output text | python -m json.tool

    3. AgentCore will load secrets from Secrets Manager at container startup.

  EOT
}
