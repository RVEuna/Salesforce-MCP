variable "domain_name" {
  description = "OpenSearch domain name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "engine_version" {
  description = "OpenSearch engine version"
  type        = string
  default     = "OpenSearch_2.13"
}

variable "instance_type" {
  description = "OpenSearch instance type"
  type        = string
  default     = "r6g.large.search"
}

variable "instance_count" {
  description = "Number of data nodes"
  type        = number
  default     = 2
}

variable "volume_size" {
  description = "EBS volume size per node in GB"
  type        = number
  default     = 100
}

variable "master_user_name" {
  description = "Master user name"
  type        = string
  default     = "admin"
}

variable "master_user_password" {
  description = "Master user password"
  type        = string
  sensitive   = true
}

variable "index_name" {
  description = "Name of the vector index"
  type        = string
  default     = "documents"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "agentcore_execution_role_arn" {
  description = "ARN of AgentCore execution role"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
