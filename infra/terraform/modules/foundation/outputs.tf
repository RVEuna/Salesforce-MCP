output "secrets_arn" {
  description = "Secrets Manager secret ARN"
  value       = aws_secretsmanager_secret.api_keys.arn
}

output "secrets_name" {
  description = "Secrets Manager secret name"
  value       = aws_secretsmanager_secret.api_keys.name
}
