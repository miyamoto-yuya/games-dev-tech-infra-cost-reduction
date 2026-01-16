variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "infra-cost-reduction"
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for analysis"
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

