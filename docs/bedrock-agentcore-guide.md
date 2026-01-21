# AWS Bedrock AgentCore 技術ガイド

## 1. 概要

### 1.1 Bedrock AgentCore とは

**AWS Bedrock AgentCore** は、MCP (Model Context Protocol) サーバーをサーバーレスでホスティングするためのフルマネージドサービスです。

| 項目 | 説明 |
|------|------|
| **サービス名** | Amazon Bedrock AgentCore Runtime |
| **リージョン** | ap-northeast-1 (東京) 等 |
| **プロトコル** | MCP (Model Context Protocol) |
| **通信形式** | JSON-RPC 2.0 over HTTP |
| **ステータス** | 2024年12月 GA (一般提供) |

### 1.2 MCP (Model Context Protocol) とは

MCP は Anthropic が策定した、AI エージェントがツール（外部機能）を呼び出すためのオープンプロトコルです。

```
┌─────────────────┐     JSON-RPC      ┌─────────────────┐
│   AI Agent      │ ◄───────────────► │   MCP Server    │
│  (Bedrock等)    │   tools/call      │  (価格取得等)    │
└─────────────────┘                   └─────────────────┘
```

**主なメソッド:**
- `initialize` - サーバー初期化
- `tools/list` - 利用可能なツール一覧取得
- `tools/call` - ツール実行

---

## 2. アーキテクチャ

### 2.1 システム構成図

```
┌─────────────────────────────────────────────────────────────────────┐
│                          AWS Cloud                                   │
│                                                                      │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │              │    │                  │    │                  │  │
│  │   Lambda     │───►│  Bedrock         │───►│   MCP Server     │  │
│  │  (handler)   │    │  AgentCore       │    │   (Docker/ECR)   │  │
│  │              │    │  Runtime         │    │                  │  │
│  └──────────────┘    └──────────────────┘    └──────────────────┘  │
│         │                    │                        │             │
│         │                    │                        │             │
│         ▼                    ▼                        ▼             │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │   Bedrock    │    │    Cognito       │    │   AWS Pricing    │  │
│  │  (Nova Lite) │    │   (認証)         │    │      API         │  │
│  └──────────────┘    └──────────────────┘    └──────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 コンポーネント詳細

| コンポーネント | 役割 | 技術 |
|--------------|------|------|
| **Lambda** | メインロジック、UI提供 | Python 3.11 |
| **AgentCore Runtime** | MCPサーバーのホスティング | サーバーレス |
| **MCP Server** | 価格情報取得ツール提供 | Python, Docker |
| **ECR** | MCPサーバーのコンテナイメージ保存 | Docker Registry |
| **Cognito** | MCP認証 | OAuth2 |
| **Bedrock** | AI分析 | Nova Lite |

---

## 3. MCP サーバー実装

### 3.1 提供ツール

本システムの MCP サーバーは以下の 3 つのツールを提供します：

#### ① get_instance_price
インスタンスの時間単価を取得

```json
{
  "name": "get_instance_price",
  "inputSchema": {
    "properties": {
      "instance_type": { "type": "string", "description": "t3.medium 等" },
      "region": { "type": "string", "default": "ap-northeast-1" },
      "service": { "type": "string", "default": "ec2" }
    },
    "required": ["instance_type"]
  }
}
```

**レスポンス例:**
```json
{
  "instance_type": "t3.medium",
  "region": "ap-northeast-1",
  "hourly_price_usd": 0.0416,
  "monthly_cost_usd": 29.95
}
```

#### ② find_cheaper_alternatives
より安い代替インスタンスを検索

```json
{
  "name": "find_cheaper_alternatives",
  "inputSchema": {
    "properties": {
      "instance_type": { "type": "string" },
      "region": { "type": "string", "default": "ap-northeast-1" },
      "service": { "type": "string", "default": "ec2" }
    },
    "required": ["instance_type"]
  }
}
```

**レスポンス例:**
```json
{
  "current": { "instance_type": "t3.medium", "hourly_price_usd": 0.0416 },
  "alternatives": [
    { "instance_type": "t4g.medium", "hourly_price_usd": 0.0336, "savings_percent": 19.2 },
    { "instance_type": "t3a.medium", "hourly_price_usd": 0.0376, "savings_percent": 9.6 }
  ]
}
```

#### ③ calculate_monthly_savings
インスタンス変更による月額削減額を計算

```json
{
  "name": "calculate_monthly_savings",
  "inputSchema": {
    "properties": {
      "current_type": { "type": "string" },
      "proposed_type": { "type": "string" },
      "count": { "type": "integer", "default": 1 },
      "region": { "type": "string", "default": "ap-northeast-1" }
    },
    "required": ["current_type", "proposed_type"]
  }
}
```

### 3.2 対応サービス

| サービス | プレフィックス | 例 |
|---------|--------------|-----|
| EC2 | なし | t3.medium, m5.large |
| RDS | db. | db.t3.medium, db.r5.large |
| ElastiCache | cache. | cache.t3.medium, cache.r6g.large |
| DocumentDB | db. | db.r5.large |

### 3.3 価格取得ロジック

```
┌─────────────────────────────────────────────────────────────┐
│                    価格取得フロー                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. AWS Pricing API を呼び出し                              │
│     └─ リージョン: us-east-1 (Pricing API の制約)           │
│                                                             │
│  2. 成功した場合                                            │
│     └─ OnDemand 価格を返却                                  │
│                                                             │
│  3. 失敗した場合                                            │
│     └─ フォールバック価格テーブルから返却                    │
│                                                             │
│  4. キャッシュ (lru_cache)                                  │
│     └─ 同一インスタンスタイプは再取得しない                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Lambda からの呼び出し方法

