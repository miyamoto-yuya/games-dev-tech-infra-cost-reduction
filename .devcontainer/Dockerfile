# ベースイメージとして公式のPythonイメージを使用（Debian Bookwormベース）
FROM python:3.11-slim-bookworm

# 作業ディレクトリの作成
WORKDIR /workspace

# 必要なツールをインストール（curl, unzipなど）
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    groff \
    less \
    git \
    gnupg \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# AWS CLI v2 をインストール（アーキテクチャを自動検出）
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then \
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"; \
    elif [ "$ARCH" = "arm64" ]; then \
        curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"; \
    fi && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws

# Terraform をインストール
RUN curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com bookworm main" > /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update \
    && apt-get install -y terraform \
    && rm -rf /var/lib/apt/lists/*

# 任意で他のライブラリも requirements.txt で追加できるように
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true
