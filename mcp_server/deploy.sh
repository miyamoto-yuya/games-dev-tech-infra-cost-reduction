#!/bin/bash
set -e

REGION="ap-northeast-1"
REPO_NAME="infra-cost-reduction-mcp-server"

echo "=== MCP Server Deploy Script ==="

# AWSアカウントID取得
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$ACCOUNT_ID" ]; then
    echo "ERROR: AWS認証情報が設定されていません"
    echo "aws sso login または aws configure を実行してください"
    exit 1
fi

ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"
echo "ECR URL: ${ECR_URL}"

# ECRログイン
echo ""
echo "=== ECRログイン ==="
aws ecr get-login-password --region ${REGION} | \
    docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# ARM64でビルド
echo ""
echo "=== Docker Build (ARM64) ==="
docker buildx build --platform linux/arm64 -t ${REPO_NAME}:latest .

# タグ付け
echo ""
echo "=== Docker Tag ==="
docker tag ${REPO_NAME}:latest ${ECR_URL}:latest

# プッシュ
echo ""
echo "=== Docker Push ==="
docker push ${ECR_URL}:latest

echo ""
echo "=== 完了 ==="
echo "ECRイメージ: ${ECR_URL}:latest"
echo ""
echo "次のステップ:"
echo "  AWSコンソール → Bedrock → AgentCore で Runtime を更新してください"
