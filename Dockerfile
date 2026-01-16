FROM python:3.11-slim

WORKDIR /app

# 必要なパッケージのインストール
RUN pip install --no-cache-dir boto3

# アプリケーションファイルをコピー
COPY check.py bedrock.py ./

# デフォルトでcheck.pyを実行
CMD ["python", "check.py"]

