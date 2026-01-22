"""
AWS Pricing MCP Server - Lightweight
AgentCore用 - 純粋JSON-RPC（起動高速化版）
"""

import json
import sys
from functools import lru_cache

# 起動高速化: boto3は遅延インポート
_boto3 = None

def get_boto3():
    global _boto3
    if _boto3 is None:
        import boto3
        _boto3 = boto3
    return _boto3

# 標準ライブラリのみ使用（最速起動のため）

REGION_MAPPING = {
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "us-east-1": "US East (N. Virginia)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "Europe (Ireland)",
}

# サイズ順序（小さい順）
SIZE_ORDER = ['nano', 'micro', 'small', 'medium', 'large', 'xlarge', '2xlarge', '4xlarge', '8xlarge', '12xlarge', '16xlarge', '24xlarge']
SIZE_MULTIPLIERS = {
    'nano': 0.25, 'micro': 0.5, 'small': 1, 'medium': 2, 'large': 4, 
    'xlarge': 8, '2xlarge': 16, '4xlarge': 32, '8xlarge': 64, 
    '12xlarge': 96, '16xlarge': 128, '24xlarge': 192
}

def get_family_min_size_simple(family: str, service: str = "ec2") -> str:
    """
    ファミリーの最小サイズを判定（シンプルルール）
    - EC2 T系: nano
    - RDS T系: medium（microやsmallは存在しない）
    - ElastiCache T系: micro
    - DocumentDB T系: medium（smallやmicroは存在しない）
    - それ以外: large
    """
    # ファミリー名の末尾部分を取得（例: "db.t3" → "t3", "cache.t4g" → "t4g"）
    base_family = family.split('.')[-1] if '.' in family else family
    
    # T系かどうか判定
    if base_family.startswith('t'):
        # RDS/DocumentDBのT系は medium が最小
        if service in ("rds", "docdb"):
            return 'medium'
        # ElastiCacheのT系は micro
        if family.startswith('cache.'):
            return 'micro'
        # EC2のT系は nano
        return 'nano'
    
    # それ以外は large
    return 'large'


def get_pricing_client():
    """Pricing APIクライアントを取得"""
    try:
        client = get_boto3().client("pricing", region_name="us-east-1")
        return client
    except Exception as e:
        print(f"[ERROR] Failed to create pricing client: {e}", file=sys.stderr)
        raise


def parse_instance_type(instance_type: str) -> tuple:
    """インスタンスタイプをファミリーとサイズに分解"""
    if instance_type.startswith(("db.", "cache.")):
        parts = instance_type.split(".")
        if len(parts) >= 3:
            return (f"{parts[0]}.{parts[1]}", parts[2])
    parts = instance_type.split(".")
    if len(parts) == 2:
        return (parts[0], parts[1])
    return (instance_type, "")


def get_service_from_family(family: str) -> str:
    """ファミリー名からサービスタイプを判定"""
    if family.startswith("db."):
        return "rds"
    elif family.startswith("cache."):
        return "elasticache"
    return "ec2"


def get_family_min_size(family: str, region: str = "ap-northeast-1", service: str = "ec2") -> str:
    """ファミリーの最小サイズを取得（シンプルルール使用）"""
    return get_family_min_size_simple(family, service)


@lru_cache(maxsize=1000)
def get_ec2_price(instance_type: str, region: str) -> float | None:
    """EC2インスタンスの時間単価を取得（USD）"""
    try:
        pricing = get_pricing_client()
        location = REGION_MAPPING.get(region, "Asia Pacific (Tokyo)")
        response = pricing.get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            ],
            MaxResults=1
        )
        
        if response["PriceList"]:
            price_data = json.loads(response["PriceList"][0])
            on_demand = price_data["terms"]["OnDemand"]
            for term in on_demand.values():
                for price_dimension in term["priceDimensions"].values():
                    price = float(price_dimension["pricePerUnit"]["USD"])
                    if price > 0:
                        return price
    except Exception as e:
        print(f"Error getting EC2 price: {e}", file=sys.stderr)
    
    return None


