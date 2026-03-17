# =============================================================================
# OpenSearch Module - Managed Domain with k-NN
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
# CloudWatch Log Groups
# =============================================================================
resource "aws_cloudwatch_log_group" "opensearch_app" {
  name              = "/aws/opensearch/${var.domain_name}-${var.environment}/app-logs"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name = "opensearch-${var.domain_name}-app-logs"
  })
}

resource "aws_cloudwatch_log_group" "opensearch_slow" {
  name              = "/aws/opensearch/${var.domain_name}-${var.environment}/slow-logs"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name = "opensearch-${var.domain_name}-slow-logs"
  })
}

resource "aws_cloudwatch_log_resource_policy" "opensearch" {
  policy_name = "OpenSearchLogPolicy-${var.domain_name}-${var.environment}"

  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "es.amazonaws.com"
        }
        Action = [
          "logs:PutLogEvents",
          "logs:CreateLogStream"
        ]
        Resource = [
          "${aws_cloudwatch_log_group.opensearch_app.arn}:*",
          "${aws_cloudwatch_log_group.opensearch_slow.arn}:*"
        ]
      }
    ]
  })
}

# =============================================================================
# OpenSearch Domain
# =============================================================================
resource "aws_opensearch_domain" "main" {
  domain_name    = "${var.domain_name}-${var.environment}"
  engine_version = var.engine_version

  cluster_config {
    instance_type            = var.instance_type
    instance_count           = var.instance_count
    zone_awareness_enabled   = var.instance_count > 1

    dynamic "zone_awareness_config" {
      for_each = var.instance_count > 1 ? [1] : []
      content {
        availability_zone_count = min(var.instance_count, 3)
      }
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.volume_size
    iops        = 3000
    throughput  = 125
  }

  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = true

    master_user_options {
      master_user_name     = var.master_user_name
      master_user_password = var.master_user_password
    }
  }

  node_to_node_encryption {
    enabled = true
  }

  encrypt_at_rest {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  log_publishing_options {
    log_type                 = "ES_APPLICATION_LOGS"
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_app.arn
    enabled                  = true
  }

  log_publishing_options {
    log_type                 = "SEARCH_SLOW_LOGS"
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_slow.arn
    enabled                  = true
  }

  tags = merge(var.tags, {
    Name = "${var.domain_name}-${var.environment}"
  })

  depends_on = [aws_cloudwatch_log_resource_policy.opensearch]
}

# =============================================================================
# Access Policy
# =============================================================================
resource "aws_opensearch_domain_policy" "main" {
  domain_name = aws_opensearch_domain.main.domain_name

  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = var.agentcore_execution_role_arn
        }
        Action   = ["es:ESHttp*"]
        Resource = "${aws_opensearch_domain.main.arn}/*"
      },
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = ["es:ESHttp*"]
        Resource = "${aws_opensearch_domain.main.arn}/*"
      }
    ]
  })
}

# =============================================================================
# Data Sources
# =============================================================================
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
