概要：
AWS費用削減シートに記載する内容をboto3で取得するコード
VScodeでの動作を想定しています

利用方法：
=========== devコンテナ起動　===========
1: このリポジトリをgit clone後、VScodeで開く
2 :左下の「><」マークをクリック
3: 「コンテナーで再度開く」をクリック

=========== AWS PROFILE 設定 ===========
1: ~/.aws/config と ~/.aws/credentials を設定
2: ターミナルで以下コマンド実行（ii-devはprofile名です、適宜変更してください）
   export AWS_PROFILE=ii-dev

=========== コード実行 ===========
1: ターミナルで以下コマンド実行（ii-devはprofile名です、適宜変更してください）
   python check.py --profile ii-dev
2: output.txtに結果が表示されます
　 結果を一旦新しいスプレッドシートにコピーして利用するのを推奨します