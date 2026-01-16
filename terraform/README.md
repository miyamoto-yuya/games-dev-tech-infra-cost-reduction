# AWS Lambda Terraform構成

インフラコスト削減ツールをAWS Lambda + Function URLでブラウザから利用できるようにするTerraform構成です。

## 作成されるリソース

- **Lambda Function**: メインのアプリケーション
- **Lambda Function URL**: ブラウザからアクセス可能なURL
- **IAM Role**: Lambda実行ロール（AWS各種サービスへのアクセス権限付き）
- **CloudWatch Logs**: ログ出力用

## 前提条件

- Terraform >= 1.0
- AWS CLI（認証設定済み）
- Bedrockのモデルアクセスが有効化されていること

## 使い方

### 1. Terraformでインフラを作成

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 2. ブラウザでアクセス

デプロイ完了後、出力される`lambda_function_url`にブラウザでアクセスします。

```
Outputs:

lambda_function_url = "https://xxxxxxxxxx.lambda-url.ap-northeast-1.on.aws/"
```

このURLをブラウザで開くと、AWSインフラコスト削減アナライザーのUIが表示されます。

### 3. 分析を実行

1. ブラウザで「**分析を実行**」ボタンをクリック
2. EC2、RDS、DocumentDB、ElastiCacheのリソース情報が収集されます
3. AIがサイジングの提案を行います

## 変数

| 変数名 | 説明 | デフォルト値 |
|--------|------|--------------|
| aws_region | AWSリージョン | ap-northeast-1 |
| project_name | プロジェクト名 | infra-cost-reduction |
| bedrock_model_id | Bedrock モデルID | anthropic.claude-3-sonnet-20240229-v1:0 |

## カスタマイズ例

### リージョンを変更する場合

```bash
terraform apply -var="aws_region=us-east-1"
```

### Bedrockモデルを変更する場合

```bash
terraform apply -var="bedrock_model_id=anthropic.claude-3-5-sonnet-20241022-v2:0"
```

## 注意事項

- Bedrockを使用するリージョンでモデルアクセスを事前に有効化してください
- Lambda Function URLは認証なし（`NONE`）で設定されています。必要に応じてIAM認証に変更してください
- Lambda関数のタイムアウトは5分（300秒）に設定されています

## トラブルシューティング

### Bedrock呼び出しエラーが発生する場合

1. AWSコンソールでBedrockの「Model access」を確認
2. 使用するモデル（Claude 3 Sonnet等）へのアクセスをリクエスト・有効化

### タイムアウトが発生する場合

大規模なAWS環境では、リソース情報の収集に時間がかかる場合があります。
`lambda.tf`の`timeout`値を増やすことで対応できます。

## 削除方法

```bash
terraform destroy
```
