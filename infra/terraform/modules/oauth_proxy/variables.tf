variable "project_name" {
  description = "Project name (used in resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

# Secrets Manager
variable "secrets_arn" {
  description = "ARN of the Secrets Manager secret containing all config"
  type        = string
}

variable "secret_name" {
  description = "Name of the Secrets Manager secret"
  type        = string
}

# Lambda deployment artifact (provide EITHER zip path OR S3 location)
variable "lambda_zip_path" {
  description = "Local path to the Lambda zip file"
  type        = string
  default     = ""
}

variable "lambda_s3_bucket" {
  description = "S3 bucket containing the Lambda zip"
  type        = string
  default     = ""
}

variable "lambda_s3_key" {
  description = "S3 key for the Lambda zip"
  type        = string
  default     = ""
}

variable "lambda_architecture" {
  description = "Lambda CPU architecture (arm64 or x86_64)"
  type        = string
  default     = "arm64"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
}

variable "log_level" {
  description = "Logging level"
  type        = string
  default     = "INFO"
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
