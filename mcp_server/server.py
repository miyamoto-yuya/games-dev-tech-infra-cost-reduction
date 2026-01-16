"""
AWS Pricing MCP Server
インスタンス料金の取得と最適化提案を行うMCPサーバー
AgentCore Runtime用 - HTTP JSON-RPC サーバー
"""

import json
import sys
from functools import lru_cache
from http.server import HTTPServer, BaseHTTPRequestHandler
import boto3

# インスタンスファミリーの同等品マッピング（コスト順）
INSTANCE_FAMILY_ALTERNATIVES = {
    "t3": ["t4g", "t3a", "t3"],
    "t3a": ["t4g", "t3a", "t3"],
    "t4g": ["t4g", "t3a", "t3"],
    "m5": ["m7g", "m6g", "m6a", "m5a", "m5"],
    "m5a": ["m7g", "m6g", "m6a", "m5a", "m5"],
    "m6i": ["m7g", "m6g", "m6a", "m6i"],
    "m6g": ["m7g", "m6g", "m6a", "m6i"],
    "c5": ["c7g", "c6g", "c6a", "c5a", "c5"],
    "c5a": ["c7g", "c6g", "c6a", "c5a", "c5"],
    "c6i": ["c7g", "c6g", "c6a", "c6i"],
    "r5": ["r7g", "r6g", "r6a", "r5a", "r5"],
    "r5a": ["r7g", "r6g", "r6a", "r5a", "r5"],
    "r6i": ["r7g", "r6g", "r6a", "r6i"],
    "db.t3": ["db.t4g", "db.t3"],
    "db.r5": ["db.r7g", "db.r6g", "db.r5"],
    "db.r6g": ["db.r7g", "db.r6g", "db.r5"],
    "db.m5": ["db.m7g", "db.m6g", "db.m5"],
    "cache.t3": ["cache.t4g", "cache.t3"],
    "cache.r5": ["cache.r7g", "cache.r6g", "cache.r5"],
    "cache.r6g": ["cache.r7g", "cache.r6g", "cache.r5"],
    "cache.m5": ["cache.m7g", "cache.m6g", "cache.m5"],
}

