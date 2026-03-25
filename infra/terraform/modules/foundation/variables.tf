variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "execution_role_arn" {
  description = "Existing IAM role ARN. When provided, IAM roles are not created."
  type        = string
  default     = ""
}

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

variable "mcp_jwt_secret" {
  description = "JWT signing secret for the MCP OAuth proxy"
  type        = string
  sensitive   = true
}

variable "mcp_base_url" {
  description = "Public base URL of the MCP server"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