### 4.1 Boto3 クライアント

```python
import boto3
import json
import uuid

def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """MCP サーバーのツールを呼び出す"""
    client = boto3.client('bedrock-agentcore', region_name='ap-northeast-1')
    
    # JSON-RPC リクエスト
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": 1
    })
    
    response = client.invoke_agent_runtime(
        agentRuntimeArn="arn:aws:bedrock-agentcore:ap-northeast-1:ACCOUNT:runtime/RUNTIME_ID",
        runtimeSessionId=str(uuid.uuid4()),
        mcpSessionId=str(uuid.uuid4()),
        mcpProtocolVersion="2024-11-05",
        contentType="application/json",
        accept="application/json, text/event-stream",
        payload=payload.encode('utf-8')
    )
    
    # ストリーミングレスポンスを結合
    content = []
    for chunk in response.get("response", []):
        content.append(chunk.decode('utf-8'))
    result = json.loads(''.join(content))
    
    return json.loads(result["result"]["content"][0]["text"])
```

### 4.2 使用例

```python
# 価格取得
price_info = call_mcp_tool("get_instance_price", {
    "instance_type": "t3.medium",
    "service": "ec2",
    "region": "ap-northeast-1"
})
print(f"時間単価: ${price_info['hourly_price_usd']}")

# 代替インスタンス検索
alternatives = call_mcp_tool("find_cheaper_alternatives", {
    "instance_type": "t3.medium"
})
for alt in alternatives['alternatives']:
    print(f"{alt['instance_type']}: {alt['savings_percent']}% 削減")
```

---

## 5. インフラ構成 (Terraform)

### 5.1 必要なリソース

```hcl
# 1. ECRリポジトリ（MCPサーバーのDockerイメージ用）
resource "aws_ecr_repository" "mcp_server" {
  name                 = "infra-cost-reduction-mcp-server"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

# 2. AgentCore用IAMロール
resource "aws_iam_role" "agentcore_execution" {
  name = "infra-cost-reduction-agentcore-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "bedrock-agentcore.amazonaws.com"
      }
    }]
  })
}

# 3. IAMポリシー（ECR + Pricing API + CloudWatch Logs）
resource "aws_iam_role_policy" "agentcore_policy" {
  name = "infra-cost-reduction-agentcore-policy"
  role = aws_iam_role.agentcore_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = aws_ecr_repository.mcp_server.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "pricing:GetProducts",
          "pricing:DescribeServices",
          "pricing:GetAttributeValues"
        ]
        Resource = "*"
      }
    ]
  })
}

# 4. Cognito（MCP認証用）
resource "aws_cognito_user_pool" "mcp_auth" {
  name = "infra-cost-reduction-mcp-auth"
}
```

