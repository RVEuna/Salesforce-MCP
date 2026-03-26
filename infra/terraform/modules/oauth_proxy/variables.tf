variable "project_name" {
  description = "Project name (used in resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

# Lambda deployment artifact (provide EITHER zip path OR S3 location)
variable "lambda_zip_path" {
  description = "Local path to the Lambda zip file. Mutually exclusive with lambda_s3_*."
  type        = string
  default     = ""
}

variable "lambda_s3_bucket" {
  description = "S3 bucket containing the Lambda zip. Mutually exclusive with lambda_zip_path."
  type        = string
  default     = ""
}

variable "lambda_s3_key" {
  description = "S3 key for the Lambda zip. Mutually exclusive with lambda_zip_path."
  type        = string
  default     = ""
}

variable "lambda_architecture" {
  description = "Lambda CPU architecture (arm64 or x86_64)"
  type        = string
  default     = "arm64"
}

# Salesforce Connected App credentials
variable "salesforce_client_id" {
  description = "Connected App consumer key"
  type        = string
  sensitive   = true
}

variable "salesforce_client_secret" {
  description = "Connected App consumer secret"
  type        = string
  sensitive   = true
}

variable "salesforce_login_url" {
  description = "Salesforce OAuth login endpoint (https://login.salesforce.com or https://test.salesforce.com)"
  type        = string
}

# AgentCore
variable "agentcore_url" {
  description = "Full AgentCore runtime invocation URL (e.g. https://<id>.runtime.agentcore.<region>.amazonaws.com/mcp)"
  type        = string
}

# Proxy config
variable "proxy_secret" {
  description = "Secret for encrypting short-lived auth codes"
  type        = string
  sensitive   = true
}

variable "proxy_base_url" {
  description = "Public base URL of the proxy (set after initial deploy when function URL is known)"
  type        = string
  default     = ""
}

variable "log_level" {
  description = "Logging level"
  type        = string
  default     = "INFO"
}

variable "sf_access_token_ttl" {
  description = "Access token TTL returned to clients (seconds)"
  type        = number
  default     = 7200
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
