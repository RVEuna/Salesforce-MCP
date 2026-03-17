output "runtime_id" {
  description = "AgentCore runtime ID"
  value       = data.external.agentcore_runtime_info.result.runtime_id
}

output "runtime_arn" {
  description = "AgentCore runtime ARN"
  value       = data.external.agentcore_runtime_info.result.runtime_arn
}

output "runtime_status" {
  description = "AgentCore runtime status"
  value       = data.external.agentcore_runtime_info.result.status
}

output "codebuild_project_name" {
  description = "CodeBuild project name"
  value       = aws_codebuild_project.container_builder.name
}

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.agentcore.name
}
