# =============================================================================
# Foundation Module - Secrets Manager
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# =============================================================================
# Secrets Manager - API Keys & Config
#
# Secret values are managed via the AWS Console, not Terraform.
# This only creates the secret resource itself.
# =============================================================================
resource "aws_secretsmanager_secret" "api_keys" {
  name        = "mcp/${var.project_name}/api-keys"
  description = "Salesforce and MCP configuration for ${var.project_name}"

  tags = merge(var.tags, {
    Name = "mcp-${var.project_name}-api-keys"
  })
}

# =============================================================================
# Data Sources
# =============================================================================
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
