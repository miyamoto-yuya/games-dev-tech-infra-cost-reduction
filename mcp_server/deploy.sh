#!/bin/bash
set -e

# 設定
REGION="ap-northeast-1"
REPO_NAME="infra-cost-reduction-mcp-server"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"

echo "=== MCP Server Deploy Script (Official SDK) ==="
echo ""

# AWSアカウントID取得
echo "=== AWS認証確認 ==="
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ -z "$ACCOUNT_ID" ]; then
    echo "ERROR: AWS認証情報が設定されていません"
    echo "aws sso login または aws configure を実行してください"
    exit 1
fi
echo "Account ID: ${ACCOUNT_ID}"

# Terraformから出力を取得（可能な場合）
if [ -d "$TERRAFORM_DIR" ] && command -v terraform &> /dev/null; then
    echo ""
    echo "=== Terraform出力を取得 ==="
    cd "$TERRAFORM_DIR"
    
    # ECR URL取得を試行
    TF_ECR_URL=$(terraform output -raw ecr_repository_url 2>/dev/null || echo "")
    if [ -n "$TF_ECR_URL" ]; then
        ECR_URL="$TF_ECR_URL"
        echo "ECR URL (from Terraform): ${ECR_URL}"
    else
        ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"
        echo "ECR URL (fallback): ${ECR_URL}"
    fi
    
    # Role ARN取得を試行
    ROLE_ARN=$(terraform output -raw agentcore_role_arn 2>/dev/null || echo "")
    if [ -n "$ROLE_ARN" ]; then
        echo "Role ARN: ${ROLE_ARN}"
    fi
    
    cd "$SCRIPT_DIR"
else
    ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"
    echo "ECR URL: ${ECR_URL}"
fi

# ECRログイン
echo ""
echo "=== ECRログイン ==="
aws ecr get-login-password --region ${REGION} | \
    docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Docker Build
echo ""
echo "=== Docker Build (ARM64 for AgentCore) ==="
cd "$SCRIPT_DIR"

# server.pyにビルド時刻を追記してキャッシュを無効化（pip installはキャッシュを使用）
BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "# Build: ${BUILD_TIME}" >> server.py

# buildxが利用可能か確認
if docker buildx version &> /dev/null; then
    docker buildx build --platform linux/arm64 -t ${REPO_NAME}:latest --load .
else
    echo "Warning: docker buildx not available, using standard build"
    docker build -t ${REPO_NAME}:latest .
fi

# server.pyから追記した行を削除
sed -i '$ d' server.py

# ビルド確認
echo ""
echo "=== ビルド確認 ==="
docker images ${REPO_NAME}:latest --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

# タグ付け
echo ""
echo "=== Docker Tag ==="
docker tag ${REPO_NAME}:latest ${ECR_URL}:latest

# プッシュ
echo ""
echo "=== Docker Push ==="
docker push ${ECR_URL}:latest

# 完了
echo ""
echo "=========================================="
echo "✅ デプロイ完了!"
echo "=========================================="
echo ""
echo "ECRイメージ: ${ECR_URL}:latest"
echo ""

# AgentCore Runtime 作成/更新コマンドを表示
echo "=== 次のステップ ==="
echo ""
echo "【新規作成の場合】"
if [ -n "$ROLE_ARN" ]; then
    echo "aws bedrock-agentcore create-agent-runtime \\"
    echo "  --name \"aws-pricing-mcp-runtime\" \\"
    echo "  --execution-role-arn \"${ROLE_ARN}\" \\"
    echo "  --container-config '{\"imageUri\": \"${ECR_URL}:latest\", \"port\": 8000}' \\"
    echo "  --region ${REGION}"
else
    echo "aws bedrock-agentcore create-agent-runtime \\"
    echo "  --name \"aws-pricing-mcp-runtime\" \\"
    echo "  --execution-role-arn \"<ROLE_ARN>\" \\"
    echo "  --container-config '{\"imageUri\": \"${ECR_URL}:latest\", \"port\": 8000}' \\"
    echo "  --region ${REGION}"
fi
echo ""
echo "【既存Runtimeを更新する場合】"
echo "aws bedrock-agentcore update-agent-runtime \\"
echo "  --agent-runtime-id \"<RUNTIME_ID>\" \\"
echo "  --container-config '{\"imageUri\": \"${ECR_URL}:latest\", \"port\": 8000}' \\"
echo "  --region ${REGION}"
echo ""
