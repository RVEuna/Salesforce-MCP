output "domain_name" {
  description = "OpenSearch domain name"
  value       = aws_opensearch_domain.main.domain_name
}

output "domain_arn" {
  description = "OpenSearch domain ARN"
  value       = aws_opensearch_domain.main.arn
}

output "endpoint" {
  description = "OpenSearch domain endpoint"
  value       = "https://${aws_opensearch_domain.main.endpoint}"
}

output "dashboard_url" {
  description = "OpenSearch Dashboards URL"
  value       = "https://${aws_opensearch_domain.main.dashboard_endpoint}/_dashboards"
}