# ツール定義
TOOLS = [
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
        "name": "find_cheaper_alternatives",
        "description": "指定したインスタンスタイプより安い代替インスタンスを検索",
        "inputSchema": {
            "type": "object",
            "properties": {
                "instance_type": {"type": "string", "description": "現在のインスタンスタイプ"},
                "region": {"type": "string", "default": "ap-northeast-1"},
                "service": {"type": "string", "default": "ec2"}
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
    }
]


def get_pricing_client():
    """Pricing APIクライアントを取得"""
    return boto3.client("pricing", region_name="us-east-1")


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


REGION_MAPPING = {
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "us-east-1": "US East (N. Virginia)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "Europe (Ireland)",
}

# フォールバック価格（Pricing API が失敗した場合）
FALLBACK_PRICES = {
    # EC2
    't3.nano': 0.0052, 't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416, 't3.large': 0.0832,
    't3a.nano': 0.0047, 't3a.micro': 0.0094, 't3a.small': 0.0188, 't3a.medium': 0.0376, 't3a.large': 0.0752,
    't4g.nano': 0.0042, 't4g.micro': 0.0084, 't4g.small': 0.0168, 't4g.medium': 0.0336, 't4g.large': 0.0672,
    'm5.large': 0.096, 'm5.xlarge': 0.192, 'm6i.large': 0.096,
    'c5.large': 0.085, 'c5.xlarge': 0.17, 'r5.large': 0.126,
    # RDS
    'db.t3.micro': 0.018, 'db.t3.small': 0.036, 'db.t3.medium': 0.072, 'db.t3.large': 0.144,
    'db.t4g.micro': 0.016, 'db.t4g.small': 0.032, 'db.t4g.medium': 0.065, 'db.t4g.large': 0.129,
    'db.r5.large': 0.25, 'db.r5.xlarge': 0.50, 'db.r6g.large': 0.218, 'db.r6g.xlarge': 0.435,
    'db.m5.large': 0.185, 'db.m5.xlarge': 0.37, 'db.m6g.large': 0.158,
    # ElastiCache
    'cache.t3.micro': 0.017, 'cache.t3.small': 0.034, 'cache.t3.medium': 0.068,
    'cache.t4g.micro': 0.016, 'cache.t4g.small': 0.032, 'cache.t4g.medium': 0.064,
    'cache.r5.large': 0.24, 'cache.r6g.large': 0.218, 'cache.m5.large': 0.17,
}


@lru_cache(maxsize=1000)
def get_ec2_price(instance_type: str, region: str) -> float | None:
    """EC2インスタンスの時間単価を取得（USD）"""
    pricing = get_pricing_client()
    location = REGION_MAPPING.get(region, "Asia Pacific (Tokyo)")
    
    try:
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
    
    return FALLBACK_PRICES.get(instance_type)


@lru_cache(maxsize=1000)
def get_rds_price(instance_type: str, region: str) -> float | None:
    """RDSインスタンスの時間単価を取得（USD）"""
    pricing = get_pricing_client()
    location = REGION_MAPPING.get(region, "Asia Pacific (Tokyo)")
    
    try:
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
    
    return FALLBACK_PRICES.get(instance_type)


@lru_cache(maxsize=1000)
def get_elasticache_price(instance_type: str, region: str) -> float | None:
    """ElastiCacheインスタンスの時間単価を取得（USD）"""
    pricing = get_pricing_client()
    location = REGION_MAPPING.get(region, "Asia Pacific (Tokyo)")
    
    try:
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
    
    return FALLBACK_PRICES.get(instance_type)


@lru_cache(maxsize=1000)
def get_docdb_price(instance_type: str, region: str) -> float | None:
    """DocumentDBインスタンスの時間単価を取得（USD）"""
    pricing = get_pricing_client()
    location = REGION_MAPPING.get(region, "Asia Pacific (Tokyo)")
    
    try:
        response = pricing.get_products(
            ServiceCode="AmazonDocDB",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
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
        print(f"Error getting DocumentDB price: {e}", file=sys.stderr)
    
    return FALLBACK_PRICES.get(instance_type)


def get_price(instance_type: str, region: str, service: str = "ec2") -> float | None:
    """サービス種別に応じた価格を取得"""
    if service == "ec2":
        return get_ec2_price(instance_type, region)
    elif service == "rds" or service == "docdb":
        price = get_rds_price(instance_type, region)
        if price is None:
            price = get_docdb_price(instance_type, region)
        return price
    elif service == "elasticache":
        return get_elasticache_price(instance_type, region)
    return FALLBACK_PRICES.get(instance_type)


def find_alternatives(instance_type: str, service: str = "ec2") -> list:
    family, size = parse_instance_type(instance_type)
    alternatives = INSTANCE_FAMILY_ALTERNATIVES.get(family, [family])
    result = []
    for alt_family in alternatives:
        alt_type = f"{alt_family}.{size}"
        if alt_type != instance_type:
            result.append(alt_type)
    return result


def call_tool(name: str, arguments: dict) -> dict:
    """ツールを実行"""
    if name == "get_instance_price":
        instance_type = arguments["instance_type"]
        region = arguments.get("region", "ap-northeast-1")
        service = arguments.get("service", "ec2")
        price = get_price(instance_type, region, service)
        
        if price:
            return {
                "instance_type": instance_type,
                "region": region,
                "hourly_price_usd": round(price, 4),
                "monthly_cost_usd": round(price * 24 * 30, 2)
            }
        return {"error": f"Price not found for {instance_type}"}
    
    elif name == "find_cheaper_alternatives":
        instance_type = arguments["instance_type"]
        region = arguments.get("region", "ap-northeast-1")
        service = arguments.get("service", "ec2")
        
        current_price = get_price(instance_type, region, service)
        alternatives = find_alternatives(instance_type, service)
        
        results = []
        for alt_type in alternatives:
            alt_price = get_price(alt_type, region, service)
            if alt_price and current_price:
                savings_percent = ((current_price - alt_price) / current_price) * 100
                results.append({
                    "instance_type": alt_type,
                    "hourly_price_usd": round(alt_price, 4),
                    "savings_percent": round(savings_percent, 1)
                })
        
        results.sort(key=lambda x: x["hourly_price_usd"])
        return {
            "current": {"instance_type": instance_type, "hourly_price_usd": round(current_price, 4) if current_price else None},
            "alternatives": results
        }
    
    elif name == "calculate_monthly_savings":
        current_type = arguments["current_type"]
        proposed_type = arguments["proposed_type"]
        count = arguments.get("count", 1)
        region = arguments.get("region", "ap-northeast-1")
        
        current_price = get_price(current_type, region, "ec2")
        proposed_price = get_price(proposed_type, region, "ec2")
        
        if current_price and proposed_price:
            monthly_savings = (current_price - proposed_price) * 24 * 30 * count
            return {
                "current_monthly_usd": round(current_price * 24 * 30 * count, 2),
                "proposed_monthly_usd": round(proposed_price * 24 * 30 * count, 2),
                "monthly_savings_usd": round(monthly_savings, 2),
                "yearly_savings_usd": round(monthly_savings * 12, 2)
            }
        return {"error": "Could not retrieve prices"}
    
    return {"error": f"Unknown tool: {name}"}


def handle_jsonrpc(request: dict) -> dict:
    """JSON-RPC リクエストを処理"""
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")
    
    print(f"Handling method: {method}", file=sys.stderr)
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "aws-pricing-server", "version": "1.0.0"}
            }
        }
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        }
    
    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        result = call_tool(tool_name, tool_args)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
            }
        }
    
    elif method == "notifications/initialized":
        # 通知は応答不要
        return None
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


class MCPHandler(BaseHTTPRequestHandler):
    """MCP HTTP ハンドラー"""
    
    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}", file=sys.stderr)
    
    def do_GET(self):
        """ヘルスチェック用"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "healthy"}).encode())
    
    def do_POST(self):
        """JSON-RPC リクエスト処理"""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        print(f"Received: {body[:200]}", file=sys.stderr)
        
        try:
            request = json.loads(body)
            response = handle_jsonrpc(request)
            
            if response:
                response_body = json.dumps(response)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(response_body))
                self.end_headers()
                self.wfile.write(response_body.encode())
            else:
                # 通知の場合は 204
                self.send_response(204)
                self.end_headers()
                
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            error_response = json.dumps({
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": None
            })
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(error_response.encode())


if __name__ == "__main__":
    port = 8000
    print(f"Starting AWS Pricing MCP Server on port {port}", file=sys.stderr)
    server = HTTPServer(("0.0.0.0", port), MCPHandler)
    server.serve_forever()
