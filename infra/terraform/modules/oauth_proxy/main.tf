# =============================================================================
# MCP Server Module - Lambda + Function URL
# =============================================================================
#
# Deploys the Salesforce MCP server as a Lambda function with a public
# Function URL. All config is loaded from Secrets Manager at runtime.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  function_name = "${var.project_name}-${var.environment}"
}

# =============================================================================
# CloudWatch Log Group
# =============================================================================
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name = "${local.function_name}-logs"
  })
}

# =============================================================================
# IAM Role
# =============================================================================
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, {
    Name = "${local.function_name}-role"
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_secrets" {
  name = "SecretsManagerAccess"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [var.secrets_arn]
      }
    ]
  })
}

# =============================================================================
# Lambda Function
# =============================================================================
resource "aws_lambda_function" "mcp_server" {
  function_name = local.function_name
  description   = "Salesforce MCP server with OAuth (${var.environment})"
  role          = aws_iam_role.lambda.arn

  runtime       = "python3.13"
  architectures = [var.lambda_architecture]
  handler       = "mcp_server.server.handler"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory

  filename         = var.lambda_zip_path != "" ? var.lambda_zip_path : null
  s3_bucket        = var.lambda_s3_bucket != "" ? var.lambda_s3_bucket : null
  s3_key           = var.lambda_s3_key != "" ? var.lambda_s3_key : null
  source_code_hash = var.lambda_zip_path != "" ? filebase64sha256(var.lambda_zip_path) : null

  environment {
    variables = {
      MCP_SECRET_PROVIDER  = "aws"
      MCP_AWS_SECRET_NAME  = var.secret_name
      MCP_AWS_SECRET_REGION = data.aws_region.current.name
      MCP_LOG_LEVEL        = var.log_level
      MCP_LOG_FORMAT       = "json"
      MCP_STATELESS        = "true"
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = merge(var.tags, {
    Name = local.function_name
  })
}

# =============================================================================
# Lambda Function URL (public, auth handled at application layer)
# =============================================================================
resource "aws_lambda_function_url" "mcp_server" {
  function_name      = aws_lambda_function.mcp_server.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "DELETE"]
    allow_headers = ["authorization", "content-type", "accept", "mcp-session-id"]
  }
}

resource "aws_lambda_permission" "public_invoke" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.mcp_server.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# =============================================================================
# Data Sources
# =============================================================================
data "aws_region" "current" {}
