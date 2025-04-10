# ベースイメージとして公式のPythonイメージを使用
FROM python:3.11-slim

# 作業ディレクトリの作成
WORKDIR /workspace

# 必要なツールをインストール（curl, unzipなど）
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    groff \
    less \
    git \
    && rm -rf /var/lib/apt/lists/*

# AWS CLI v2 をインストール
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws
    
# 任意で他のライブラリも requirements.txt で追加できるように
COPY requirements.txt .
RUN pip install -r requirements.txt || true  # requirements.txt が空でもOKにする
