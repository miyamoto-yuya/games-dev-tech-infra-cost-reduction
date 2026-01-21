#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "  インフラコスト削減ツール デプロイ"
echo "=========================================="

# 引数チェック
if [ "$1" = "lambda" ]; then
    DEPLOY_LAMBDA=true
    DEPLOY_MCP=false
elif [ "$1" = "mcp" ]; then
    DEPLOY_LAMBDA=false
    DEPLOY_MCP=true
elif [ "$1" = "all" ] || [ -z "$1" ]; then
    DEPLOY_LAMBDA=true
    DEPLOY_MCP=true
else
    echo "使い方: $0 [lambda|mcp|all]"
    echo "  lambda : Lambda関数のみデプロイ"
    echo "  mcp    : MCPサーバーのみデプロイ"
    echo "  all    : 両方デプロイ (デフォルト)"
    exit 1
fi

# Lambda デプロイ
if [ "$DEPLOY_LAMBDA" = true ]; then
    echo ""
    echo "=== Lambda関数デプロイ ==="
    cd "${SCRIPT_DIR}/terraform"
    terraform apply -auto-approve
    echo ""
    echo "Lambda URL:"
    terraform output lambda_function_url
fi

# MCP Server デプロイ
if [ "$DEPLOY_MCP" = true ]; then
    echo ""
    echo "=== MCPサーバーデプロイ ==="
    cd "${SCRIPT_DIR}/mcp_server"
    ./deploy.sh
fi

echo ""
echo "=========================================="
echo "  デプロイ完了"
echo "=========================================="

