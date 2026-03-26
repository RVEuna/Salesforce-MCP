# =============================================================================
# Outputs
# =============================================================================

# Secrets Manager
output "secrets_arn" {
  description = "Secrets Manager secret ARN"
  value       = module.foundation.secrets_arn
}

# Lambda
output "function_name" {
  description = "Lambda function name"
  value       = module.mcp_server.function_name
}

output "function_url" {
  description = "Lambda function URL (public endpoint)"
  value       = module.mcp_server.function_url
}

output "mcp_server_url" {
  description = "MCP server URL for client configuration"
  value       = module.mcp_server.mcp_server_url
}

output "lambda_role_arn" {
  description = "IAM role ARN for the Lambda"
  value       = module.mcp_server.role_arn
}
