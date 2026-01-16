# AWS Pricing MCP Server Dockerfile
# AgentCore Runtime用 - HTTP JSON-RPC サーバー

FROM python:3.11-slim

WORKDIR /app

# 依存関係のインストール
RUN pip install --no-cache-dir boto3

# アプリケーションコードをコピー
COPY server.py .

# ポート公開
EXPOSE 8000

# サーバー起動
CMD ["python", "-u", "server.py"]
