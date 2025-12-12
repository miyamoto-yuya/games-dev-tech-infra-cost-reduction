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
