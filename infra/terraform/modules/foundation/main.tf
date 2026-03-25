# =============================================================================
# Foundation Module - IAM, ECR, Secrets Manager
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
# ECR Repository
# =============================================================================
resource "aws_ecr_repository" "mcp_server" {
  name                 = "bedrock-agentcore-${var.project_name}-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(var.tags, {
    Name = "bedrock-agentcore-${var.project_name}-${var.environment}"
  })
}

resource "aws_ecr_lifecycle_policy" "mcp_server" {
  repository = aws_ecr_repository.mcp_server.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# =============================================================================
# Secrets Manager - API Keys
# =============================================================================
resource "aws_secretsmanager_secret" "api_keys" {
  name        = "mcp/${var.project_name}/api-keys"
  description = "API keys for MCP server"

  tags = merge(var.tags, {
    Name = "mcp-${var.project_name}-api-keys"
  })
}

resource "aws_secretsmanager_secret_version" "api_keys" {
  secret_id = aws_secretsmanager_secret.api_keys.id
  secret_string = jsonencode({
    SALESFORCE_INSTANCE_URL     = var.salesforce_instance_url
    SALESFORCE_LOGIN_URL        = var.salesforce_login_url
    SALESFORCE_CLIENT_ID        = var.salesforce_client_id
    SALESFORCE_CLIENT_SECRET    = var.salesforce_client_secret
    SALESFORCE_API_VERSION      = var.salesforce_api_version
    SALESFORCE_ACCESS_TOKEN_TTL = tostring(var.salesforce_access_token_ttl)
    MCP_JWT_SECRET              = var.mcp_jwt_secret
    MCP_BASE_URL                = var.mcp_base_url
  })
}

# =============================================================================
# IAM Role - AgentCore Execution Role
# Skipped when var.execution_role_arn is provided (reuse existing role).
# =============================================================================
locals {
  create_iam_roles = var.execution_role_arn == ""
}

data "aws_iam_policy_document" "agentcore_assume_role" {
  count = local.create_iam_roles ? 1 : 0

  statement {
    effect = "Allow"
    principals {
      type = "Service"
      identifiers = [
        "bedrock-agentcore.amazonaws.com",
        "ecs-tasks.amazonaws.com"
      ]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "agentcore_execution" {
  count = local.create_iam_roles ? 1 : 0

  name               = "AgentCoreExecutionRole-${var.project_name}-${var.environment}"
  description        = "Execution role for Bedrock AgentCore runtime"
  assume_role_policy = data.aws_iam_policy_document.agentcore_assume_role[0].json

  tags = merge(var.tags, {
    Name = "AgentCoreExecutionRole-${var.project_name}-${var.environment}"
  })
}

resource "aws_iam_role_policy_attachment" "agentcore_ecs_task" {
  count = local.create_iam_roles ? 1 : 0

  role       = aws_iam_role.agentcore_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "agentcore_cloudwatch" {
  count = local.create_iam_roles ? 1 : 0

  name = "CloudWatchLogsAccess"
  role = aws_iam_role.agentcore_execution[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/*",
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/*:*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "agentcore_secrets" {
  count = local.create_iam_roles ? 1 : 0

  name = "SecretsManagerAccess"
  role = aws_iam_role.agentcore_execution[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [aws_secretsmanager_secret.api_keys.arn]
      }
    ]
  })
}

resource "aws_iam_role_policy" "agentcore_ecr" {
  count = local.create_iam_roles ? 1 : 0

  name = "ECRAccess"
  role = aws_iam_role.agentcore_execution[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = [aws_ecr_repository.mcp_server.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      }
    ]
  })
}

# =============================================================================
# IAM Role - CodeBuild Role
# Skipped when using an existing execution role.
# =============================================================================
data "aws_iam_policy_document" "codebuild_assume_role" {
  count = local.create_iam_roles ? 1 : 0

  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "codebuild" {
  count = local.create_iam_roles ? 1 : 0

  name               = "CodeBuildRole-${var.project_name}-${var.environment}"
  description        = "Role for CodeBuild to build and push container images"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role[0].json

  tags = merge(var.tags, {
    Name = "CodeBuildRole-${var.project_name}-${var.environment}"
  })
}

resource "aws_iam_role_policy" "codebuild_logs" {
  count = local.create_iam_roles ? 1 : 0

  name = "CloudWatchLogsAccess"
  role = aws_iam_role.codebuild[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = ["arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/*"]
      }
    ]
  })
}

resource "aws_iam_role_policy" "codebuild_ecr" {
  count = local.create_iam_roles ? 1 : 0

  name = "ECRPushAccess"
  role = aws_iam_role.codebuild[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:TagResource"
        ]
        Resource = [aws_ecr_repository.mcp_server.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "codebuild_s3" {
  count = local.create_iam_roles ? 1 : 0

  name = "S3SourceAccess"
  role = aws_iam_role.codebuild[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.codebuild_source.arn,
          "${aws_s3_bucket.codebuild_source.arn}/*"
        ]
      }
    ]
  })
}

# =============================================================================
# S3 Bucket for CodeBuild Sources
# =============================================================================
resource "aws_s3_bucket" "codebuild_source" {
  bucket = "bedrock-agentcore-${var.project_name}-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, {
    Name = "bedrock-agentcore-${var.project_name}-codebuild"
  })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# =============================================================================
# Data Sources
# =============================================================================
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
