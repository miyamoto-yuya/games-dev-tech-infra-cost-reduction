# Lambda実行ロール
resource "aws_iam_role" "lambda_execution" {
  name = "${var.project_name}-lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# CloudWatch Logs書き込み権限
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda関数に必要なAWSリソースアクセス権限
resource "aws_iam_role_policy" "lambda_resources" {
  name = "${var.project_name}-lambda-resources-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          # EC2関連
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          # RDS関連
          "rds:DescribeDBClusters",
          "rds:DescribeDBInstances",
          # DocumentDB関連
          "docdb:DescribeDBClusters",
          "docdb:DescribeDBInstances",
          # ElastiCache関連
          "elasticache:DescribeReplicationGroups",
          "elasticache:DescribeCacheClusters",
          # CloudWatch関連
          "cloudwatch:GetMetricStatistics"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          # Bedrock関連
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:*:inference-profile/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          # AWS Marketplace（Bedrockモデル初回有効化に必要）
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe",
          "aws-marketplace:Unsubscribe"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          # AgentCore MCP Server呼び出し
          "bedrock-agentcore:InvokeAgentRuntime",
          "bedrock-agentcore:GetAgentCard"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          # AWS Pricing API（Lambda内で直接呼び出す場合のフォールバック）
          "pricing:GetProducts",
          "pricing:DescribeServices",
          "pricing:GetAttributeValues"
        ]
        Resource = "*"
      }
    ]
  })
}