### 5.2 AgentCore Runtime の作成

AgentCore Runtime は現時点で AWS コンソールまたは CLI で作成する必要があります：

```bash
# AWS CLI での Runtime 作成
aws bedrock-agentcore create-agent-runtime \
  --name "infra_cost_reduction_pricing_mcp" \
  --execution-role-arn "arn:aws:iam::ACCOUNT:role/infra-cost-reduction-agentcore-execution-role" \
  --container-config '{
    "imageUri": "ACCOUNT.dkr.ecr.ap-northeast-1.amazonaws.com/infra-cost-reduction-mcp-server:latest",
    "port": 8000
  }' \
  --region ap-northeast-1
```

---

## 6. Docker イメージ

### 6.1 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 依存関係インストール
RUN pip install --no-cache-dir boto3

# MCPサーバーコード
COPY server.py .

# ポート公開
EXPOSE 8000

# 起動コマンド
CMD ["python", "server.py"]
```

### 6.2 ビルド & プッシュ

```bash
# ECR ログイン
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.ap-northeast-1.amazonaws.com

# ビルド
docker build -t infra-cost-reduction-mcp-server .

# タグ付け
docker tag infra-cost-reduction-mcp-server:latest \
  ACCOUNT.dkr.ecr.ap-northeast-1.amazonaws.com/infra-cost-reduction-mcp-server:latest

# プッシュ
docker push ACCOUNT.dkr.ecr.ap-northeast-1.amazonaws.com/infra-cost-reduction-mcp-server:latest
```

---

## 7. コスト

### 7.1 AgentCore 料金

| 項目 | 料金 |
|------|------|
| **リクエスト** | $0.0001 / リクエスト |
| **コンピューティング** | $0.00001667 / 秒 (vCPU-秒) |
| **メモリ** | $0.0000025 / 秒 (GB-秒) |

### 7.2 月額コスト試算

| 条件 | 計算 | コスト |
|------|------|--------|
| 月間 10,000 リクエスト | 10,000 × $0.0001 | $1.00 |
| 平均処理時間 200ms | 10,000 × 0.2秒 × $0.00001667 | $0.03 |
| メモリ 512MB | 10,000 × 0.2秒 × 0.5 × $0.0000025 | $0.0025 |
| **合計** | | **約 $1.03/月** |

※ 実際の料金は利用状況により変動します

---

## 8. トラブルシューティング

### 8.1 よくあるエラー

| エラー | 原因 | 対処法 |
|--------|------|--------|
| `ResourceNotFoundException` | Runtime ARN が不正 | ARN を確認 |
| `AccessDeniedException` | IAM 権限不足 | ポリシーを確認 |
| `ServiceException` | MCP サーバーエラー | CloudWatch Logs を確認 |
| `ThrottlingException` | レート制限 | リトライ処理を追加 |

### 8.2 ログ確認

```bash
# AgentCore のログ
aws logs tail /aws/agentcore/infra_cost_reduction_pricing_mcp --follow

# Lambda のログ
aws logs tail /aws/lambda/infra-cost-reduction --follow
```

---

## 9. 参考リンク

- [AWS Bedrock AgentCore ドキュメント](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [MCP (Model Context Protocol) 仕様](https://modelcontextprotocol.io/)
- [AWS Pricing API ドキュメント](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html)

---

## 10. 変更履歴

| 日付 | バージョン | 変更内容 |
|------|-----------|---------|
| 2026-01-16 | 1.0 | 初版作成 |

---

*作成者: インフラコスト削減プロジェクトチーム*

