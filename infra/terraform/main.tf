# =============================================================================
# MCP Server Infrastructure - Root Module
# =============================================================================
#
# Deploys a Salesforce MCP server to AWS Lambda with Secrets Manager.
#
# Resources created:
# - Secrets Manager secret (values managed via Console)
# - Lambda function + Function URL
# - IAM role with Secrets Manager access
# - CloudWatch dashboards and alarms
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
# Foundation - Secrets Manager
# =============================================================================
module "foundation" {
  source = "./modules/foundation"

  project_name = var.project_name
  environment  = var.environment

  tags = var.tags
}

# =============================================================================
# MCP Server - Lambda + Function URL
# =============================================================================
module "mcp_server" {
  source = "./modules/oauth_proxy"

  project_name = var.project_name
  environment  = var.environment

  secrets_arn = module.foundation.secrets_arn
  secret_name = module.foundation.secrets_name

  lambda_zip_path  = var.lambda_zip_path
  lambda_s3_bucket = var.lambda_s3_bucket
  lambda_s3_key    = var.lambda_s3_key

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

  lambda_function_name = module.mcp_server.function_name

  alarm_email = var.alarm_email

  tags = var.tags

  depends_on = [module.mcp_server]
}
