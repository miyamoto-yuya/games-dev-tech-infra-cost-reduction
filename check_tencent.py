#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tencent Cloud Advisor レポート生成ツール

tccli advisor DescribeStrategies コマンドを実行し、
指定されたグループ（Security, Cost, Performance, Reliability）の情報をHTML形式で出力します。

API Keyの設定方法:
1. 環境変数で設定:
   export TENCENTCLOUD_SECRET_ID="your-secret-id"
   export TENCENTCLOUD_SECRET_KEY="your-secret-key"
   export TENCENTCLOUD_REGION="ap-tokyo"  # オプション

2. コマンドライン引数で設定:
   python check_tencent.py --secret-id YOUR_ID --secret-key YOUR_KEY --region ap-tokyo

3. tccli configure コマンドで設定:
   tccli configure
"""

import subprocess
import json
import sys
import argparse
import os
from html import escape
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

try:
    from googletrans import Translator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    print("警告: googletransがインストールされていません。翻訳機能を使用するには 'pip install googletrans==4.0.0rc1' を実行してください。", file=sys.stderr)


def escape_html(text):
    """HTMLエスケープを行う"""
    if text is None:
        return ''
    return escape(str(text))


def translate_to_japanese(text: str) -> str:
    """テキストを日本語に翻訳"""
    if not text:
        return text
    
    if not TRANSLATOR_AVAILABLE:
        return text
    
    # N/Aや空文字列の場合は翻訳不要
    if text in ['N/A', '', None] or str(text).strip() == '':
        return text
    
    # 文字列に変換
    text_str = str(text)
    
    try:
        translator = Translator()
        # リトライ処理（最大3回）
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 長いテキストの場合は分割して翻訳
                if len(text_str) > 5000:
                    # 長いテキストは分割
                    parts = []
                    for i in range(0, len(text_str), 5000):
                        part = text_str[i:i+5000]
                        result = translator.translate(part, src='en', dest='ja')
                        parts.append(result.text)
                    return ''.join(parts)
                else:
                    result = translator.translate(text_str, src='en', dest='ja')
                    translated = result.text
                    # 翻訳結果が空でないことを確認
                    if translated and translated.strip():
                        return translated
                    else:
                        # 翻訳結果が空の場合は元のテキストを返す
                        return text_str
            except Exception as retry_error:
                if attempt < max_retries - 1:
                    # リトライ前に少し待機
                    import time
                    time.sleep(0.5)
                    continue
                else:
                    raise retry_error
    except Exception as e:
        # 翻訳に失敗した場合は元のテキストを返す
        print(f"警告: 翻訳に失敗しました (テキスト: {text_str[:50]}...): {e}", file=sys.stderr)
        return text_str


def get_strategy_risks(strategy_id: int, secret_id: Optional[str] = None, secret_key: Optional[str] = None, region: Optional[str] = None, language: str = 'en-US'):
    """
    各戦略のリスク情報（リソースリスト）を取得
    
    Args:
        strategy_id: 戦略ID
        secret_id: Tencent Cloud Secret ID（オプション、環境変数からも取得可能）
        secret_key: Tencent Cloud Secret Key（オプション、環境変数からも取得可能）
        region: リージョン（オプション、環境変数からも取得可能）
        language: 言語設定（デフォルト: en-US）
    """
    try:
        # コマンドを構築
        cmd = ['tccli', 'advisor', 'DescribeTaskStrategyRisks', '--StrategyId', str(strategy_id), '--language', language]
        
        # 環境変数または引数から認証情報を取得
        env = os.environ.copy()
        
        if secret_id:
            env['TENCENTCLOUD_SECRET_ID'] = secret_id
        if secret_key:
            env['TENCENTCLOUD_SECRET_KEY'] = secret_key
        if region:
            env['TENCENTCLOUD_REGION'] = region
        elif 'TENCENTCLOUD_REGION' not in env:
            env['TENCENTCLOUD_REGION'] = 'ap-tokyo'
        
        # tccliコマンドを実行
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        
        # JSONをパース
        data = json.loads(result.stdout)
        
        return data
    
    except subprocess.CalledProcessError as e:
        # エラーが発生しても警告のみで続行
        print(f"警告: 戦略ID {strategy_id} のリスク情報取得に失敗しました: {e.stderr}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"警告: 戦略ID {strategy_id} のJSONパースに失敗しました: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"警告: 戦略ID {strategy_id} のリスク情報取得中にエラーが発生しました: {e}", file=sys.stderr)
        return None


def get_strategies(group_name: str = 'Cost', secret_id: Optional[str] = None, secret_key: Optional[str] = None, region: Optional[str] = None, language: str = 'en-US', include_resources: bool = True):
    """
    tccli advisor DescribeStrategies コマンドを実行し、
    指定されたGroupNameの戦略を取得
    
    Args:
        group_name: グループ名（デフォルト: Cost, 選択肢: Security, Cost, Performance, Reliability）
        secret_id: Tencent Cloud Secret ID（オプション、環境変数からも取得可能）
        secret_key: Tencent Cloud Secret Key（オプション、環境変数からも取得可能）
        region: リージョン（オプション、環境変数からも取得可能）
        language: 言語設定（デフォルト: en-US）
        include_resources: リソースリストを含めるか（デフォルト: True）
    """
    try:
        # コマンドを構築
        cmd = ['tccli', 'advisor', 'DescribeStrategies', '--language', language]
        
        # 環境変数または引数から認証情報を取得
        env = os.environ.copy()
        
        if secret_id:
            env['TENCENTCLOUD_SECRET_ID'] = secret_id
        elif 'TENCENTCLOUD_SECRET_ID' not in env:
            # 環境変数にも設定されていない場合
            # tccli configureで設定されている可能性があるため、警告は出さない
            pass
        
        if secret_key:
            env['TENCENTCLOUD_SECRET_KEY'] = secret_key
        elif 'TENCENTCLOUD_SECRET_KEY' not in env:
            # 環境変数にも設定されていない場合
            # tccli configureで設定されている可能性があるため、警告は出さない
            pass
        
        if region:
            env['TENCENTCLOUD_REGION'] = region
        elif 'TENCENTCLOUD_REGION' not in env:
            # デフォルトリージョンを設定（必要に応じて変更）
            env['TENCENTCLOUD_REGION'] = 'ap-tokyo'
        
        # tccliコマンドを実行
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        
        # JSONをパース
        data = json.loads(result.stdout)
        
        # 指定されたGroupNameの戦略をフィルタリング
        strategies = []
        found_strategies_count = 0  # 見つかった戦略の総数
        filtered_count = 0  # RiskTotalCountが0で除外された戦略数
        
        if 'Strategies' in data:
            for strategy in data['Strategies']:
                if strategy.get('GroupName') == group_name:
                    found_strategies_count += 1
                    # リソースリストを取得する場合
                    if include_resources:
                        strategy_id = strategy.get('StrategyId')
                        if strategy_id:
                            # StrategyIdを整数に変換
                            try:
                                strategy_id_int = int(strategy_id)
                            except (ValueError, TypeError):
                                strategy_id_int = None
                            
                            if strategy_id_int:
                                risks_data = get_strategy_risks(
                                    strategy_id=strategy_id_int,
                                    secret_id=secret_id,
                                    secret_key=secret_key,
                                    region=region,
                                    language=language
                                )
                                if risks_data:
                                    # リソース情報を戦略データに追加
                                    strategy['ResourceList'] = risks_data.get('Risks', '')
                                    strategy['ResourceCount'] = risks_data.get('ResourceCount', 0)
                                    strategy['RiskTotalCount'] = risks_data.get('RiskTotalCount', 0)
                                else:
                                    # リソース情報が取得できない場合はRiskTotalCountを0に設定
                                    strategy['RiskTotalCount'] = 0
                            else:
                                # StrategyIdが無効な場合はRiskTotalCountを0に設定
                                strategy['RiskTotalCount'] = 0
                        else:
                            # StrategyIdが存在しない場合はRiskTotalCountを0に設定
                            strategy['RiskTotalCount'] = 0
                        
                        # RiskTotalCountが0の場合は戦略を追加しない
                        if strategy.get('RiskTotalCount', 0) == 0:
                            filtered_count += 1
                            continue
                    else:
                        # include_resourcesがFalseの場合は、RiskTotalCountを確認できないため全て表示
                        pass
                    strategies.append(strategy)
        
        # 統計情報を返す
        return strategies, found_strategies_count, filtered_count
    
    except subprocess.CalledProcessError as e:
        print(f"エラー: tccliコマンドの実行に失敗しました: {e}", file=sys.stderr)
        print(f"標準エラー出力: {e.stderr}", file=sys.stderr)
        if "SecretId" in e.stderr or "SecretKey" in e.stderr or "credential" in e.stderr.lower():
            print("\nAPI Keyが正しく設定されていない可能性があります。", file=sys.stderr)
            print("以下のいずれかの方法で設定してください:", file=sys.stderr)
            print("1. 環境変数: export TENCENTCLOUD_SECRET_ID=... export TENCENTCLOUD_SECRET_KEY=...", file=sys.stderr)
            print("2. コマンドライン引数: --secret-id ... --secret-key ...", file=sys.stderr)
            print("3. tccli configure コマンドで設定", file=sys.stderr)
        return [], 0, 0
    except json.JSONDecodeError as e:
        print(f"エラー: JSONのパースに失敗しました: {e}", file=sys.stderr)
        return [], 0, 0
    except FileNotFoundError:
        print("エラー: tccliコマンドが見つかりません。Tencent Cloud CLIがインストールされているか確認してください。", file=sys.stderr)
        return [], 0, 0
    except Exception as e:
        print(f"エラー: 予期しないエラーが発生しました: {e}", file=sys.stderr)
        return [], 0, 0


def format_resource_list(resource_list):
    """Resource ListをHTML形式で整形"""
    if resource_list is None or resource_list == '':
        return 'N/A'
    
    # 文字列の場合はJSONとしてパースを試みる
    if isinstance(resource_list, str):
        try:
            resources = json.loads(resource_list)
        except (json.JSONDecodeError, TypeError):
            # JSONでない場合はそのまま表示
            return f'<div class="resource-list">{escape_html(str(resource_list))}</div>'
    else:
        resources = resource_list
    
    if not isinstance(resources, list):
        return f'<div class="resource-list">{escape_html(str(resources))}</div>'
    
    if not resources:
        return 'N/A'
    
    # 除外するフィールド
    excluded_fields = {'conditionID', 'PriId'}
    
    html_parts = ['<div class="resource-list">']
    for i, resource in enumerate(resources, 1):
        html_parts.append('<div class="resource-item">')
        if isinstance(resource, dict):
            # リソース情報を整形
            # ResourceIdを優先表示
            if 'ResourceId' in resource and resource['ResourceId'] is not None and str(resource['ResourceId']).strip():
                html_parts.append(f'<div class="resource-id"><strong>Resource ID:</strong> {escape_html(str(resource["ResourceId"]))}</div>')
            # ResourceNameを優先表示
            if 'ResourceName' in resource and resource['ResourceName'] is not None and str(resource['ResourceName']).strip():
                html_parts.append(f'<div class="resource-name"><strong>Resource Name:</strong> {escape_html(str(resource["ResourceName"]))}</div>')
            # ResourceTypeを優先表示
            if 'ResourceType' in resource and resource['ResourceType'] is not None and str(resource['ResourceType']).strip():
                html_parts.append(f'<div class="resource-type"><strong>Type:</strong> {escape_html(str(resource["ResourceType"]))}</div>')
            # Regionを優先表示
            if 'Region' in resource and resource['Region'] is not None and str(resource['Region']).strip():
                html_parts.append(f'<div class="resource-region"><strong>Region:</strong> {escape_html(str(resource["Region"]))}</div>')
            # Levelを表示（3のときはRisk: High、2のときはRisk: Medium）
            if 'Level' in resource and resource['Level'] is not None:
                # Levelを整数に変換
                try:
                    level = int(resource['Level'])
                except (ValueError, TypeError):
                    level = None
                
                if level == 3:
                    html_parts.append(f'<div class="resource-level"><strong>Risk:</strong> High</div>')
                elif level == 2:
                    html_parts.append(f'<div class="resource-level"><strong>Risk:</strong> Medium</div>')
                elif level == 1:
                    html_parts.append(f'<div class="resource-level"><strong>Risk:</strong> Low</div>')
                elif level is not None:
                    html_parts.append(f'<div class="resource-level"><strong>Risk:</strong> {escape_html(str(level))}</div>')
            # その他のフィールドを表示（除外フィールドと空の値を除く）
            for key, value in resource.items():
                # 除外フィールドをスキップ
                if key in excluded_fields:
                    continue
                # 既に表示済みのフィールドをスキップ
                if key in ['ResourceId', 'ResourceName', 'ResourceType', 'Region', 'Level']:
                    continue
                # None、空文字列、空のリスト/辞書をスキップ
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                if isinstance(value, (list, dict)) and not value:
                    continue
                html_parts.append(f'<div class="resource-field"><strong>{escape_html(str(key))}:</strong> {escape_html(str(value))}</div>')
        else:
            html_parts.append(f'<div class="resource-simple">{escape_html(str(resource))}</div>')
        html_parts.append('</div>')
    html_parts.append('</div>')
    return ''.join(html_parts)


def format_conditions(conditions):
    """ConditionsをHTML形式で整形"""
    if conditions is None:
        return 'N/A'
    
    if not isinstance(conditions, list):
        # 文字列の場合はJSONとしてパースを試みる
        try:
            conditions = json.loads(conditions) if isinstance(conditions, str) else conditions
        except (json.JSONDecodeError, TypeError):
            return escape_html(str(conditions))
    
    if not conditions:
        return 'N/A'
    
    html_parts = ['<div class="conditions-list">']
    for condition in conditions:
        if isinstance(condition, dict):
            html_parts.append('<div class="condition-item">')
            if 'Desc' in condition:
                html_parts.append(f'<div class="condition-desc">{escape_html(condition["Desc"])}</div>')
            if 'LevelDesc' in condition:
                level = condition.get('Level', '')
                level_desc = condition['LevelDesc']
                level_class = 'level-low' if level == 1 else 'level-medium' if level == 2 else 'level-high'
                html_parts.append(f'<div class="condition-level {level_class}">Risk: {escape_html(level_desc)}</div>')
            # ConditionIdは表示しない
            html_parts.append('</div>')
        else:
            html_parts.append(f'<div class="condition-item">{escape_html(str(condition))}</div>')
    html_parts.append('</div>')
    return ''.join(html_parts)


def format_value(value):
    """値を表示用にフォーマット"""
    if value is None:
        return 'N/A'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def generate_html_table(headers: List[str], rows: List[List[Any]], section_title: str = "", strategies: List[Dict[str, Any]] = None):
    """HTMLテーブルを生成"""
    html = []
    if section_title:
        html.append(f'<h2>{escape_html(section_title)}</h2>')
    html.append('<table class="data-table">')
    html.append('<thead><tr>')
    for header in headers:
        html.append(f'<th>{escape_html(header)}</th>')
    html.append('</tr></thead>')
    html.append('<tbody>')
    for row_idx, row in enumerate(rows):
        html.append('<tr>')
        for i, cell in enumerate(row):
            header = headers[i] if i < len(headers) else ''
            # Conditions列の場合は特別な整形を行う
            if header == 'Conditions':
                html.append(f'<td class="conditions-cell">{format_conditions(cell)}</td>')
            # ResourceList列の場合は特別な整形を行う
            elif header == 'ResourceList':
                html.append(f'<td class="resource-list-cell">{format_resource_list(cell)}</td>')
            # DescとRepair列の場合は日本語に翻訳
            elif header in ['Desc', 'Repair']:
                cell_value = format_value(cell)
                # N/Aや空の場合は翻訳不要
                if cell_value in ['N/A', '', None]:
                    html.append(f'<td>{escape_html(str(cell_value))}</td>')
                else:
                    translated_text = translate_to_japanese(str(cell_value))
                    html.append(f'<td>{escape_html(translated_text)}</td>')
            else:
                html.append(f'<td>{escape_html(format_value(cell))}</td>')
        html.append('</tr>')
    html.append('</tbody>')
    html.append('</table>')
    return '\n'.join(html)


def main():
    """メイン処理"""
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(
        description='Tencent Cloud Advisor レポート生成ツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
API Keyの設定方法:
  1. 環境変数で設定:
     export TENCENTCLOUD_SECRET_ID="your-secret-id"
     export TENCENTCLOUD_SECRET_KEY="your-secret-key"
     export TENCENTCLOUD_REGION="ap-tokyo"

  2. コマンドライン引数で設定:
     python check_tencent.py --secret-id YOUR_ID --secret-key YOUR_KEY --region ap-tokyo

  3. tccli configure コマンドで設定:
     tccli configure
        '''
    )
    parser.add_argument('--secret-id', help='Tencent Cloud Secret ID')
    parser.add_argument('--secret-key', help='Tencent Cloud Secret Key')
    parser.add_argument('--region', help='Tencent Cloud リージョン (デフォルト: ap-tokyo)')
    parser.add_argument('--language', default='en-US', help='言語設定 (デフォルト: en-US, 選択肢: en-US, zh-CN)')
    parser.add_argument('--group', default='Cost', help='グループ名 (デフォルト: Cost, 選択肢: Security, Cost, Performance, Reliability)')
    
    args = parser.parse_args()
    
    # 現在の日付を取得（YYYYMMDD形式、日本時間）
    jst = timezone(timedelta(hours=9))
    current_date = datetime.now(jst).strftime('%Y%m%d')
    
    # ファイル名を生成（グループ名を含める）
    group_name_lower = args.group.lower()
    html_filename = f"tencent-{group_name_lower}-{current_date}.html"
    
    # 戦略を取得
    strategies, found_strategies_count, filtered_count = get_strategies(
        group_name=args.group,
        secret_id=args.secret_id,
        secret_key=args.secret_key,
        region=args.region,
        language=args.language
    )
    
    # 戦略が見つからなかった場合
    if found_strategies_count == 0:
        print(f"警告: {args.group}グループの戦略が見つかりませんでした。", file=sys.stderr)
        # 空のHTMLファイルを生成
        html_content = f'''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tencent Cloud {args.group} レポート</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
        }}
        .message {{
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <h1>Tencent Cloud {args.group} レポート</h1>
    <div class="message">
        <p>{args.group}グループの戦略が見つかりませんでした。</p>
        <p>以下のコマンドを実行して確認してください:</p>
        <pre>tccli advisor DescribeStrategies | jq '.Strategies[] | select(.GroupName == "{args.group}")'</pre>
    </div>
</body>
</html>'''
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"空のレポートを {html_filename} に出力しました。")
        return
    
    # RiskTotalCountが0で除外された場合
    if not strategies and found_strategies_count > 0:
        print(f"情報: {args.group}グループで{found_strategies_count}件の戦略が見つかりましたが、すべてRiskTotalCountが0のため表示対象外です。", file=sys.stderr)
        # 空のHTMLファイルを生成
        html_content = f'''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tencent Cloud {args.group} レポート</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
        }}
        .message {{
            background-color: #e6f2ff;
            border: 1px solid #0066cc;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <h1>Tencent Cloud {args.group} レポート</h1>
    <div class="message">
        <p>{args.group}グループで{found_strategies_count}件の戦略が見つかりましたが、すべてRiskTotalCountが0のため表示対象外です。</p>
        <p>リスクが検出されていないため、現在最適化の必要はありません。</p>
    </div>
</body>
</html>'''
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"空のレポートを {html_filename} に出力しました。")
        return
    
    # テーブルのヘッダーと行を準備
    # すべての戦略に共通するフィールドを確認
    all_keys = set()
    for strategy in strategies:
        all_keys.update(strategy.keys())
    
    # 主要なフィールドを優先順位順に並べる
    # StrategyIdとGroupNameは除外
    priority_fields = [
        'Name',           # 左側に配置
        'Product',        # 左側に配置
        'ProductDesc',   # 左側に配置
        'StrategyName',
        'Description',
        'RiskLevel',
        'RiskDesc',
        'ProductName',
        'Category',
        'CategoryName',
        'Conditions',
        'ResourceList',
        'ResourceCount',
        'RiskTotalCount',
        'EstimatedMonthlySavings',
        'EstimatedSavingsPercentage',
        'CurrentCost',
        'RecommendedAction',
        'Impact',
        'Priority',
        'Status',
        'CreateTime',
        'UpdateTime'
    ]
    
    # 除外するフィールド
    excluded_fields = {'StrategyId', 'GroupName', 'GroupId'}
    
    # 優先フィールドから存在するものを選択（除外フィールドを除く）
    headers = []
    for field in priority_fields:
        if field in all_keys and field not in excluded_fields:
            headers.append(field)
    
    # 残りのフィールドを追加（除外フィールドを除く）
    remaining_fields = sorted(all_keys - set(headers) - excluded_fields)
    headers.extend(remaining_fields)
    
    # 行データを準備
    rows = []
    for strategy in strategies:
        row = [strategy.get(header, 'N/A') for header in headers]
        rows.append(row)
    
    # HTMLコンテンツを生成
    html_content = []
    
    # HTMLヘッダー
    html_content.append(f'''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tencent Cloud {args.group} レポート</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #0066cc;
            margin-top: 30px;
            margin-bottom: 15px;
            border-left: 5px solid #0066cc;
            padding-left: 10px;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
            background-color: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow-x: auto;
        }}
        .data-table th {{
            background-color: #0066cc;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
            cursor: pointer;
            user-select: none;
            position: relative;
        }}
        .data-table th:hover {{
            background-color: #0052a3;
        }}
        .data-table th::after {{
            content: ' ↕';
            opacity: 0.5;
            font-size: 0.8em;
        }}
        .data-table th.sort-asc::after {{
            content: ' ↑';
            opacity: 1;
        }}
        .data-table th.sort-desc::after {{
            content: ' ↓';
            opacity: 1;
        }}
        .data-table td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
            word-wrap: break-word;
            max-width: 300px;
        }}
        .data-table tr:hover {{
            background-color: #f0f8ff;
        }}
        .data-table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        .summary {{
            background-color: #e6f2ff;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .summary p {{
            margin: 5px 0;
        }}
        .conditions-cell {{
            max-width: 400px;
        }}
        .conditions-list {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .condition-item {{
            background-color: #f8f9fa;
            border-left: 3px solid #0066cc;
            padding: 8px 12px;
            border-radius: 4px;
        }}
        .condition-desc {{
            font-weight: 500;
            color: #333;
            margin-bottom: 4px;
        }}
        .condition-level {{
            font-size: 0.9em;
            margin-top: 4px;
        }}
        .condition-level.level-low {{
            color: #28a745;
        }}
        .condition-level.level-medium {{
            color: #ffc107;
        }}
        .condition-level.level-high {{
            color: #dc3545;
        }}
        .condition-id {{
            font-size: 0.85em;
            color: #6c757d;
            margin-top: 4px;
        }}
        .resource-list-cell {{
            max-width: 500px;
        }}
        .resource-list {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .resource-item {{
            background-color: #f0f8ff;
            border-left: 3px solid #0066cc;
            padding: 8px 12px;
            border-radius: 4px;
            margin-bottom: 4px;
        }}
        .resource-id, .resource-name, .resource-type, .resource-region, .resource-field {{
            margin: 4px 0;
            font-size: 0.9em;
        }}
        .resource-id strong, .resource-name strong, .resource-type strong, .resource-region strong, .resource-field strong {{
            color: #0066cc;
        }}
        .resource-simple {{
            font-size: 0.9em;
            color: #333;
        }}
    </style>
</head>
<body>
    <h1>Tencent Cloud {args.group} レポート</h1>
    <div class="summary">
        <p><strong>生成日時:</strong> {datetime.now(timezone(timedelta(hours=9))).strftime('%Y年%m月%d日 %H:%M:%S')}</p>
        <p><strong>戦略数:</strong> {len(strategies)}</p>
    </div>
''')
    
    # テーブルを追加
    html_content.append(generate_html_table(headers, rows, f"{args.group} 戦略", strategies))
    
    # HTMLフッター（ソート機能付き）
    html_content.append('''
    <script>
        function sortTable(table, columnIndex, isNumeric = false) {
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const currentSort = table.dataset.sortColumn;
            const currentOrder = table.dataset.sortOrder || 'asc';
            
            // ソート方向を決定
            let sortOrder = 'asc';
            if (currentSort == columnIndex && currentOrder === 'asc') {
                sortOrder = 'desc';
            }
            
            // テーブルにソート情報を保存
            table.dataset.sortColumn = columnIndex;
            table.dataset.sortOrder = sortOrder;
            
            // ヘッダーのソートクラスを更新
            const headers = table.querySelectorAll('th');
            headers.forEach((th, index) => {
                th.classList.remove('sort-asc', 'sort-desc');
                if (index == columnIndex) {
                    th.classList.add('sort-' + sortOrder);
                }
            });
            
            // 行をソート
            rows.sort((a, b) => {
                const aText = a.cells[columnIndex].textContent.trim();
                const bText = b.cells[columnIndex].textContent.trim();
                
                let aValue, bValue;
                
                if (isNumeric) {
                    // 数値として比較（数値以外の文字を除去）
                    aValue = parseFloat(aText.replace(/[^0-9.-]/g, '')) || 0;
                    bValue = parseFloat(bText.replace(/[^0-9.-]/g, '')) || 0;
                } else {
                    // 文字列として比較
                    aValue = aText.toLowerCase();
                    bValue = bText.toLowerCase();
                }
                
                if (aValue < bValue) {
                    return sortOrder === 'asc' ? -1 : 1;
                }
                if (aValue > bValue) {
                    return sortOrder === 'asc' ? 1 : -1;
                }
                return 0;
            });
            
            // ソートした行を再配置
            rows.forEach(row => tbody.appendChild(row));
        }
        
        // ページ読み込み時にすべてのテーブルにソート機能を追加
        document.addEventListener('DOMContentLoaded', function() {
            const tables = document.querySelectorAll('.data-table');
            tables.forEach(table => {
                const headers = table.querySelectorAll('th');
                headers.forEach((header, index) => {
                    header.addEventListener('click', function() {
                        // 数値列かどうかを判定
                        const headerText = header.textContent.trim();
                        const isNumeric = /Savings|Percentage|Cost|Priority|Time/i.test(headerText);
                        sortTable(table, index, isNumeric);
                    });
                });
            });
        });
    </script>
</body>
</html>
''')
    
    # HTMLファイルに出力
    with open(html_filename, "w", encoding="utf-8") as f:
        f.write('\n'.join(html_content))
    
    print(f"レポートを {html_filename} に出力しました。")
    print(f"戦略数: {len(strategies)}")


if __name__ == "__main__":
    main()

