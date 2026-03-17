# =============================================================================
# MCP Server Infrastructure - Root Module
# =============================================================================
#
# This deploys an MCP server to AWS Bedrock AgentCore with OpenSearch backend.
#
# Resources created:
# - ECR repository for container images
# - OpenSearch managed domain for document storage
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

  project_name = var.project_name
  environment  = var.environment

  # Optional: pre-populate API key secret
  # api_key = var.api_key

  tags = var.tags
}

# =============================================================================
# OpenSearch Managed Domain
# =============================================================================
module "opensearch" {
  source = "./modules/opensearch"

  domain_name   = var.project_name
  environment   = var.environment
  index_name    = var.opensearch_index_name
  instance_type = var.opensearch_instance_type
  instance_count = var.opensearch_instance_count
  volume_size   = var.opensearch_volume_size

  master_user_name     = var.opensearch_master_user
  master_user_password = var.opensearch_master_password

  agentcore_execution_role_arn = module.foundation.agentcore_execution_role_arn

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

  ecr_repository_url  = module.foundation.ecr_repository_url
  container_image_tag = var.container_image_tag
  execution_role_arn  = module.foundation.agentcore_execution_role_arn
  codebuild_role_arn  = module.foundation.codebuild_role_arn
  codebuild_source_bucket = module.foundation.codebuild_source_bucket

  tags = var.tags

  depends_on = [module.foundation, module.opensearch]
}

# =============================================================================
# Monitoring - CloudWatch Dashboards and Alarms
# =============================================================================
module "monitoring" {
  source = "./modules/monitoring"

  project_name = var.project_name
  environment  = var.environment

  opensearch_domain_name = module.opensearch.domain_name
  agentcore_runtime_name = "${var.project_name}-${var.environment}"

  alarm_email = var.alarm_email

  tags = var.tags

  depends_on = [module.agentcore]
}