@lru_cache(maxsize=1000)
def get_rds_price(instance_type: str, region: str) -> float | None:
    """RDSインスタンスの時間単価を取得（USD）"""
    try:
        pricing = get_pricing_client()
        location = REGION_MAPPING.get(region, "Asia Pacific (Tokyo)")
        response = pricing.get_products(
            ServiceCode="AmazonRDS",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": "Aurora MySQL"},
                {"Type": "TERM_MATCH", "Field": "deploymentOption", "Value": "Single-AZ"},
            ],
            MaxResults=5
        )
        
        if response["PriceList"]:
            for price_item in response["PriceList"]:
                price_data = json.loads(price_item)
                on_demand = price_data.get("terms", {}).get("OnDemand", {})
                for term in on_demand.values():
                    for price_dimension in term.get("priceDimensions", {}).values():
                        price = float(price_dimension.get("pricePerUnit", {}).get("USD", 0))
                        if price > 0:
                            return price
    except Exception as e:
        print(f"Error getting RDS price: {e}", file=sys.stderr)
    
    return None


@lru_cache(maxsize=1000)
def get_elasticache_price(instance_type: str, region: str) -> float | None:
    """ElastiCacheインスタンスの時間単価を取得（USD）"""
    try:
        pricing = get_pricing_client()
        location = REGION_MAPPING.get(region, "Asia Pacific (Tokyo)")
        response = pricing.get_products(
            ServiceCode="AmazonElastiCache",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "cacheEngine", "Value": "Redis"},
            ],
            MaxResults=5
        )
        
        if response["PriceList"]:
            for price_item in response["PriceList"]:
                price_data = json.loads(price_item)
                on_demand = price_data.get("terms", {}).get("OnDemand", {})
                for term in on_demand.values():
                    for price_dimension in term.get("priceDimensions", {}).values():
                        price = float(price_dimension.get("pricePerUnit", {}).get("USD", 0))
                        if price > 0:
                            return price
    except Exception as e:
        print(f"Error getting ElastiCache price: {e}", file=sys.stderr)
    
    return None


@lru_cache(maxsize=1000)
def get_docdb_price(instance_type: str, region: str) -> float | None:
    """DocumentDBインスタンスの時間単価を取得（USD）"""
    try:
        pricing = get_pricing_client()
        location = REGION_MAPPING.get(region, "Asia Pacific (Tokyo)")
        # DocumentDBのPricing APIはinstanceTypeフィールドを使用
        response = pricing.get_products(
            ServiceCode="AmazonDocDB",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
            ],
            MaxResults=10
        )
        
        print(f"[DocDB Pricing] {instance_type} in {location}: {len(response.get('PriceList', []))} results", file=sys.stderr)
        
        if response["PriceList"]:
            for price_item in response["PriceList"]:
                price_data = json.loads(price_item)
                on_demand = price_data.get("terms", {}).get("OnDemand", {})
                for term in on_demand.values():
                    for price_dimension in term.get("priceDimensions", {}).values():
                        # 時間単価のみ取得（ストレージ料金などを除外）
                        unit = price_dimension.get("unit", "")
                        if "Hrs" in unit or "Hour" in unit:
                            price = float(price_dimension.get("pricePerUnit", {}).get("USD", 0))
                            if price > 0:
                                print(f"[DocDB Pricing] Found price for {instance_type}: ${price}/hr", file=sys.stderr)
                                return price
    except Exception as e:
        print(f"Error getting DocumentDB price for {instance_type}: {e}", file=sys.stderr)
    
    print(f"[DocDB Pricing] No price found for {instance_type}", file=sys.stderr)
    return None


def get_price(instance_type: str, region: str, service: str = "ec2") -> float | None:
    """サービス種別に応じた価格を取得"""
    if service == "ec2":
        return get_ec2_price(instance_type, region)
    elif service == "rds":
        return get_rds_price(instance_type, region)
    elif service == "docdb":
        return get_docdb_price(instance_type, region)
    elif service == "elasticache":
        return get_elasticache_price(instance_type, region)
    return None


