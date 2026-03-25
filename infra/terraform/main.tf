# =============================================================================
# MCP Server Infrastructure - Root Module
# =============================================================================
#
# This deploys a Salesforce MCP server to AWS Bedrock AgentCore.
#
# Resources created:
# - ECR repository for container images
# - AgentCore runtime for MCP server hosting
# - IAM roles and policies
# - CloudWatch dashboards and alarms
# - Secrets Manager for API keys
#
# Usage:
#   1. Copy terraform.tfvars.example to terraform.tfvars
#   2. Edit terraform.tfvars with your values
#   3. Run: terraform init && terraform apply

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }

  # Uncomment to use remote state (recommended for team environments)
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "mcp-server/terraform.tfstate"
  #   region         = "us-east-2"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# =============================================================================
# Foundation - IAM, ECR, Secrets
# =============================================================================
module "foundation" {
  source = "./modules/foundation"

  project_name       = var.project_name
  environment        = var.environment
  execution_role_arn = var.execution_role_arn

  salesforce_instance_url     = var.salesforce_instance_url
  salesforce_login_url        = var.salesforce_login_url
  salesforce_client_id        = var.salesforce_client_id
  salesforce_client_secret    = var.salesforce_client_secret
  salesforce_api_version      = var.salesforce_api_version
  salesforce_access_token_ttl = var.salesforce_access_token_ttl
  mcp_jwt_secret              = var.mcp_jwt_secret
  mcp_base_url                = var.mcp_base_url

  tags = var.tags
}

# =============================================================================
# AgentCore Runtime
# =============================================================================
module "agentcore" {
  source = "./modules/agentcore"

  project_name       = var.project_name
  environment        = var.environment
  agent_runtime_name = var.project_name

  ecr_repository_url      = module.foundation.ecr_repository_url
  container_image_tag     = var.container_image_tag
  execution_role_arn      = module.foundation.agentcore_execution_role_arn
  codebuild_role_arn      = module.foundation.codebuild_role_arn
  codebuild_source_bucket = module.foundation.codebuild_source_bucket
  create_codebuild        = var.execution_role_arn == ""

  tags = var.tags

  depends_on = [module.foundation]
}

# =============================================================================
# Monitoring - CloudWatch Dashboards and Alarms
# =============================================================================
module "monitoring" {
  source = "./modules/monitoring"

  project_name = var.project_name
  environment  = var.environment

  agentcore_runtime_name = "${var.project_name}-${var.environment}"

  alarm_email = var.alarm_email

  tags = var.tags

  depends_on = [module.agentcore]
}
