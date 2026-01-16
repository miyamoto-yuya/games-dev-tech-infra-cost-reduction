# AgentCore Runtime - AWS Pricing MCP Server

# ECRリポジトリ（MCPサーバーのDockerイメージ用）
resource "aws_ecr_repository" "mcp_server" {
  name                 = "${var.project_name}-mcp-server"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# AgentCore用IAMロール
resource "aws_iam_role" "agentcore_execution" {
  name = "${var.project_name}-agentcore-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "bedrock-agentcore.amazonaws.com"
        }
      }
    ]
  })
}

# AgentCore用IAMポリシー
resource "aws_iam_role_policy" "agentcore_policy" {
  name = "${var.project_name}-agentcore-policy"
  role = aws_iam_role.agentcore_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          # ECRアクセス
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = aws_ecr_repository.mcp_server.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          # AWS Pricing API
          "pricing:GetProducts",
          "pricing:DescribeServices",
          "pricing:GetAttributeValues"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          # CloudWatch Logs
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/agentcore/*"
      }
    ]
  })
}

# Cognito User Pool（MCP認証用）
resource "aws_cognito_user_pool" "mcp_auth" {
  name = "${var.project_name}-mcp-auth"

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

# Cognito User Pool Client
resource "aws_cognito_user_pool_client" "mcp_client" {
  name         = "${var.project_name}-mcp-client"
  user_pool_id = aws_cognito_user_pool.mcp_auth.id

  generate_secret = true

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  supported_identity_providers = ["COGNITO"]

  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["aws-pricing-mcp/read"]

  depends_on = [aws_cognito_resource_server.mcp_resource]
}

# Cognito Resource Server（OAuth2スコープ定義）
resource "aws_cognito_resource_server" "mcp_resource" {
  identifier   = "aws-pricing-mcp"
  name         = "AWS Pricing MCP Server"
  user_pool_id = aws_cognito_user_pool.mcp_auth.id

  scope {
    scope_name        = "read"
    scope_description = "Read access to AWS Pricing MCP Server"
  }
}

# Cognito Domain
resource "aws_cognito_user_pool_domain" "mcp_domain" {
  domain       = "${var.project_name}-mcp-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.mcp_auth.id
}

# 現在のAWSアカウントID取得
data "aws_caller_identity" "current" {}

# 出力
output "ecr_repository_url" {
  description = "ECR repository URL for MCP server"
  value       = aws_ecr_repository.mcp_server.repository_url
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.mcp_auth.id
}

output "cognito_client_id" {
  description = "Cognito Client ID"
  value       = aws_cognito_user_pool_client.mcp_client.id
}

output "cognito_domain" {
  description = "Cognito Domain"
  value       = "https://${aws_cognito_user_pool_domain.mcp_domain.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "agentcore_role_arn" {
  description = "AgentCore execution role ARN"
  value       = aws_iam_role.agentcore_execution.arn
}

