#!/bin/bash
# MCPサーバーをAgentCore Runtimeにデプロイするスクリプト

set -e

# 変数
REGION="${AWS_REGION:-ap-northeast-1}"
PROJECT_NAME="infra-cost-reduction"
RUNTIME_NAME="${PROJECT_NAME}-pricing-mcp"

# Terraformから値を取得
cd ../terraform
ECR_REPO_URL=$(terraform output -raw ecr_repository_url 2>/dev/null || echo "")
AGENTCORE_ROLE_ARN=$(terraform output -raw agentcore_role_arn 2>/dev/null || echo "")
cd ../mcp_server

if [ -z "$ECR_REPO_URL" ]; then
    echo "Error: ECR repository URL not found. Run 'terraform apply' first."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=== MCPサーバーデプロイ開始 ==="
echo "ECR Repository: $ECR_REPO_URL"
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo "Role ARN: $AGENTCORE_ROLE_ARN"

# Step 1: Dockerイメージをビルド
echo ""
echo "=== Step 1: Dockerイメージをビルド ==="
docker build -t ${RUNTIME_NAME}:latest .

# Step 2: ECRにログイン
echo ""
echo "=== Step 2: ECRにログイン ==="
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Step 3: イメージをタグ付け・プッシュ
echo ""
echo "=== Step 3: イメージをECRにプッシュ ==="
docker tag ${RUNTIME_NAME}:latest ${ECR_REPO_URL}:latest
docker push ${ECR_REPO_URL}:latest

# Step 4: AgentCore Runtimeにデプロイ
echo ""
echo "=== Step 4: AgentCore Runtimeにデプロイ ==="

# AgentCore Runtimeが存在するかチェック
EXISTING=$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-name "${RUNTIME_NAME}" \
    --region $REGION 2>/dev/null || echo "")

if [ -n "$EXISTING" ]; then
    echo "Updating existing Agent Runtime..."
    aws bedrock-agentcore-control update-agent-runtime \
        --agent-runtime-name "${RUNTIME_NAME}" \
        --agent-runtime-artifact "containerConfiguration={containerUri=${ECR_REPO_URL}:latest}" \
        --region $REGION
else
    echo "Creating new Agent Runtime..."
    aws bedrock-agentcore-control create-agent-runtime \
        --agent-runtime-name "${RUNTIME_NAME}" \
        --description "AWS Pricing MCP Server for cost optimization" \
        --role-arn "${AGENTCORE_ROLE_ARN}" \
        --agent-runtime-artifact "containerConfiguration={containerUri=${ECR_REPO_URL}:latest}" \
        --network-configuration "networkMode=PUBLIC" \
        --protocol-configuration "serverProtocol=MCP" \
        --region $REGION
fi

# Step 5: エンドポイントを作成（存在しない場合）
echo ""
echo "=== Step 5: エンドポイントを確認・作成 ==="

ENDPOINT_NAME="${RUNTIME_NAME}-endpoint"
EXISTING_ENDPOINT=$(aws bedrock-agentcore-control get-agent-runtime-endpoint \
    --agent-runtime-endpoint-name "${ENDPOINT_NAME}" \
    --region $REGION 2>/dev/null || echo "")

if [ -z "$EXISTING_ENDPOINT" ]; then
    echo "Creating Agent Runtime Endpoint..."
    aws bedrock-agentcore-control create-agent-runtime-endpoint \
        --agent-runtime-endpoint-name "${ENDPOINT_NAME}" \
        --agent-runtime-name "${RUNTIME_NAME}" \
        --description "Endpoint for AWS Pricing MCP Server" \
        --region $REGION
fi

# エンドポイントURLを取得
echo ""
echo "=== エンドポイント情報を取得 ==="
sleep 5  # 作成完了を待つ
ENDPOINT_INFO=$(aws bedrock-agentcore-control get-agent-runtime-endpoint \
    --agent-runtime-endpoint-name "${ENDPOINT_NAME}" \
    --region $REGION 2>/dev/null || echo "")

echo "$ENDPOINT_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Endpoint URL:', d.get('agentRuntimeEndpointUrl', 'Not ready yet'))" 2>/dev/null || echo "エンドポイント準備中..."

echo ""
echo "=== デプロイ完了 ==="
echo "Runtime Name: ${RUNTIME_NAME}"
echo "Endpoint Name: ${ENDPOINT_NAME}"
echo ""
echo "エンドポイントURLを確認:"
echo "aws bedrock-agentcore-control get-agent-runtime-endpoint --agent-runtime-endpoint-name ${ENDPOINT_NAME} --region $REGION"

