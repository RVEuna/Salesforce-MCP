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
  count     = var.api_key != "" ? 1 : 0
  secret_id = aws_secretsmanager_secret.api_keys.id
  secret_string = jsonencode({
    api_key = var.api_key
  })
}

# =============================================================================
# IAM Role - AgentCore Execution Role
# =============================================================================
data "aws_iam_policy_document" "agentcore_assume_role" {
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
  name               = "AgentCoreExecutionRole-${var.project_name}-${var.environment}"
  description        = "Execution role for Bedrock AgentCore runtime"
  assume_role_policy = data.aws_iam_policy_document.agentcore_assume_role.json

  tags = merge(var.tags, {
    Name = "AgentCoreExecutionRole-${var.project_name}-${var.environment}"
  })
}

resource "aws_iam_role_policy_attachment" "agentcore_ecs_task" {
  role       = aws_iam_role.agentcore_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# CloudWatch Logs Policy
resource "aws_iam_role_policy" "agentcore_cloudwatch" {
  name = "CloudWatchLogsAccess"
  role = aws_iam_role.agentcore_execution.id

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

# Secrets Manager Policy
resource "aws_iam_role_policy" "agentcore_secrets" {
  name = "SecretsManagerAccess"
  role = aws_iam_role.agentcore_execution.id

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

# ECR Policy
resource "aws_iam_role_policy" "agentcore_ecr" {
  name = "ECRAccess"
  role = aws_iam_role.agentcore_execution.id

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
# =============================================================================
data "aws_iam_policy_document" "codebuild_assume_role" {
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
  name               = "CodeBuildRole-${var.project_name}-${var.environment}"
  description        = "Role for CodeBuild to build and push container images"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json

  tags = merge(var.tags, {
    Name = "CodeBuildRole-${var.project_name}-${var.environment}"
  })
}

resource "aws_iam_role_policy" "codebuild_logs" {
  name = "CloudWatchLogsAccess"
  role = aws_iam_role.codebuild.id

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
  name = "ECRPushAccess"
  role = aws_iam_role.codebuild.id

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
  name = "S3SourceAccess"
  role = aws_iam_role.codebuild.id

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