def calculate_scale_down_recommendation(
    instance_type: str, 
    cpu_avg_max: float, 
    region: str = "ap-northeast-1",
    service: str = "ec2"
) -> dict | None:
    """
    CPU使用率に基づいて最適なスケールダウン候補を計算
    目標: 予測CPU使用率が50-70%になるインスタンスタイプ
    """
    # None チェック
    if cpu_avg_max is None:
        return {"recommendation": None, "reason": "CPU取得不可", "current_cpu": None}
    
    if cpu_avg_max >= 40:
        return {
            "recommendation": None,
            "reason": "適正" if cpu_avg_max <= 70 else "スペック不足",
            "current_cpu": cpu_avg_max
        }
    
    family, current_size = parse_instance_type(instance_type)
    if not current_size or current_size not in SIZE_ORDER:
        return {"recommendation": None, "reason": "不明なインスタンスサイズ", "current_cpu": cpu_avg_max}
    
    current_multiplier = SIZE_MULTIPLIERS.get(current_size)
    if not current_multiplier:
        return {"recommendation": None, "reason": "サイズ係数不明", "current_cpu": cpu_avg_max}
    
    current_price = get_price(instance_type, region, service)
    if not current_price:
        return {"recommendation": None, "reason": "価格取得失敗", "current_cpu": cpu_avg_max}
    
    current_size_index = SIZE_ORDER.index(current_size)
    # 動的に最小サイズを検出（サービス毎に異なる）
    min_size = get_family_min_size(family, region, service)
    min_size_index = SIZE_ORDER.index(min_size) if min_size in SIZE_ORDER else 0
    
    if current_size_index <= min_size_index:
        return {
            "recommendation": None,
            "reason": "最小構成",
            "current_cpu": cpu_avg_max
        }
    
    best_candidate = None
    
    for i in range(current_size_index - 1, min_size_index - 1, -1):
        candidate_size = SIZE_ORDER[i]
        candidate_type = f"{family}.{candidate_size}"
        candidate_multiplier = SIZE_MULTIPLIERS.get(candidate_size)
        
        if not candidate_multiplier:
            continue
        
        ratio = current_multiplier / candidate_multiplier
        predicted_cpu = cpu_avg_max * ratio
        
        candidate_price = get_price(candidate_type, region, service)
        if not candidate_price:
            continue
        
        if candidate_price < current_price and predicted_cpu <= 70:
            best_candidate = {
                "recommended_type": candidate_type,
                "predicted_cpu": round(predicted_cpu, 2),
                "current_price": round(current_price, 4),
                "recommended_price": round(candidate_price, 4),
                "hourly_savings": round(current_price - candidate_price, 4),
                "monthly_savings": round((current_price - candidate_price) * 730, 2),
                "savings_percent": round((1 - candidate_price / current_price) * 100, 1)
            }
            if predicted_cpu >= 40:
                break
        elif predicted_cpu > 70:
            break
    
    if best_candidate:
        return {
            "recommendation": best_candidate,
            "reason": "変更推奨" if best_candidate["predicted_cpu"] >= 40 else "過剰（更に削減余地あり）",
            "current_cpu": cpu_avg_max
        }
    
    return {
        "recommendation": None,
        "reason": "スケールダウン候補なし",
        "current_cpu": cpu_avg_max
    }


def get_batch_recommendations(instances: list, region: str = "ap-northeast-1") -> list:
    """複数インスタンスの一括提案を取得（価格APIを最小化）"""
    results = []
    # 価格キャッシュ（同じインスタンスタイプの再取得を防ぐ）
    price_cache = {}
    
    for inst in instances:
        try:
            name = inst.get("name", "")
            instance_type = inst.get("instance_type", "")
            cpu_avg_max = inst.get("cpu_avg_max")
            service = inst.get("service", "ec2")
            
            # CPU使用率がない場合はスキップ
            if cpu_avg_max is None:
                results.append({
                    "name": name,
                    "instance_type": instance_type,
                    "cpu_avg_max": None,
                    "recommendation": None,
                    "reason": "CPU取得不可",
                    "current_cpu": None
                })
                continue
            
            # CPU使用率が適正範囲以上の場合はスキップ（提案不要）
            if cpu_avg_max >= 40:
                reason = "適正" if cpu_avg_max <= 70 else "スペック不足"
                results.append({
                    "name": name,
                    "instance_type": instance_type,
                    "cpu_avg_max": cpu_avg_max,
                    "recommendation": None,
                    "reason": reason,
                    "current_cpu": cpu_avg_max
                })
                continue
            
            # 最小構成チェック（価格API不要）
            family, current_size = parse_instance_type(instance_type)
            min_size = get_family_min_size(family, region, service)
            if current_size and current_size in SIZE_ORDER:
                current_idx = SIZE_ORDER.index(current_size)
                min_idx = SIZE_ORDER.index(min_size) if min_size in SIZE_ORDER else 0
                if current_idx <= min_idx:
                    results.append({
                        "name": name,
                        "instance_type": instance_type,
                        "cpu_avg_max": cpu_avg_max,
                        "recommendation": None,
                        "reason": "最小構成",
                        "current_cpu": cpu_avg_max
                    })
                    continue
            
            # スケールダウン計算（必要な場合のみ）
            rec = calculate_scale_down_recommendation(instance_type, cpu_avg_max, region, service)
            if rec is None:
                rec = {"recommendation": None, "reason": "計算エラー", "current_cpu": cpu_avg_max}
            
            results.append({
                "name": name,
                "instance_type": instance_type,
                "cpu_avg_max": cpu_avg_max,
                **rec
            })
        except Exception as e:
            print(f"[Batch] Error processing {inst}: {e}", file=sys.stderr)
            results.append({
                "name": inst.get("name", "unknown"),
                "instance_type": inst.get("instance_type", ""),
                "cpu_avg_max": inst.get("cpu_avg_max", 0),
                "recommendation": None,
                "reason": f"エラー: {str(e)}"
            })
    
    print(f"[Batch] Completed {len(results)} recommendations", file=sys.stderr)
    return results


