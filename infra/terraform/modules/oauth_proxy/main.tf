# =============================================================================
# OAuth Proxy Module - Lambda + Function URL
# =============================================================================
#
# Deploys the Salesforce OAuth proxy as a Lambda function with a public
# Function URL. The proxy brokers Salesforce OAuth for MCP clients and
# forwards authenticated requests to the AgentCore runtime.

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
# CloudWatch Log Group
# =============================================================================
resource "aws_cloudwatch_log_group" "proxy" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name = "${local.function_name}-logs"
  })
}

# =============================================================================
# IAM Role
# =============================================================================
locals {
  function_name = "${var.project_name}-oauth-proxy-${var.environment}"
}

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

resource "aws_iam_role" "proxy" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, {
    Name = "${local.function_name}-role"
  })
}

resource "aws_iam_role_policy_attachment" "proxy_basic_execution" {
  role       = aws_iam_role.proxy.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# =============================================================================
# Lambda Function
# =============================================================================
resource "aws_lambda_function" "proxy" {
  function_name = local.function_name
  description   = "Salesforce OAuth proxy for MCP clients connecting to AgentCore"
  role          = aws_iam_role.proxy.arn

  runtime       = "python3.13"
  architectures = [var.lambda_architecture]
  handler       = "salesforce_oauth_proxy.handler"
  timeout       = 300
  memory_size   = 256

  filename         = var.lambda_zip_path != "" ? var.lambda_zip_path : null
  s3_bucket        = var.lambda_s3_bucket != "" ? var.lambda_s3_bucket : null
  s3_key           = var.lambda_s3_key != "" ? var.lambda_s3_key : null
  source_code_hash = var.lambda_zip_path != "" ? filebase64sha256(var.lambda_zip_path) : null

  environment {
    variables = {
      SALESFORCE_CLIENT_ID     = var.salesforce_client_id
      SALESFORCE_CLIENT_SECRET = var.salesforce_client_secret
      SALESFORCE_LOGIN_URL     = var.salesforce_login_url
      AGENTCORE_URL            = var.agentcore_url
      PROXY_SECRET             = var.proxy_secret
      PROXY_BASE_URL           = var.proxy_base_url
      LOG_LEVEL                = var.log_level
      SF_ACCESS_TOKEN_TTL      = tostring(var.sf_access_token_ttl)
    }
  }

  depends_on = [aws_cloudwatch_log_group.proxy]

  tags = merge(var.tags, {
    Name = local.function_name
  })
}

# =============================================================================
# Lambda Function URL (public, auth handled at application layer)
# =============================================================================
resource "aws_lambda_function_url" "proxy" {
  function_name      = aws_lambda_function.proxy.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST"]
    allow_headers = ["authorization", "content-type", "accept"]
  }
}

resource "aws_lambda_permission" "public_invoke" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.proxy.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
