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

# Quick Start Instructions
output "next_steps" {
  description = "Next steps after deployment"
  value       = <<-EOT

    Deployment complete! Next steps:

    1. Build and push your container:
       aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${module.foundation.ecr_repository_url}
       docker build -t ${module.foundation.ecr_repository_url}:${var.container_image_tag} .
       docker push ${module.foundation.ecr_repository_url}:${var.container_image_tag}

    2. Update your .env with Salesforce Connected App credentials:
       SALESFORCE_INSTANCE_URL=https://myorg.my.salesforce.com
       SALESFORCE_CLIENT_ID=<your consumer key>
       SALESFORCE_CLIENT_SECRET=<your consumer secret>

    3. Test locally, then deploy to AgentCore.

  EOT
}
