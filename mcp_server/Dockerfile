# AWS Pricing Server - Minimal
# AgentCore Runtime用 - 標準ライブラリ + boto3のみ

FROM python:3.11-slim

WORKDIR /app

# boto3のみ（最小依存）
RUN pip install --no-cache-dir boto3>=1.34.0

# アプリケーションコードをコピー
COPY server.py .

# ポート公開
EXPOSE 8000

# サーバー起動（即時開始）
CMD ["python", "-u", "server.py"]
