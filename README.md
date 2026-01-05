# AWS コスト最適化レポート生成ツール

## 概要

AWS費用削減シートに記載する内容をboto3で取得するコードです。  
VSCodeでの動作を想定しています。  
実行後、HTMLファイルとテキストファイルに結果が出力されます。

## 利用方法

### devコンテナ起動

1. このリポジトリをgit clone後、VSCodeで開く
2. 左下の「><」マークをクリック
3. 「コンテナーで再度開く」をクリック

### AWS PROFILE 設定

1. `~/.aws/config` と `~/.aws/credentials` を設定
2. ターミナルで以下コマンド実行（`ii-dev`はprofile名です、適宜変更してください）
   ```bash
   export AWS_PROFILE=ii-dev
   ```
3. SSOアカウントの場合
   ```bash
   aws sso login --profile ii-dev
   ```

### コード実行

1. ターミナルで以下コマンド実行（`ii-dev`はprofile名です、適宜変更してください）
   ```bash
   python check.py --profile ii-dev
   ```
2. 実行後、以下のファイルが生成されます：
   - `{AWSアカウントID}-{年月日}.html` - HTML形式のレポート
   - `{AWSアカウントID}-{年月日}.txt` - テキスト形式のレポート
3. 結果を一旦新しいスプレッドシートにコピーして利用するのを推奨します
4. 最大CPU使用率は過去30日の5分平均の最大値を取得しています

### ファイルのアップロード

実行後、表示されるS3アップロードコマンドを実行してください：

```bash
aws s3 cp {ファイル名}.html s3://infra-test-935762823806/cost-reduction/ --profile ii-dev
```

### アクセス先URL

実行後、表示されるCloudFrontのURLからレポートを確認できます：

```
https://d1zflfjtk1ntnd.cloudfront.net/cost-reduction/{ファイル名}.html
```

## 取得できる情報

- **EC2**: インスタンス情報、CPU使用率、稼働状況
- **RDS**: クラスター情報、CPU使用率
- **DocumentDB**: クラスター情報、CPU使用率
- **Redis**: クラスター情報、CPU使用率、メモリ使用率
- **Memcached**: クラスター情報、CPU使用率、メモリ使用率
- **削減提案**: AWS Cost Optimization Hubからの推奨事項

## 注意事項

- 最大CPU使用率は過去30日の5分平均の最大値を取得しています
- 停止中のインスタンスも取得対象に含まれます

---

# Tencent Cloud コスト最適化レポート生成ツール

## 概要

Tencent Cloud Advisor APIからCostグループの戦略情報を取得し、HTML形式でレポートを生成するツールです。

## 前提条件

1. Tencent Cloud CLI (tccli) がインストールされていること
   ```bash
   pip install tccli
   ```

## API Keyの設定方法

以下の3つの方法のいずれかでAPI Keyを設定できます。

### 方法1: 環境変数で設定（推奨）

```bash
export TENCENTCLOUD_SECRET_ID="your-secret-id"
export TENCENTCLOUD_SECRET_KEY="your-secret-key"
export TENCENTCLOUD_REGION="ap-tokyo"  # オプション（デフォルト: ap-tokyo）
```

### 方法2: コマンドライン引数で設定

```bash
python check_tencent.py --secret-id YOUR_SECRET_ID --secret-key YOUR_SECRET_KEY --region ap-tokyo
```

### 方法3: tccli configure コマンドで設定

```bash
tccli configure
```

対話形式で以下を入力します：
- SecretId: あなたのSecret ID
- SecretKey: あなたのSecret Key
- Region: リージョン（例: ap-tokyo）

## コード実行

1. API Keyを設定（上記のいずれかの方法）
2. ターミナルで以下コマンド実行
   ```bash
   python check_tencent.py
   ```
3. 実行後、以下のファイルが生成されます：
   - `tencent-cost-{年月日}.html` - HTML形式のレポート

## 取得できる情報

- **コスト最適化戦略**: Tencent Cloud Advisorから取得したCostグループの戦略情報
  - 戦略ID、戦略名、説明
  - リスクレベル、リスク説明
  - 推定削減額、削減率
  - 推奨アクションなど

## 注意事項

- API Keyは機密情報です。環境変数や設定ファイルに保存する際は適切に管理してください
- リージョンは使用するTencent Cloudのリージョンに合わせて設定してください
