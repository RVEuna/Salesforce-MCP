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

# AgentCore JWT Authorizer (for OAuth proxy + Salesforce JWT tokens)
variable "jwt_authorizer_discovery_url" {
  description = "OIDC discovery URL for AgentCore customJWTAuthorizer. Typically: https://<sf-instance>.my.salesforce.com/.well-known/openid-configuration"
  type        = string
  default     = ""
}

variable "jwt_authorizer_audiences" {
  description = "Allowed JWT audience values for AgentCore (typically the Connected App client ID)"
  type        = list(string)
  default     = []
}

# OAuth Proxy (Lambda)
variable "deploy_oauth_proxy" {
  description = "Whether to deploy the OAuth proxy Lambda"
  type        = bool
  default     = false
}

variable "oauth_proxy_agentcore_url" {
  description = "AgentCore invocation URL for the OAuth proxy to forward /mcp requests"
  type        = string
  default     = ""
}

variable "oauth_proxy_secret" {
  description = "Secret for the OAuth proxy to encrypt short-lived auth codes"
  type        = string
  sensitive   = true
  default     = ""
}

variable "oauth_proxy_lambda_zip_path" {
  description = "Local path to the OAuth proxy Lambda zip"
  type        = string
  default     = ""
}

variable "oauth_proxy_lambda_s3_bucket" {
  description = "S3 bucket containing the OAuth proxy Lambda zip"
  type        = string
  default     = ""
}

variable "oauth_proxy_lambda_s3_key" {
  description = "S3 key for the OAuth proxy Lambda zip"
  type        = string
  default     = ""
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
