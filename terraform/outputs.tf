# Lambda Function URL（ブラウザでアクセスするURL）
output "lambda_function_url" {
  description = "Lambda Function URL - Access this URL in your browser"
  value       = aws_lambda_function_url.main.function_url
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.main.function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.main.arn
}
