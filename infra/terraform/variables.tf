# =============================================================================
# Input Variables
# =============================================================================

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-2"
}

variable "project_name" {
  description = "Project name (used in resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

# AgentCore Configuration
variable "execution_role_arn" {
  description = "Existing IAM role ARN for AgentCore execution. If provided, skips IAM role creation (useful when you lack iam:CreateRole permissions)."
  type        = string
  default     = ""
}

variable "container_image_tag" {
  description = "Docker image tag for the MCP server"
  type        = string
  default     = "latest"
}

# Monitoring Configuration
variable "alarm_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = ""
}

# Tags
variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
