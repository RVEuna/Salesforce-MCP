# =============================================================================
# AgentCore Module - Runtime and CodeBuild
# =============================================================================
#
# Note: Uses null_resource with AWS CLI since Terraform AWS provider doesn't
# yet have native AgentCore support.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0"
    }
  }
}

# =============================================================================
# CloudWatch Log Group
# =============================================================================
resource "aws_cloudwatch_log_group" "agentcore" {
  name              = "/aws/bedrock-agentcore/${var.agent_runtime_name}-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name = "agentcore-${var.agent_runtime_name}-${var.environment}"
  })
}

# =============================================================================
# AgentCore Runtime (via AWS CLI)
# =============================================================================

locals {
  # AgentCore runtime names only allow [a-zA-Z][a-zA-Z0-9_]{0,47} — no hyphens
  runtime_name_safe = replace("${var.agent_runtime_name}_${var.environment}", "-", "_")

  runtime_config_hash = sha256(jsonencode({
    name          = local.runtime_name_safe
    container_uri = "${var.ecr_repository_url}:${var.container_image_tag}"
    role_arn      = var.execution_role_arn
  }))

  codebuild_env_type = var.container_architecture == "ARM" ? "ARM_CONTAINER" : "LINUX_CONTAINER"
  codebuild_image    = var.container_architecture == "ARM" ? "aws/codebuild/amazonlinux2-aarch64-standard:3.0" : "aws/codebuild/amazonlinux2-x86_64-standard:5.0"

  default_buildspec = <<-EOT
    version: 0.2
    phases:
      pre_build:
        commands:
          - echo Logging in to Amazon ECR...
          - aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
      build:
        commands:
          - echo Build started on `date`
          - docker build -t $ECR_REPOSITORY_URI:$IMAGE_TAG .
          - docker tag $ECR_REPOSITORY_URI:$IMAGE_TAG $ECR_REPOSITORY_URI:latest
      post_build:
        commands:
          - echo Pushing the Docker image...
          - docker push $ECR_REPOSITORY_URI:$IMAGE_TAG
          - docker push $ECR_REPOSITORY_URI:latest
  EOT
}

resource "null_resource" "agentcore_runtime" {
  provisioner "local-exec" {
    interpreter = ["PowerShell", "-Command"]
    command     = <<-EOT
      Write-Host "Creating/Updating AgentCore Runtime..."
      Set-Content -Path "agentcore_artifact.json" -Value '{"containerConfiguration":{"containerUri":"${var.ecr_repository_url}:${var.container_image_tag}"}}'
      Set-Content -Path "agentcore_network.json" -Value '{"networkMode":"${var.network_mode}"}'
      $existing = (aws bedrock-agentcore-control list-agent-runtimes --region ${data.aws_region.current.region} --query "agentRuntimes[?agentRuntimeName=='${local.runtime_name_safe}'].agentRuntimeId" --output text 2>$null)
      if ([string]::IsNullOrEmpty($existing) -or $existing -eq "None") {
        Write-Host "Creating new AgentCore Runtime..."
        aws bedrock-agentcore-control create-agent-runtime --region ${data.aws_region.current.region} --agent-runtime-name "${local.runtime_name_safe}" --agent-runtime-artifact file://agentcore_artifact.json --network-configuration file://agentcore_network.json --role-arn "${var.execution_role_arn}"
      } else {
        Write-Host "Updating existing AgentCore Runtime: $existing"
        aws bedrock-agentcore-control update-agent-runtime --region ${data.aws_region.current.region} --agent-runtime-id "$existing" --agent-runtime-artifact file://agentcore_artifact.json --network-configuration file://agentcore_network.json --role-arn "${var.execution_role_arn}"
      }
      Remove-Item -Path "agentcore_artifact.json" -ErrorAction SilentlyContinue
      Remove-Item -Path "agentcore_network.json" -ErrorAction SilentlyContinue
    EOT
  }

  provisioner "local-exec" {
    when        = destroy
    interpreter = ["PowerShell", "-Command"]
    command     = <<-EOT
      Write-Host "Deleting AgentCore Runtime..."
      $runtimeId = (aws bedrock-agentcore-control list-agent-runtimes --region ${self.triggers.region} --query "agentRuntimes[?agentRuntimeName=='${self.triggers.runtime_name}'].agentRuntimeId" --output text 2>$null)
      if (-not [string]::IsNullOrEmpty($runtimeId) -and $runtimeId -ne "None") {
        aws bedrock-agentcore-control delete-agent-runtime --region ${self.triggers.region} --agent-runtime-id "$runtimeId"
      }
    EOT
  }

  triggers = {
    config_hash  = local.runtime_config_hash
    region       = data.aws_region.current.region
    runtime_name = local.runtime_name_safe
  }
}

data "external" "agentcore_runtime_info" {
  depends_on = [null_resource.agentcore_runtime]

  program = ["bash", "-c", <<-EOT
    RUNTIME=$(aws bedrock-agentcore-control list-agent-runtimes \
      --region ${data.aws_region.current.region} \
      --query "agentRuntimes[?agentRuntimeName=='${local.runtime_name_safe}'] | [0]" \
      --output json 2>/dev/null || echo '{}')

    if [ "$RUNTIME" = "null" ] || [ -z "$RUNTIME" ] || [ "$RUNTIME" = "{}" ]; then
      echo '{"runtime_id":"pending","runtime_arn":"pending","status":"CREATING"}'
    else
      RUNTIME_ID=$(echo "$RUNTIME" | jq -r '.agentRuntimeId // "pending"')
      RUNTIME_ARN=$(echo "$RUNTIME" | jq -r '.agentRuntimeArn // "pending"')
      STATUS=$(echo "$RUNTIME" | jq -r '.agentRuntimeStatus // "UNKNOWN"')
      echo "{\"runtime_id\":\"$RUNTIME_ID\",\"runtime_arn\":\"$RUNTIME_ARN\",\"status\":\"$STATUS\"}"
    fi
  EOT
  ]
}

# =============================================================================
# CodeBuild Project
# =============================================================================
resource "aws_codebuild_project" "container_builder" {
  count = var.create_codebuild ? 1 : 0

  name          = "bedrock-agentcore-${var.project_name}-${var.environment}-builder"
  description   = "Build container images for AgentCore runtime"
  service_role  = var.codebuild_role_arn
  build_timeout = 30

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    type                        = local.codebuild_env_type
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = local.codebuild_image
    privileged_mode             = true
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "ECR_REPOSITORY_URI"
      value = var.ecr_repository_url
    }

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    }

    environment_variable {
      name  = "AWS_REGION"
      value = data.aws_region.current.name
    }

    environment_variable {
      name  = "IMAGE_TAG"
      value = var.container_image_tag
    }
  }

  source {
    type     = "S3"
    location = "${var.codebuild_source_bucket}/source.zip"

    buildspec = local.default_buildspec
  }

  tags = merge(var.tags, {
    Name = "bedrock-agentcore-${var.project_name}-${var.environment}-builder"
  })
}

# =============================================================================
# Data Sources
# =============================================================================
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
