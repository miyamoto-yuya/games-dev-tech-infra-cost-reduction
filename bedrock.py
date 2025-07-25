import boto3
import json # 必要に応じてJSON形式での入出力も検討

# output.txtの内容を読み込む
try:
    with open("output.txt", "r", encoding="utf-8") as f:
        output_content = f.read()
except FileNotFoundError:
    print("Error: output.txt not found.")
    exit()

# Bedrock Runtimeクライアントを作成
# リージョンやモデルIDは環境に合わせて変更
bedrock_runtime = boto3.client("bedrock-runtime", region_name="ap-northeast-1") # 例: 東京リージョン

# 使用するモデルID (例: Claude 3 Sonnet)
# 利用可能なモデルIDは Bedrockのドキュメントを確認してください
model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

# プロンプトの構築
prompt = f"""あなたはAWSのインスタンスサイジングに関する一般的な提案を行うAIです。

以下に、現在のEC2/RDS/DocDB/Redisインスタンス情報と、過去30日間の5分間平均の最大CPU使用率を示します。
---
{output_content}
---

上記のデータに基づき、各インスタンス/クラスターについて、最大CPU使用率が目標である60%程度になるには、現在のインスタンスタイプからどのように変更するのが良いか、一般的な観点から提案してください。
特に最大CPU使用率が70%を超えているものに焦点を当ててください。
提案はあくまで一般的なもので構いません。正確なサイジングにはより詳細なメトリクス分析やワークロード特性の理解が必要です。
"""

# Bedrockにリクエストを送信
try:
    response = bedrock_runtime.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ],
            "max_tokens": 1000, # 応答の最大トークン数
            "temperature": 0.7 # 応答の多様性 (0.0-1.0)
        }),
        contentType='application/json',
        accept='application/json'
    )

    # 応答の解析
    response_body = json.loads(response['body'].read())
    bedrock_response_text = response_body['content'][0]['text']

    print("Bedrockからの提案:")
    print(bedrock_response_text)

except Exception as e:
    print(f"Bedrock呼び出しエラー: {e}")