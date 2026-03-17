# =============================================================================
# Monitoring Module - CloudWatch Dashboards and Alarms
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
# SNS Topic for Alarms
# =============================================================================
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-${var.environment}-alerts"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-alerts"
  })
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# =============================================================================
# CloudWatch Alarms
# =============================================================================

# OpenSearch cluster health
resource "aws_cloudwatch_metric_alarm" "opensearch_cluster_red" {
  alarm_name          = "${var.project_name}-${var.environment}-opensearch-cluster-red"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ClusterStatus.red"
  namespace           = "AWS/ES"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "OpenSearch cluster status is RED"

  dimensions = {
    DomainName = var.opensearch_domain_name
    ClientId   = data.aws_caller_identity.current.account_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

# OpenSearch free storage space
resource "aws_cloudwatch_metric_alarm" "opensearch_free_storage" {
  alarm_name          = "${var.project_name}-${var.environment}-opensearch-low-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/ES"
  period              = 300
  statistic           = "Minimum"
  threshold           = 10000  # 10 GB in MB
  alarm_description   = "OpenSearch free storage space is low"

  dimensions = {
    DomainName = var.opensearch_domain_name
    ClientId   = data.aws_caller_identity.current.account_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = var.tags
}

# =============================================================================
# CloudWatch Dashboard
# =============================================================================
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 1
        properties = {
          markdown = "# ${var.project_name} - ${var.environment} Dashboard"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 1
        width  = 12
        height = 6
        properties = {
          title  = "OpenSearch Cluster Health"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/ES", "ClusterStatus.green", "DomainName", var.opensearch_domain_name, "ClientId", data.aws_caller_identity.current.account_id, { color = "#2ca02c" }],
            [".", "ClusterStatus.yellow", ".", ".", ".", ".", { color = "#ffbb00" }],
            [".", "ClusterStatus.red", ".", ".", ".", ".", { color = "#d62728" }]
          ]
          view    = "timeSeries"
          stacked = false
          period  = 60
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 1
        width  = 12
        height = 6
        properties = {
          title  = "OpenSearch Search Latency"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/ES", "SearchLatency", "DomainName", var.opensearch_domain_name, "ClientId", data.aws_caller_identity.current.account_id]
          ]
          view    = "timeSeries"
          stacked = false
          period  = 60
          stat    = "Average"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 7
        width  = 12
        height = 6
        properties = {
          title  = "OpenSearch CPU Utilization"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/ES", "CPUUtilization", "DomainName", var.opensearch_domain_name, "ClientId", data.aws_caller_identity.current.account_id]
          ]
          view    = "timeSeries"
          stacked = false
          period  = 60
          stat    = "Average"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 7
        width  = 12
        height = 6
        properties = {
          title  = "OpenSearch Free Storage Space"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/ES", "FreeStorageSpace", "DomainName", var.opensearch_domain_name, "ClientId", data.aws_caller_identity.current.account_id]
          ]
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Minimum"
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 13
        width  = 24
        height = 6
        properties = {
          title  = "AgentCore Logs"
          region = data.aws_region.current.name
          query  = "SOURCE '/aws/bedrock-agentcore/${var.agentcore_runtime_name}' | fields @timestamp, @message | sort @timestamp desc | limit 100"
        }
      }
    ]
  })
}

# =============================================================================
# Data Sources
# =============================================================================
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
