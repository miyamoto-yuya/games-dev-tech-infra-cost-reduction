# AWS Bedrock AgentCore 構築手順書

## 概要

**Bedrock AgentCore** は、MCPサーバーをサーバーレスでホスティングするAWSマネージドサービスです。

| 項目 | 説明 |
|------|------|
| プロトコル | MCP（Model Context Protocol） |
| 通信形式 | JSON-RPC 2.0 |

```
クライアント(Lambda等) ──► Bedrock AgentCore ──► MCPサーバー(Docker/ECR)
```

---

## Step 1: Terraformでインフラ構築

### main.tf

```hcl
# ECRリポジトリ
resource "aws_ecr_repository" "mcp_server" {
  name                 = "my-mcp-server"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

# AgentCore実行ロール
resource "aws_iam_role" "agentcore" {
  name = "my-agentcore-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# AgentCoreポリシー
resource "aws_iam_role_policy" "agentcore" {
  name = "agentcore-policy"
  role = aws_iam_role.agentcore.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage", "ecr:BatchCheckLayerAvailability"]
        Resource = aws_ecr_repository.mcp_server.arn
      },
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      }
    ]
  })
}

# 出力
output "ecr_repository_url" {
  value = aws_ecr_repository.mcp_server.repository_url
}

output "execution_role_arn" {
  value = aws_iam_role.agentcore.arn
}
```

### 適用手順

```bash
# ディレクトリの初期化
terraform init
```

```bash
# インフラの適用
terraform apply
```

出力例:

```
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.

Outputs:

ecr_repository_url = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/my-mcp-server"
execution_role_arn = "arn:aws:iam::123456789012:role/my-agentcore-role"
```

---

## Step 2: MCPサーバーの実装

### server.py

```python
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

TOOLS = [{
    "name": "add",
    "description": "足し算",
    "inputSchema": {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"]
    }
}]

def call_tool(name, args):
    if name == "add":
        return {"result": args["a"] + args["b"]}
    return {"error": "Unknown tool"}

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        method, params = body.get("method"), body.get("params", {})
        
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "serverInfo": {"name": "my-mcp"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            r = call_tool(params["name"], params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": json.dumps(r)}]}
        else:
            result = {"error": "Unknown method"}
        
        res = json.dumps({"jsonrpc": "2.0", "result": result, "id": body.get("id", 1)})
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(res.encode())

if __name__ == "__main__":
    HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
```

### Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY server.py .
EXPOSE 8000
CMD ["python", "server.py"]
```

---

## Step 3: Dockerイメージのビルド・プッシュ

### ECR URLの取得

```bash
ECR_URL=$(terraform output -raw ecr_repository_url)
echo $ECR_URL
```

### ECRへのログイン

```bash
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin ${ECR_URL%/*}
```

出力例:

```
Login Succeeded
```

### Dockerイメージのビルド

```bash
docker build -t my-mcp-server .
```

### タグ付けとプッシュ

```bash
docker tag my-mcp-server:latest ${ECR_URL}:latest
docker push ${ECR_URL}:latest
```

---

## Step 4: AgentCore Runtimeの作成

> ⚠️ AgentCore RuntimeはTerraformプロバイダー未対応のためCLIで作成します

### 環境変数の設定

```bash
ROLE_ARN=$(terraform output -raw execution_role_arn)
ECR_URL=$(terraform output -raw ecr_repository_url)
```

### Runtimeの作成

```bash
aws bedrock-agentcore create-agent-runtime \
  --name "my-mcp-runtime" \
  --execution-role-arn "${ROLE_ARN}" \
  --container-config "{\"imageUri\": \"${ECR_URL}:latest\", \"port\": 8000}" \
  --region ap-northeast-1
```

出力例:

```json
{
    "agentRuntimeArn": "arn:aws:bedrock-agentcore:ap-northeast-1:123456789012:agent-runtime/abc123",
    "agentRuntimeName": "my-mcp-runtime",
    "status": "CREATING"
}
```

作成されたRuntime ARNを控えておきます。

### ステータスの確認

```bash
aws bedrock-agentcore get-agent-runtime \
  --agent-runtime-id "abc123" \
  --region ap-northeast-1
```

---

## Step 5: 呼び出し（Lambda）

```python
import boto3, json, uuid

def call_mcp(runtime_arn, tool_name, arguments):
    client = boto3.client('bedrock-agentcore', region_name='ap-northeast-1')
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "id": 1
    })
    
    res = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        runtimeSessionId=str(uuid.uuid4()),
        mcpSessionId=str(uuid.uuid4()),
        mcpProtocolVersion="2024-11-05",
        contentType="application/json",
        accept="application/json, text/event-stream",
        payload=payload.encode()
    )
    
    content = ''.join(c.decode() for c in res.get("response", []))
    return json.loads(json.loads(content)["result"]["content"][0]["text"])

# 使用例
result = call_mcp(RUNTIME_ARN, "add", {"a": 10, "b": 20})
# => {"result": 30}
```

### Lambda用IAMポリシー

Lambda関数から AgentCore を呼び出すには、以下のポリシーを追加してください：

```hcl
resource "aws_iam_role_policy" "lambda_agentcore" {
  name = "lambda-agentcore-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "bedrock-agentcore:InvokeAgentRuntime"
        Resource = "*"
      }
    ]
  })
}
```

---

## Step 6: テスト実行

### ローカルでのテスト（Docker起動前）

MCPサーバーを直接起動してテスト：

```bash
python server.py &
```

別のターミナルで `curl` を使用してテスト：

```bash
# Initialize
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
```

期待される出力:

```json
{"jsonrpc": "2.0", "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "my-mcp"}}, "id": 1}
```

### ツール一覧の取得

```bash
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}'
```

期待される出力:

```json
{"jsonrpc": "2.0", "result": {"tools": [{"name": "add", "description": "足し算", "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}}]}, "id": 2}
```

### ツールの呼び出しテスト

```bash
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"add","arguments":{"a":10,"b":20}},"id":3}'
```

期待される出力:

```json
{"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": "{\"result\": 30}"}]}, "id": 3}
```

### Dockerコンテナでのテスト

```bash
# コンテナを起動
docker run -d -p 8000:8000 --name mcp-test my-mcp-server
```

```bash
# 同様のcurlコマンドでテスト
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"add","arguments":{"a":5,"b":3}},"id":1}'
```

```bash
# テスト後のクリーンアップ
docker stop mcp-test && docker rm mcp-test
```

### AgentCore経由でのテスト（デプロイ後）

Python スクリプトでテスト:

```python
# test_agentcore.py
import boto3
import json
import uuid

RUNTIME_ARN = "arn:aws:bedrock-agentcore:ap-northeast-1:123456789012:agent-runtime/abc123"

def test_add():
    client = boto3.client('bedrock-agentcore', region_name='ap-northeast-1')
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "add", "arguments": {"a": 10, "b": 20}},
        "id": 1
    })
    
    res = client.invoke_agent_runtime(
        agentRuntimeArn=RUNTIME_ARN,
        runtimeSessionId=str(uuid.uuid4()),
        mcpSessionId=str(uuid.uuid4()),
        mcpProtocolVersion="2024-11-05",
        contentType="application/json",
        accept="application/json, text/event-stream",
        payload=payload.encode()
    )
    
    content = ''.join(c.decode() for c in res.get("response", []))
    result = json.loads(json.loads(content)["result"]["content"][0]["text"])
    
    assert result["result"] == 30, f"Expected 30, got {result}"
    print("✅ Test passed: add(10, 20) = 30")

if __name__ == "__main__":
    test_add()
```

実行:

```bash
python test_agentcore.py
```

期待される出力:

```
✅ Test passed: add(10, 20) = 30
```

---

## 料金

### AgentCore料金体系

| 項目 | 料金 |
|------|------|
| リクエスト | $0.0001/リクエスト |
| コンピューティング | $0.00001667/秒（vCPU-秒） |
| メモリ | $0.0000025/秒（GB-秒） |

### 月額コスト試算

| 条件 | 計算 | コスト |
|------|------|--------|
| 月間10,000リクエスト | 10,000 × $0.0001 | $1.00 |
| 平均処理時間200ms | 10,000 × 0.2秒 × $0.00001667 | $0.03 |
| メモリ512MB | 10,000 × 0.2秒 × 0.5 × $0.0000025 | $0.0025 |
| **合計** | | **約$1.03/月** |

---

## トラブルシューティング

| エラー | 対処法 |
|--------|--------|
| `ResourceNotFoundException` | Runtime ARNを確認 |
| `AccessDeniedException` | IAMポリシーを確認 |
| `ImagePullFailure` | ECR権限、イメージURIを確認 |

ログ確認：
```bash
aws logs tail /aws/agentcore/my-mcp-runtime --follow
```

---

## 参考リンク

- [AWS Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [MCP仕様](https://modelcontextprotocol.io/)