def get_batch_prices(instance_types: list, region: str = "ap-northeast-1") -> dict:
    """複数インスタンスタイプの価格を一括取得"""
    results = {}
    for item in instance_types:
        try:
            instance_type = item.get("instance_type", "")
            service = item.get("service", "ec2")
            
            if instance_type and instance_type not in results:
                print(f"[BatchPrice] Getting price for {instance_type} ({service})", file=sys.stderr)
                price = get_price(instance_type, region, service)
                results[instance_type] = {
                    "hourly_price_usd": round(price, 4) if price else None,
                    "monthly_cost_usd": round(price * 730, 2) if price else None,
                    "service": service
                }
        except Exception as e:
            print(f"[BatchPrice] Error for {item}: {e}", file=sys.stderr)
            instance_type = item.get("instance_type", "unknown")
            results[instance_type] = {
                "hourly_price_usd": None,
                "monthly_cost_usd": None,
                "service": item.get("service", "ec2"),
                "error": str(e)
            }
    
    return results


# MCP SDK関連のデコレータは削除（起動高速化のため）
# ツール定義はget_tools_list()で提供、実行はcall_tool_sync()で処理




# ツール定義リスト（AgentCore用）
def get_tools_list() -> list:
    """ツール定義をdict形式で取得"""
    return [
        {
            "name": "get_instance_price",
            "description": "指定したインスタンスタイプの時間単価（USD）を取得します",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "instance_type": {"type": "string", "description": "インスタンスタイプ（例: t3.medium）"},
                    "region": {"type": "string", "description": "AWSリージョン", "default": "ap-northeast-1"},
                    "service": {"type": "string", "description": "サービスタイプ", "default": "ec2"}
                },
                "required": ["instance_type"]
            }
        },
        {
            "name": "calculate_monthly_savings",
            "description": "インスタンスタイプ変更による月額コスト削減額を計算",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "current_type": {"type": "string"},
                    "proposed_type": {"type": "string"},
                    "count": {"type": "integer", "default": 1},
                    "region": {"type": "string", "default": "ap-northeast-1"},
                    "service": {"type": "string", "default": "ec2"}
                },
                "required": ["current_type", "proposed_type"]
            }
        },
        {
            "name": "get_scale_down_recommendation",
            "description": "CPU使用率に基づいて最適なスケールダウン候補を計算。予測CPU使用率が50-70%になるインスタンスを推奨",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "instance_type": {"type": "string", "description": "現在のインスタンスタイプ（例: t3a.large）"},
                    "cpu_avg_max": {"type": "number", "description": "CPU AvgMax使用率（%）"},
                    "region": {"type": "string", "default": "ap-northeast-1"},
                    "service": {"type": "string", "default": "ec2", "description": "ec2, rds, elasticache, docdb"}
                },
                "required": ["instance_type", "cpu_avg_max"]
            }
        },
        {
            "name": "get_batch_recommendations",
            "description": "複数インスタンスに対する一括スケールダウン提案を取得",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "instances": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "instance_type": {"type": "string"},
                                "cpu_avg_max": {"type": "number"},
                                "service": {"type": "string", "default": "ec2"}
                            },
                            "required": ["name", "instance_type", "cpu_avg_max"]
                        }
                    },
                    "region": {"type": "string", "default": "ap-northeast-1"}
                },
                "required": ["instances"]
            }
        },
        {
            "name": "get_batch_prices",
            "description": "複数インスタンスタイプの価格を一括取得",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "instance_types": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "instance_type": {"type": "string"},
                                "service": {"type": "string", "default": "ec2"}
                            },
                            "required": ["instance_type"]
                        }
                    },
                    "region": {"type": "string", "default": "ap-northeast-1"}
                },
                "required": ["instance_types"]
            }
        }
    ]


