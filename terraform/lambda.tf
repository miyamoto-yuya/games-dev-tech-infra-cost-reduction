# Lambda関数用のCloudWatch Logsグループ
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}"
  retention_in_days = 7
}

# Lambda関数のZIPファイルを作成
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda_function"
  output_path = "${path.module}/lambda_function.zip"
}

# Lambda関数
resource "aws_lambda_function" "main" {
  filename         = data.archive_file.lambda.output_path
  function_name    = var.project_name
  role             = aws_iam_role.lambda_execution.arn
  handler          = "handler.lambda_handler"
  source_code_hash = data.archive_file.lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 300  # 5分（リソース取得に時間がかかる可能性があるため）
  memory_size      = 512

  environment {
    variables = {
      AWS_REGION_NAME   = var.aws_region
      BEDROCK_MODEL_ID  = var.bedrock_model_id
      MCP_RUNTIME_ARN   = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:runtime/infra_cost_reduction_pricing_mcp-M4Abq6BZRK"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.lambda_basic,
  ]
}

# Lambda Function URL（API Gatewayの代わりにシンプルな構成）
resource "aws_lambda_function_url" "main" {
  function_name      = aws_lambda_function.main.function_name
  authorization_type = "NONE"  # 認証なし（必要に応じてIAM認証に変更可能）

  cors {
    allow_credentials = false
    allow_origins     = ["*"]
    allow_methods     = ["*"]
    allow_headers     = ["Content-Type"]
    max_age           = 86400
  }
}

# パブリックアクセスを明示的に許可
resource "aws_lambda_permission" "function_url_public" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.main.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

