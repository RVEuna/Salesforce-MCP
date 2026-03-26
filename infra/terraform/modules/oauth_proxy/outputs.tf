output "function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.mcp_server.function_name
}

output "function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.mcp_server.arn
}

output "function_url" {
  description = "Lambda function URL (public endpoint)"
  value       = aws_lambda_function_url.mcp_server.function_url
}

output "mcp_server_url" {
  description = "MCP server URL for client configuration (function URL + /mcp)"
  value       = "${aws_lambda_function_url.mcp_server.function_url}mcp"
}

output "role_arn" {
  description = "IAM role ARN for the Lambda"
  value       = aws_iam_role.lambda.arn
}
