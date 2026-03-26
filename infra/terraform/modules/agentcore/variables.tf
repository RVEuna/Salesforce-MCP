variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "agent_runtime_name" {
  description = "AgentCore runtime name"
  type        = string
}

variable "ecr_repository_url" {
  description = "ECR repository URL"
  type        = string
}

variable "container_image_tag" {
  description = "Container image tag"
  type        = string
  default     = "latest"
}

variable "execution_role_arn" {
  description = "IAM role ARN for AgentCore execution"
  type        = string
}

variable "codebuild_role_arn" {
  description = "IAM role ARN for CodeBuild"
  type        = string
  default     = ""
}

variable "codebuild_source_bucket" {
  description = "S3 bucket for CodeBuild sources"
  type        = string
  default     = ""
}

variable "create_codebuild" {
  description = "Whether to create the CodeBuild project (requires codebuild_role_arn)"
  type        = bool
  default     = true
}

variable "network_mode" {
  description = "Network mode for AgentCore"
  type        = string
  default     = "PUBLIC"
}

variable "container_architecture" {
  description = "Container architecture (ARM or X86_64)"
  type        = string
  default     = "ARM"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# JWT Authorizer (enables customJWTAuthorizer on AgentCore instead of IAM/SigV4)
variable "jwt_authorizer_discovery_url" {
  description = "OIDC discovery URL for customJWTAuthorizer. Set to Salesforce instance URL + /.well-known/openid-configuration. Leave empty to use default IAM auth."
  type        = string
  default     = ""
}

variable "jwt_authorizer_audiences" {
  description = "Allowed JWT audience values (typically the Connected App client ID)"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
