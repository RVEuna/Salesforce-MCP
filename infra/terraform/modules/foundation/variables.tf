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

variable "api_key" {
  description = "API key to store in Secrets Manager"
  type        = string
  default     = ""
  sensitive   = true
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