def call_tool_sync(name: str, arguments: dict) -> dict:
    """ツールを同期的に実行（AgentCore用）"""
    try:
        print(f"[call_tool_sync] Called with name={name}, args keys={list(arguments.keys())}", file=sys.stderr)
        result = {}
        
        if name == "get_instance_price":
            instance_type = arguments["instance_type"]
            region = arguments.get("region", "ap-northeast-1")
            service = arguments.get("service", "ec2")
            price = get_price(instance_type, region, service)
            
            if price:
                result = {
                    "instance_type": instance_type,
                    "region": region,
                    "hourly_price_usd": round(price, 4),
                    "monthly_cost_usd": round(price * 24 * 30, 2)
                }
            else:
                result = {"error": f"Price not found for {instance_type}"}
        
        elif name == "calculate_monthly_savings":
            current_type = arguments["current_type"]
            proposed_type = arguments["proposed_type"]
            count = arguments.get("count", 1)
            region = arguments.get("region", "ap-northeast-1")
            
            current_price = get_price(current_type, region, "ec2")
            proposed_price = get_price(proposed_type, region, "ec2")
            
            if current_price and proposed_price:
                monthly_savings = (current_price - proposed_price) * 24 * 30 * count
                result = {
                    "current_monthly_usd": round(current_price * 24 * 30 * count, 2),
                    "proposed_monthly_usd": round(proposed_price * 24 * 30 * count, 2),
                    "monthly_savings_usd": round(monthly_savings, 2),
                    "yearly_savings_usd": round(monthly_savings * 12, 2)
                }
            else:
                result = {"error": "Could not retrieve prices"}
        
        elif name == "get_scale_down_recommendation":
            instance_type = arguments["instance_type"]
            cpu_avg_max = arguments["cpu_avg_max"]
            region = arguments.get("region", "ap-northeast-1")
            service = arguments.get("service", "ec2")
            
            result = calculate_scale_down_recommendation(instance_type, cpu_avg_max, region, service)
            if result is None:
                result = {"recommendation": None, "reason": "計算エラー"}
        
        elif name == "get_batch_recommendations":
            instances = arguments["instances"]
            region = arguments.get("region", "ap-northeast-1")
            print(f"[call_tool_sync] get_batch_recommendations: {len(instances)} instances", file=sys.stderr)
            
            result = {"recommendations": get_batch_recommendations(instances, region)}
        
        elif name == "get_batch_prices":
            instance_types = arguments["instance_types"]
            region = arguments.get("region", "ap-northeast-1")
            print(f"[call_tool_sync] get_batch_prices: {len(instance_types)} types", file=sys.stderr)
            
            result = {"prices": get_batch_prices(instance_types, region)}
        
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        print(f"[call_tool_sync] Returning result for {name}", file=sys.stderr)
        return result
        
    except Exception as e:
        print(f"[call_tool_sync] ERROR: {name} failed with {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return {"error": f"Internal error: {str(e)}"}


# 標準ライブラリのHTTPサーバー（最速起動）
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class MCPHandler(BaseHTTPRequestHandler):
    """軽量HTTPハンドラー"""
    
    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}", file=sys.stderr, flush=True)
    
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        """ヘルスチェック（GET /）"""
        self.send_json({"status": "healthy", "server": "aws-pricing-mcp"})
    
    def do_POST(self):
        """JSON-RPCリクエスト処理"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            request = json.loads(body.decode('utf-8'))
            
            method = request.get("method", "")
            params = request.get("params", {})
            req_id = request.get("id")
            
            print(f"[RPC] method={method}", file=sys.stderr, flush=True)
            
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "aws-pricing-server", "version": "1.0.0"}
                }
            elif method == "tools/list":
                result = {"tools": get_tools_list()}
            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                tool_result = call_tool_sync(tool_name, tool_args)
                result = {
                    "content": [{"type": "text", "text": json.dumps(tool_result, ensure_ascii=False)}]
                }
            elif method == "notifications/initialized":
                self.send_response(204)
                self.end_headers()
                return
            else:
                self.send_json({
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": req_id
                })
                return
            
            self.send_json({"jsonrpc": "2.0", "result": result, "id": req_id})
            
        except Exception as e:
            print(f"[RPC] Error: {e}", file=sys.stderr, flush=True)
            self.send_json({
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": None
            }, status=500)


def main():
    """メインエントリーポイント"""
    port = 8000
    # 即座にログ出力
    print(f"Starting server on port {port}...", file=sys.stderr, flush=True)
    
    server = HTTPServer(('0.0.0.0', port), MCPHandler)
    print(f"Server ready at http://0.0.0.0:{port}/", file=sys.stderr, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
