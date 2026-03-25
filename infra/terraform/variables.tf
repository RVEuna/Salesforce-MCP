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

# Salesforce Credentials (stored in Secrets Manager)
variable "salesforce_instance_url" {
  description = "Salesforce instance URL"
  type        = string
  sensitive   = true
}

variable "salesforce_login_url" {
  description = "Salesforce OAuth login endpoint"
  type        = string
  default     = "https://login.salesforce.com"
}

variable "salesforce_client_id" {
  description = "Salesforce Connected App consumer key"
  type        = string
  sensitive   = true
}

variable "salesforce_client_secret" {
  description = "Salesforce Connected App consumer secret"
  type        = string
  sensitive   = true
}

variable "salesforce_api_version" {
  description = "Salesforce API version"
  type        = string
  default     = "v66.0"
}

variable "salesforce_access_token_ttl" {
  description = "Salesforce access token cache lifetime in seconds"
  type        = number
  default     = 7200
}

# MCP Credentials (stored in Secrets Manager)
variable "mcp_jwt_secret" {
  description = "JWT signing secret for the MCP OAuth proxy"
  type        = string
  sensitive   = true
}

variable "mcp_base_url" {
  description = "Public base URL of the MCP server"
  type        = string
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
