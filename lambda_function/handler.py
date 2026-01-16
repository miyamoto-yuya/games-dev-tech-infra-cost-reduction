import boto3
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone


# MCP サーバー設定
MCP_RUNTIME_ARN = os.environ.get(
    "MCP_RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:ap-northeast-1:935762823806:runtime/infra_cost_reduction_pricing_mcp-M4Abq6BZRK"
)


def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """MCP サーバーのツールを呼び出す"""
    try:
        client = boto3.client('bedrock-agentcore', region_name='ap-northeast-1')
        
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        })
        
        response = client.invoke_agent_runtime(
            agentRuntimeArn=MCP_RUNTIME_ARN,
            runtimeSessionId=str(uuid.uuid4()),
            mcpSessionId=str(uuid.uuid4()),
            mcpProtocolVersion="2024-11-05",
            contentType="application/json",
            accept="application/json, text/event-stream",
            payload=payload.encode('utf-8')
        )
        
        content = []
        for chunk in response.get("response", []):
            content.append(chunk.decode('utf-8'))
        result = json.loads(''.join(content))
        
        if "result" in result and "content" in result["result"]:
            return json.loads(result["result"]["content"][0]["text"])
        return {"error": "Invalid response format"}
        
    except Exception as e:
        print(f"MCP call error: {e}")
        return {"error": str(e)}


def get_instance_price_from_mcp(instance_type: str, service: str = "ec2", region: str = "ap-northeast-1") -> float:
    """MCPサーバーからインスタンス価格を取得"""
    result = call_mcp_tool("get_instance_price", {
        "instance_type": instance_type,
        "service": service,
        "region": region
    })
    return result.get('hourly_price_usd') or result.get('hourly_price', 0.0)

# CloudWatchから最大CPU使用率を取得（30日間、5分平均）
def get_max_cpu_utilization(instance_id, namespace='AWS/EC2', dimension_name='InstanceId'):
    cloudwatch = boto3.client('cloudwatch')

    period = 300  # 5分の期間
    days = 30  # 取得する期間（30日）

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    max_cpu = 0.0
    max_cpu_timestamp = None
    
    interval = timedelta(days=5)
    current_start = start_time

    while current_start < end_time:
        current_end = min(current_start + interval, end_time)

        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName='CPUUtilization',
            Dimensions=[{'Name': dimension_name, 'Value': instance_id}],
            StartTime=current_start,
            EndTime=current_end,
            Period=period,
            Statistics=['Average'],
            Unit='Percent'
        )

        datapoints = response.get('Datapoints', [])

        for dp in datapoints:
            if dp['Average'] > max_cpu:
                max_cpu = dp['Average']
                max_cpu_timestamp = dp['Timestamp']

        current_start = current_end
    
    return (round(max_cpu, 2), max_cpu_timestamp) if max_cpu > 0 else (None, None)


def get_ec2_instances():
    ec2 = boto3.client("ec2")
    
    response = ec2.describe_instances()
    instances_info = []
    instance_data = defaultdict(lambda: {"count": 0, "ebs_info": set(), "instance_ids": [], "auto_scaling_group": None})

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            if instance["State"]["Name"] in ["terminated", "stopped"]:
                continue
            
            instance_id = instance["InstanceId"]
            instance_type = instance["InstanceType"]
            
            instance_name = "N/A"
            for tag in instance.get("Tags", []):
                if tag["Key"] == "Name":
                    instance_name = tag["Value"]
                    break
            
            auto_scaling_group_name = None
            for tag in instance.get("Tags", []):
                if tag["Key"] == "aws:autoscaling:groupName":
                    auto_scaling_group_name = tag["Value"]
                    break
            
            key = (instance_name, instance_type)
            instance_data[key]["count"] += 1
            instance_data[key]["instance_ids"].append(instance_id)
            instance_data[key]["auto_scaling_group"] = auto_scaling_group_name
            
            for block_device in instance.get("BlockDeviceMappings", []):
                volume_id = block_device.get("Ebs", {}).get("VolumeId", "N/A")
                if volume_id != "N/A":
                    volume = ec2.describe_volumes(VolumeIds=[volume_id])["Volumes"][0]
                    ebs_type = volume["VolumeType"]
                    storage_size = volume["Size"]
                    instance_data[key]["ebs_info"].add((ebs_type, storage_size))
    
    for (instance_name, instance_type), data in instance_data.items():
        count = data["count"]
        ebs_info = data["ebs_info"]
        instance_ids = data["instance_ids"]
        auto_scaling_group_name = data["auto_scaling_group"]

        instance_id_display = instance_ids[0] if count == 1 else None

        max_cpu = 0.0
        max_cpu_timestamp = None

        if auto_scaling_group_name:
            max_cpu, max_cpu_timestamp = get_max_cpu_utilization(auto_scaling_group_name, namespace='AWS/EC2', dimension_name='AutoScalingGroupName')
        elif instance_ids:
            cpu_usages = [get_max_cpu_utilization(iid) for iid in instance_ids]
            for cpu, ts in cpu_usages:
                if cpu is not None and cpu > max_cpu:
                    max_cpu = cpu
                    max_cpu_timestamp = ts
        else:
            max_cpu = None
            max_cpu_timestamp = None

        if ebs_info:
            for ebs in ebs_info:
                instances_info.append({
                    "name": instance_name,
                    "instance_id": instance_id_display,
                    "instance_type": instance_type,
                    "count": count,
                    "ebs_type": ebs[0],
                    "ebs_size": ebs[1],
                    "max_cpu": max_cpu,
                    "max_cpu_time": max_cpu_timestamp.isoformat() if max_cpu_timestamp else None
                })

    return instances_info


def get_rds_clusters():
    rds = boto3.client("rds")
    clusters_info = []

    response = rds.describe_db_clusters()
    cluster_instance_ids = set()

    for cluster in response["DBClusters"]:
        if cluster["Engine"] == "docdb":
            continue
        cluster_name = cluster["DBClusterIdentifier"]
        node_count = len(cluster["DBClusterMembers"])

        instance_types = set()
        for member in cluster["DBClusterMembers"]:
            db_instance_identifier = member["DBInstanceIdentifier"]
            cluster_instance_ids.add(db_instance_identifier)
            db_instance = rds.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)["DBInstances"][0]
            instance_type = db_instance["DBInstanceClass"]
            instance_types.add(instance_type)

        instance_type_display = ", ".join(sorted(instance_types)) if len(instance_types) > 1 else next(iter(instance_types))
        cpu, ts = get_max_cpu_utilization(cluster_name, namespace='AWS/RDS', dimension_name='DBClusterIdentifier')

        clusters_info.append({
            "name": cluster_name,
            "instance_type": instance_type_display,
            "count": node_count,
            "max_cpu": cpu,
            "max_cpu_time": ts.isoformat() if ts else None
        })

    response = rds.describe_db_instances()
    for instance in response["DBInstances"]:
        instance_id = instance["DBInstanceIdentifier"]
        if instance_id in cluster_instance_ids:
            continue

        if instance["Engine"] == "docdb":
            continue

        instance_type = instance["DBInstanceClass"]
        cpu, ts = get_max_cpu_utilization(instance_id, namespace='AWS/RDS', dimension_name='DBInstanceIdentifier')
        clusters_info.append({
            "name": instance_id,
            "instance_type": instance_type,
            "count": 1,
            "max_cpu": cpu,
            "max_cpu_time": ts.isoformat() if ts else None
        })

    return clusters_info


def get_docdb_clusters():
    docdb = boto3.client("docdb")
    response = docdb.describe_db_clusters()
    clusters_info = []
    
    for cluster in response["DBClusters"]:
        if cluster["Engine"] != "docdb":
            continue
        cluster_name = cluster["DBClusterIdentifier"]
        
        instance_types = set()
        for member in cluster["DBClusterMembers"]:
            db_instance_identifier = member["DBInstanceIdentifier"]
            db_instance = docdb.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)["DBInstances"][0]
            instance_type = db_instance["DBInstanceClass"]
            instance_types.add(instance_type)
        
        instance_type_display = ", ".join(sorted(instance_types)) if len(instance_types) > 1 else next(iter(instance_types))
        
        node_count = len(cluster["DBClusterMembers"])
        cpu, ts = get_max_cpu_utilization(cluster_name, namespace='AWS/DocDB', dimension_name='DBClusterIdentifier')
        clusters_info.append({
            "name": cluster_name,
            "instance_type": instance_type_display,
            "count": node_count,
            "max_cpu": cpu,
            "max_cpu_time": ts.isoformat() if ts else None
        })
    
    return clusters_info


def get_redis_clusters():
    elasticache = boto3.client("elasticache")
    response = elasticache.describe_replication_groups()
    clusters_info = []

    for cluster in response["ReplicationGroups"]:
        cluster_name = cluster["ReplicationGroupId"]
        instance_type = cluster["CacheNodeType"]
        node_count = len(cluster["MemberClusters"])

        cpu = None
        ts = None
        for node_id in cluster["MemberClusters"]:
            cpu, ts = get_max_cpu_utilization(
                node_id,
                namespace='AWS/ElastiCache',
                dimension_name='CacheClusterId'
            )

        clusters_info.append({
            "name": cluster_name,
            "instance_type": instance_type,
            "count": node_count,
            "max_cpu": cpu,
            "max_cpu_time": ts.isoformat() if ts else None
        })

    return clusters_info


def get_memcache_clusters():
    elasticache = boto3.client("elasticache")
    response = elasticache.describe_cache_clusters()
    clusters_info = []

    for cluster in response["CacheClusters"]:
        if cluster["Engine"] != "memcached":
            continue
            
        cluster_name = cluster["CacheClusterId"]
        instance_type = cluster["CacheNodeType"]
        node_count = cluster["NumCacheNodes"]
        
        cpu, ts = get_max_cpu_utilization(
            cluster_name,
            namespace='AWS/ElastiCache',
            dimension_name='CacheClusterId'
        )

        clusters_info.append({
            "name": cluster_name,
            "instance_type": instance_type,
            "count": node_count,
            "max_cpu": cpu,
            "max_cpu_time": ts.isoformat() if ts else None
        })

    return clusters_info


def collect_all_resources():
    """すべてのAWSリソース情報を収集"""
    return {
        "ec2": get_ec2_instances(),
        "rds": get_rds_clusters(),
        "docdb": get_docdb_clusters(),
        "redis": get_redis_clusters(),
        "memcache": get_memcache_clusters()
    }


def format_resources_for_bedrock(resources, pricing_info=None):
    """リソース情報をBedrock用のテキスト形式に変換（価格情報含む）"""
    output = []
    
    # 時間単価から月額を計算するヘルパー
    def get_monthly_cost(instance_type, service):
        if not pricing_info:
            return None
        service_key = 'elasticache' if service in ['redis', 'memcache'] else service
        prices = pricing_info.get(service_key, {})
        hourly = prices.get(instance_type, 0)
        return round(hourly * 730, 2) if hourly else None
    
    output.append("EC2 :")
    output.append("Instance Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources["ec2"]:
        monthly = get_monthly_cost(item['instance_type'], 'ec2')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{item['name']}\t{item['instance_type']}\t{item['count']}\t{item['max_cpu']}\t{monthly_str}")

    output.append("\nRDS :")
    output.append("Cluster Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources["rds"]:
        monthly = get_monthly_cost(item['instance_type'], 'rds')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{item['name']}\t{item['instance_type']}\t{item['count']}\t{item['max_cpu']}\t{monthly_str}")

    output.append("\nDocumentDB :")
    output.append("Cluster Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources["docdb"]:
        monthly = get_monthly_cost(item['instance_type'], 'docdb')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{item['name']}\t{item['instance_type']}\t{item['count']}\t{item['max_cpu']}\t{monthly_str}")

    output.append("\nRedis (ElastiCache) :")
    output.append("Cluster Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources["redis"]:
        monthly = get_monthly_cost(item['instance_type'], 'redis')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{item['name']}\t{item['instance_type']}\t{item['count']}\t{item['max_cpu']}\t{monthly_str}")

    output.append("\nMemcached (ElastiCache) :")
    output.append("Cluster Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources["memcache"]:
        monthly = get_monthly_cost(item['instance_type'], 'memcache')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{item['name']}\t{item['instance_type']}\t{item['count']}\t{item['max_cpu']}\t{monthly_str}")

    return "\n".join(output)


def collect_pricing_info(resources):
    """リソースの価格情報を収集（EC2/RDS/ElastiCache/DocDB）- 重複タイプは1回のみ取得"""
    pricing_info = {
        'ec2': {},
        'rds': {},
        'elasticache': {},
        'docdb': {}
    }
    
    # サービスとリソースキーのマッピング
    service_mapping = [
        ('ec2', 'ec2', resources.get("ec2", [])),
        ('rds', 'rds', resources.get("rds", [])),
        ('docdb', 'docdb', resources.get("docdb", [])),
        ('elasticache', 'redis', resources.get("redis", [])),
        ('elasticache', 'memcache', resources.get("memcache", [])),
    ]
    
    for service_key, resource_key, items in service_mapping:
        for item in items:
            instance_type = item.get("instance_type")
            if instance_type and instance_type not in pricing_info[service_key]:
                price = get_instance_price_from_mcp(instance_type, service_key)
                if price > 0:
                    pricing_info[service_key][instance_type] = price
    
    return pricing_info


def get_bedrock_analysis(resource_text):
    """Bedrockにリソース情報を送信して分析を取得（トークン使用量も返す）"""
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION_NAME", "ap-northeast-1"))
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    prompt = f"""あなたはAWSのコスト削減に特化した提案を行うAIです。

以下に、現在のEC2/RDS/DocDB/Redis/Memcachedインスタンス情報と、過去30日間のCPU使用率データを示します。

【データカラムの説明】
- 「CPU AvgMax」列: 過去30日間の5分間平均値の最大（★判定に使用）
- 「CPU Max」列: 過去30日間の5分間最大値の最大（参考値）

---
{resource_text}
---

【判断基準】★★★ 必ず「CPU AvgMax」の値のみで判定 ★★★

| CPU AvgMax | 判定 | 提案 |
|------------|------|------|
| 30%未満 | 過剰 | 小さいタイプへ変更（コスト削減） |
| 30%〜70% | 適正 | 変更不要 |
| 70%以上 | 不足 | 変更不要（コメントのみ） |

★★★ 重要 ★★★
- これはコスト削減ツールです
- スケールダウン（小さいタイプへの変更）のみ提案してください
- スペック不足の場合は「変更不要」とし、コメントで「スペック不足」と記載するだけでOK

例：
- CPU AvgMax = 10% → 過剰 → t3.medium → t3.small へ変更提案
- CPU AvgMax = 35% → 適正 → 変更不要
- CPU AvgMax = 80% → 不足 → 変更不要（コメント：スペック不足）

【出力形式】
## サマリー
(コスト削減の可能性を1-2文で)

## 詳細提案

### EC2
- **インスタンス名**: (名前)
  - 現在: (タイプ) / CPU AvgMax: (値)%
  - 判定: (過剰/適正/不足)
  - 提案: (小さいタイプ または「変更不要」)

### RDS
(同様)

### DocumentDB
(同様)

### Redis (ElastiCache)
(同様)

### Memcached (ElastiCache)
(同様)

※ 該当リソースがない場合は「なし」と記載
"""

    # モデルIDに応じてリクエスト形式を切り替え
    if model_id.startswith("amazon.nova"):
        # Amazon Nova形式
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "maxTokens": 4000,
                "temperature": 0.7
            }
        }
    elif model_id.startswith("amazon.titan"):
        # Amazon Titan形式
        request_body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 2000,
                "temperature": 0.7
            }
        }
    elif "anthropic" in model_id or "claude" in model_id:
        # Anthropic Claude形式
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ],
            "max_tokens": 2000,
            "anthropic_version": "bedrock-2023-05-31",
            "temperature": 0.7
        }
    else:
        # デフォルト（Nova形式）
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "maxTokens": 4000,
                "temperature": 0.7
            }
        }

    response = bedrock_runtime.invoke_model(
        modelId=model_id,
        body=json.dumps(request_body),
        contentType='application/json',
        accept='application/json'
    )

    response_body = json.loads(response['body'].read())
    
    # トークン使用量を取得（Nova形式）
    usage = response_body.get('usage', {})
    input_tokens = usage.get('inputTokens', 0)
    output_tokens = usage.get('outputTokens', 0)
    
    # Nova Lite の料金（USD / 1K tokens）- ap-northeast-1
    INPUT_PRICE_PER_1K = 0.00006   # $0.06 / 1M tokens
    OUTPUT_PRICE_PER_1K = 0.00024  # $0.24 / 1M tokens
    
    input_cost = (input_tokens / 1000) * INPUT_PRICE_PER_1K
    output_cost = (output_tokens / 1000) * OUTPUT_PRICE_PER_1K
    total_cost = input_cost + output_cost
    
    token_info = {
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total_cost, 6),
        "total_cost_jpy": round(total_cost * 150, 4)  # 概算レート
    }
    
    # レスポンス形式に応じてテキストを抽出
    if model_id.startswith("amazon.nova"):
        analysis_text = response_body['output']['message']['content'][0]['text']
    elif model_id.startswith("amazon.titan"):
        analysis_text = response_body['results'][0]['outputText']
    elif "anthropic" in model_id or "claude" in model_id:
        analysis_text = response_body['content'][0]['text']
    else:
        analysis_text = response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', str(response_body))
    
    return {
        "text": analysis_text,
        "token_usage": token_info
    }


def get_cloudshell_script():
    """CloudShell用のスクリプトを返す"""
    return '''#!/usr/bin/env python3
"""
AWS インフラコスト削減アナライザー - CloudShell 用スクリプト
AWS CloudShell で実行して、結果をコピー&ペーストしてください。
"""

import boto3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import sys

def get_max_cpu_utilization(instance_id, namespace='AWS/EC2', dimension_name='InstanceId'):
    cloudwatch = boto3.client('cloudwatch')
    period = 300
    days = 30
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    max_cpu = 0.0
    max_cpu_timestamp = None
    interval = timedelta(days=5)
    current_start = start_time

    while current_start < end_time:
        current_end = min(current_start + interval, end_time)
        try:
            response = cloudwatch.get_metric_statistics(
                Namespace=namespace,
                MetricName='CPUUtilization',
                Dimensions=[{'Name': dimension_name, 'Value': instance_id}],
                StartTime=current_start,
                EndTime=current_end,
                Period=period,
                Statistics=['Average'],
                Unit='Percent'
            )
            for dp in response.get('Datapoints', []):
                if dp['Average'] > max_cpu:
                    max_cpu = dp['Average']
                    max_cpu_timestamp = dp['Timestamp']
        except Exception:
            pass
        current_start = current_end
    
    return (round(max_cpu, 2), max_cpu_timestamp) if max_cpu > 0 else (None, None)


def get_ec2_instances():
    ec2 = boto3.client("ec2")
    response = ec2.describe_instances()
    instances_info = []
    instance_data = defaultdict(lambda: {"count": 0, "ebs_info": set(), "instance_ids": [], "auto_scaling_group": None})

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            if instance["State"]["Name"] in ["terminated", "stopped"]:
                continue
            
            instance_id = instance["InstanceId"]
            instance_type = instance["InstanceType"]
            
            instance_name = "N/A"
            for tag in instance.get("Tags", []):
                if tag["Key"] == "Name":
                    instance_name = tag["Value"]
                    break
            
            auto_scaling_group_name = None
            for tag in instance.get("Tags", []):
                if tag["Key"] == "aws:autoscaling:groupName":
                    auto_scaling_group_name = tag["Value"]
                    break
            
            key = (instance_name, instance_type)
            instance_data[key]["count"] += 1
            instance_data[key]["instance_ids"].append(instance_id)
            instance_data[key]["auto_scaling_group"] = auto_scaling_group_name
            
            for block_device in instance.get("BlockDeviceMappings", []):
                volume_id = block_device.get("Ebs", {}).get("VolumeId", "N/A")
                if volume_id != "N/A":
                    try:
                        volume = ec2.describe_volumes(VolumeIds=[volume_id])["Volumes"][0]
                        ebs_type = volume["VolumeType"]
                        storage_size = volume["Size"]
                        instance_data[key]["ebs_info"].add((ebs_type, storage_size))
                    except Exception:
                        pass
    
    for (instance_name, instance_type), data in instance_data.items():
        count = data["count"]
        ebs_info = data["ebs_info"]
        instance_ids = data["instance_ids"]
        auto_scaling_group_name = data["auto_scaling_group"]
        instance_id_display = instance_ids[0] if count == 1 else None

        max_cpu = 0.0
        max_cpu_timestamp = None

        if auto_scaling_group_name:
            max_cpu, max_cpu_timestamp = get_max_cpu_utilization(auto_scaling_group_name, namespace='AWS/EC2', dimension_name='AutoScalingGroupName')
        elif instance_ids:
            for iid in instance_ids:
                cpu, ts = get_max_cpu_utilization(iid)
                if cpu is not None and cpu > max_cpu:
                    max_cpu = cpu
                    max_cpu_timestamp = ts

        if ebs_info:
            for ebs in ebs_info:
                instances_info.append([
                    instance_name, instance_id_display, instance_type, count,
                    ebs[0], ebs[1], max_cpu,
                    max_cpu_timestamp.isoformat() if max_cpu_timestamp else "N/A"
                ])

    return instances_info


def get_rds_clusters():
    rds = boto3.client("rds")
    clusters_info = []
    cluster_instance_ids = set()

    try:
        response = rds.describe_db_clusters()
        for cluster in response["DBClusters"]:
            if cluster["Engine"] == "docdb":
                continue
            cluster_name = cluster["DBClusterIdentifier"]
            node_count = len(cluster["DBClusterMembers"])

            instance_types = set()
            for member in cluster["DBClusterMembers"]:
                db_instance_identifier = member["DBInstanceIdentifier"]
                cluster_instance_ids.add(db_instance_identifier)
                db_instance = rds.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)["DBInstances"][0]
                instance_type = db_instance["DBInstanceClass"]
                instance_types.add(instance_type)

            instance_type_display = ", ".join(sorted(instance_types)) if len(instance_types) > 1 else next(iter(instance_types))
            cpu, ts = get_max_cpu_utilization(cluster_name, namespace='AWS/RDS', dimension_name='DBClusterIdentifier')
            clusters_info.append([cluster_name, instance_type_display, node_count, cpu, ts.isoformat() if ts else None])
    except Exception:
        pass

    try:
        response = rds.describe_db_instances()
        for instance in response["DBInstances"]:
            instance_id = instance["DBInstanceIdentifier"]
            if instance_id in cluster_instance_ids or instance["Engine"] == "docdb":
                continue
            instance_type = instance["DBInstanceClass"]
            cpu, ts = get_max_cpu_utilization(instance_id, namespace='AWS/RDS', dimension_name='DBInstanceIdentifier')
            clusters_info.append([instance_id, instance_type, 1, cpu, ts.isoformat() if ts else None])
    except Exception:
        pass

    return clusters_info


def get_docdb_clusters():
    docdb = boto3.client("docdb")
    clusters_info = []
    
    try:
        response = docdb.describe_db_clusters()
        for cluster in response["DBClusters"]:
            if cluster["Engine"] != "docdb":
                continue
            cluster_name = cluster["DBClusterIdentifier"]
            
            instance_types = set()
            for member in cluster["DBClusterMembers"]:
                db_instance_identifier = member["DBInstanceIdentifier"]
                db_instance = docdb.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)["DBInstances"][0]
                instance_type = db_instance["DBInstanceClass"]
                instance_types.add(instance_type)
            
            instance_type_display = ", ".join(sorted(instance_types)) if len(instance_types) > 1 else next(iter(instance_types))
            node_count = len(cluster["DBClusterMembers"])
            cpu, ts = get_max_cpu_utilization(cluster_name, namespace='AWS/DocDB', dimension_name='DBClusterIdentifier')
            clusters_info.append([cluster_name, instance_type_display, node_count, cpu, ts.isoformat() if ts else None])
    except Exception:
        pass
    
    return clusters_info


def get_redis_clusters():
    elasticache = boto3.client("elasticache")
    clusters_info = []

    try:
        response = elasticache.describe_replication_groups()
        for cluster in response["ReplicationGroups"]:
            cluster_name = cluster["ReplicationGroupId"]
            instance_type = cluster["CacheNodeType"]
            node_count = len(cluster["MemberClusters"])
            cpu, ts = None, None
            for node_id in cluster["MemberClusters"]:
                cpu, ts = get_max_cpu_utilization(node_id, namespace='AWS/ElastiCache', dimension_name='CacheClusterId')
            clusters_info.append([cluster_name, instance_type, node_count, cpu, ts.isoformat() if ts else None])
    except Exception:
        pass

    return clusters_info


def get_memcache_clusters():
    elasticache = boto3.client("elasticache")
    clusters_info = []

    try:
        response = elasticache.describe_cache_clusters()
        for cluster in response["CacheClusters"]:
            if cluster["Engine"] != "memcached":
                continue
            cluster_name = cluster["CacheClusterId"]
            instance_type = cluster["CacheNodeType"]
            node_count = cluster["NumCacheNodes"]
            cpu, ts = get_max_cpu_utilization(cluster_name, namespace='AWS/ElastiCache', dimension_name='CacheClusterId')
            clusters_info.append([cluster_name, instance_type, node_count, cpu, ts.isoformat() if ts else None])
    except Exception:
        pass

    return clusters_info


def main():
    print("=" * 60, file=sys.stderr)
    print("AWS インフラコスト削減アナライザー", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("データを収集中...", file=sys.stderr)
    
    ec2_instances = get_ec2_instances()
    print(f"  EC2: {len(ec2_instances)} 件", file=sys.stderr)
    
    rds_clusters = get_rds_clusters()
    print(f"  RDS: {len(rds_clusters)} 件", file=sys.stderr)
    
    docdb_clusters = get_docdb_clusters()
    print(f"  DocumentDB: {len(docdb_clusters)} 件", file=sys.stderr)
    
    redis_clusters = get_redis_clusters()
    print(f"  Redis: {len(redis_clusters)} 件", file=sys.stderr)
    
    memcache_clusters = get_memcache_clusters()
    print(f"  Memcached: {len(memcache_clusters)} 件", file=sys.stderr)
    
    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("以下の結果をコピーしてブラウザに貼り付けてください", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)

    print("\\nEC2 :")
    print("Instance Name\\tInstance ID\\tInstance Type\\t台数\\tEBS Type\\tEBS Size\\tMax CPU\\tMax CPU Time")
    for instance in ec2_instances:
        print("\\t".join(map(str, instance)))

    print("\\nRedis :")
    print("Cluster Name\\tInstance Type\\t台数\\tMax CPU\\tMax CPU Time")
    for cluster in redis_clusters:
        print("\\t".join(map(str, cluster)))

    print("\\nMemcached :")
    print("Cluster Name\\tInstance Type\\t台数\\tMax CPU\\tMax CPU Time")
    for cluster in memcache_clusters:
        print("\\t".join(map(str, cluster)))

    print("\\nRDS :")
    print("Cluster Name\\tInstance Type\\t台数\\tMax CPU\\tMax CPU Time")
    for cluster in rds_clusters:
        print("\\t".join(map(str, cluster)))

    print("\\nDocumentDB :")
    print("Cluster Name\\tInstance Type\\t台数\\tMax CPU\\tMax CPU Time")
    for cluster in docdb_clusters:
        print("\\t".join(map(str, cluster)))


if __name__ == "__main__":
    main()
'''


def get_local_check_script():
    """ローカル実行用のスクリプトを返す（AWS CLIプロファイル対応 + 自動アップロード）"""
    # 動的にURLを埋め込む
    return '''#!/usr/bin/env python3
"""
AWS インフラコスト削減アナライザー - ローカル実行用スクリプト

使用方法:
  # 自動アップロード + AI分析（推奨）
  python check.py --profile account-a --upload --analyze
  
  # 複数アカウント一括処理
  for p in account-a account-b account-c; do
    python check.py --profile $p --upload --analyze
  done
  
  # ファイルに保存
  python check.py --profile account-a --output result.txt
"""
import boto3
import argparse
import sys
import io
import json
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from collections import defaultdict
from datetime import datetime, timedelta, timezone

DEFAULT_URL = "https://oprto2mpbwtacfhzaql7phb5ay0rxifk.lambda-url.ap-northeast-1.on.aws/"
_session = None

def get_session():
    global _session
    if _session is None:
        _session = boto3.Session()
    return _session

def get_client(service_name):
    return get_session().client(service_name)

def get_max_cpu_utilization(instance_id, namespace='AWS/EC2', dimension_name='InstanceId'):
    cloudwatch = get_client('cloudwatch')
    period, days = 300, 30
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    max_cpu, max_cpu_timestamp = 0.0, None
    interval = timedelta(days=5)
    current_start = start_time
    while current_start < end_time:
        current_end = min(current_start + interval, end_time)
        response = cloudwatch.get_metric_statistics(
            Namespace=namespace, MetricName='CPUUtilization',
            Dimensions=[{'Name': dimension_name, 'Value': instance_id}],
            StartTime=current_start, EndTime=current_end,
            Period=period, Statistics=['Average'], Unit='Percent'
        )
        for dp in response.get('Datapoints', []):
            if dp['Average'] > max_cpu:
                max_cpu, max_cpu_timestamp = dp['Average'], dp['Timestamp']
        current_start = current_end
    return (round(max_cpu, 2), max_cpu_timestamp) if max_cpu > 0 else (None, None)

def get_ec2_instances():
    ec2 = get_client("ec2")
    response = ec2.describe_instances()
    instances_info = []
    instance_data = defaultdict(lambda: {"count": 0, "ebs_info": set(), "instance_ids": [], "asg": None})
    for reservation in response["Reservations"]:
        for inst in reservation["Instances"]:
            if inst["State"]["Name"] in ["terminated", "stopped"]: continue
            iid, itype = inst["InstanceId"], inst["InstanceType"]
            name, asg = "N/A", None
            for tag in inst.get("Tags", []):
                if tag["Key"] == "Name": name = tag["Value"]
                if tag["Key"] == "aws:autoscaling:groupName": asg = tag["Value"]
            key = (name, itype)
            instance_data[key]["count"] += 1
            instance_data[key]["instance_ids"].append(iid)
            instance_data[key]["asg"] = asg
            for bd in inst.get("BlockDeviceMappings", []):
                vid = bd.get("Ebs", {}).get("VolumeId")
                if vid:
                    vol = ec2.describe_volumes(VolumeIds=[vid])["Volumes"][0]
                    instance_data[key]["ebs_info"].add((vol["VolumeType"], vol["Size"]))
    for (name, itype), data in instance_data.items():
        ids = data["instance_ids"]
        id_disp = ids[0] if data["count"] == 1 else None
        max_cpu, max_ts = None, None
        if data["asg"]:
            max_cpu, max_ts = get_max_cpu_utilization(data["asg"], 'AWS/EC2', 'AutoScalingGroupName')
        elif ids:
            for i in ids:
                c, t = get_max_cpu_utilization(i)
                if c and (max_cpu is None or c > max_cpu): max_cpu, max_ts = c, t
        for ebs in data["ebs_info"] or [(None, None)]:
            instances_info.append([name, id_disp, itype, data["count"], ebs[0], ebs[1], max_cpu, max_ts.isoformat() if max_ts else "N/A"])
    return instances_info

def get_rds_clusters():
    rds = get_client("rds")
    info, seen = [], set()
    for c in rds.describe_db_clusters()["DBClusters"]:
        if c["Engine"] == "docdb": continue
        types = set()
        for m in c["DBClusterMembers"]:
            seen.add(m["DBInstanceIdentifier"])
            types.add(rds.describe_db_instances(DBInstanceIdentifier=m["DBInstanceIdentifier"])["DBInstances"][0]["DBInstanceClass"])
        cpu, ts = get_max_cpu_utilization(c["DBClusterIdentifier"], 'AWS/RDS', 'DBClusterIdentifier')
        info.append([c["DBClusterIdentifier"], ", ".join(sorted(types)), len(c["DBClusterMembers"]), cpu, ts.isoformat() if ts else None])
    for i in rds.describe_db_instances()["DBInstances"]:
        if i["DBInstanceIdentifier"] in seen or i["Engine"] == "docdb": continue
        cpu, ts = get_max_cpu_utilization(i["DBInstanceIdentifier"], 'AWS/RDS', 'DBInstanceIdentifier')
        info.append([i["DBInstanceIdentifier"], i["DBInstanceClass"], 1, cpu, ts.isoformat() if ts else None])
    return info

def get_docdb_clusters():
    docdb = get_client("docdb")
    info = []
    for c in docdb.describe_db_clusters()["DBClusters"]:
        if c["Engine"] != "docdb": continue
        types = set()
        for m in c["DBClusterMembers"]:
            types.add(docdb.describe_db_instances(DBInstanceIdentifier=m["DBInstanceIdentifier"])["DBInstances"][0]["DBInstanceClass"])
        cpu, ts = get_max_cpu_utilization(c["DBClusterIdentifier"], 'AWS/DocDB', 'DBClusterIdentifier')
        info.append([c["DBClusterIdentifier"], ", ".join(sorted(types)), len(c["DBClusterMembers"]), cpu, ts.isoformat() if ts else None])
    return info

def get_redis_clusters():
    ec = get_client("elasticache")
    info = []
    for c in ec.describe_replication_groups()["ReplicationGroups"]:
        cpu, ts = None, None
        for n in c["MemberClusters"]:
            cpu, ts = get_max_cpu_utilization(n, 'AWS/ElastiCache', 'CacheClusterId')
        info.append([c["ReplicationGroupId"], c["CacheNodeType"], len(c["MemberClusters"]), cpu, ts.isoformat() if ts else None])
    return info

def get_memcache_clusters():
    ec = get_client("elasticache")
    info = []
    for c in ec.describe_cache_clusters()["CacheClusters"]:
        if c["Engine"] != "memcached": continue
        cpu, ts = get_max_cpu_utilization(c["CacheClusterId"], 'AWS/ElastiCache', 'CacheClusterId')
        info.append([c["CacheClusterId"], c["CacheNodeType"], c["NumCacheNodes"], cpu, ts.isoformat() if ts else None])
    return info

def output_results(ec2, rds, docdb, redis, memcache, file=None):
    out = file or sys.stdout
    print("\\nEC2 :", file=out)
    print("Instance Name\\tInstance ID\\tInstance Type\\t台数\\tEBS Type\\tEBS Size\\tMax CPU\\tMax CPU Time", file=out)
    for i in ec2: print("\\t".join(map(str, i)), file=out)
    print("\\nRedis :", file=out)
    print("Cluster Name\\tInstance Type\\t台数\\tMax CPU\\tMax CPU Time", file=out)
    for c in redis: print("\\t".join(map(str, c)), file=out)
    print("\\nMemcached :", file=out)
    print("Cluster Name\\tInstance Type\\t台数\\tMax CPU\\tMax CPU Time", file=out)
    for c in memcache: print("\\t".join(map(str, c)), file=out)
    print("\\nRDS :", file=out)
    print("Cluster Name\\tInstance Type\\t台数\\tMax CPU\\tMax CPU Time", file=out)
    for c in rds: print("\\t".join(map(str, c)), file=out)
    print("\\nDocumentDB :", file=out)
    print("Cluster Name\\tInstance Type\\t台数\\tMax CPU\\tMax CPU Time", file=out)
    for c in docdb: print("\\t".join(map(str, c)), file=out)

def get_result_text(ec2, rds, docdb, redis, memcache):
    buf = io.StringIO()
    output_results(ec2, rds, docdb, redis, memcache, file=buf)
    return buf.getvalue()

def upload(text, url, analyze=False):
    data = json.dumps({"action": "analyze_text" if analyze else "upload_only", "resource_text": text}).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def log(msg, quiet=False):
    if not quiet: print(msg, file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description='AWS インフラリソース情報を収集・分析')
    parser.add_argument('--profile', '-p', type=str, help='AWSプロファイル名')
    parser.add_argument('--output', '-o', type=str, help='出力ファイル名')
    parser.add_argument('--stdout', '-s', action='store_true', help='標準出力に出力')
    parser.add_argument('--upload', '-u', action='store_true', help='サーバーに自動アップロード')
    parser.add_argument('--analyze', '-a', action='store_true', help='AI分析も実行')
    parser.add_argument('--url', type=str, default=DEFAULT_URL, help='アップロード先URL')
    parser.add_argument('--region', '-r', type=str, help='AWSリージョン')
    parser.add_argument('--quiet', '-q', action='store_true', help='進捗非表示')
    args = parser.parse_args()
    
    global _session
    quiet = args.quiet or args.stdout
    
    if args.profile:
        _session = boto3.Session(profile_name=args.profile, region_name=args.region) if args.region else boto3.Session(profile_name=args.profile)
        log(f"Using profile: {args.profile}", quiet)
    elif args.region:
        _session = boto3.Session(region_name=args.region)
    
    log("Collecting...", quiet)
    ec2 = get_ec2_instances(); log(f"  EC2: {len(ec2)}", quiet)
    rds = get_rds_clusters(); log(f"  RDS: {len(rds)}", quiet)
    docdb = get_docdb_clusters(); log(f"  DocDB: {len(docdb)}", quiet)
    redis = get_redis_clusters(); log(f"  Redis: {len(redis)}", quiet)
    memcache = get_memcache_clusters(); log(f"  Memcache: {len(memcache)}", quiet)
    
    text = get_result_text(ec2, rds, docdb, redis, memcache)

    if args.upload:
        log(f"Uploading to {args.url}...", quiet)
        res = upload(text, args.url, args.analyze)
        if "error" in res:
            log(f"❌ Error: {res['error']}", False)
            sys.exit(1)
        log("✅ Upload successful!", quiet)
        if args.analyze and "analysis" in res:
            print("\\n" + "="*60 + "\\n🤖 AI サイジング提案\\n" + "="*60 + "\\n")
            print(res["analysis"])
        if args.output:
            with open(args.output, "w") as f:
                f.write(text)
                if args.analyze and "analysis" in res:
                    f.write("\\n\\n" + res["analysis"])
            log(f"Also saved: {args.output}", quiet)
    elif args.stdout:
        output_results(ec2, rds, docdb, redis, memcache)
    elif args.output:
        with open(args.output, "w") as f:
            output_results(ec2, rds, docdb, redis, memcache, file=f)
        log(f"Saved: {args.output}", quiet)
    else:
        with open("output.txt", "w") as f:
            output_results(ec2, rds, docdb, redis, memcache, file=f)
        log("Saved: output.txt", quiet)

if __name__ == "__main__":
    main()
'''


def get_html_template():
    """フロントエンドHTMLを返す"""
    return '''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS インフラコスト削減アナライザー</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0f1a;
            --bg-secondary: #111827;
            --bg-card: #1a2332;
            --text-primary: #f0f4f8;
            --text-secondary: #94a3b8;
            --accent-cyan: #22d3ee;
            --accent-orange: #fb923c;
            --accent-green: #4ade80;
            --accent-red: #f87171;
            --accent-purple: #a78bfa;
            --border-color: #2d3a4f;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Noto Sans JP', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            background-image: 
                radial-gradient(ellipse at 10% 20%, rgba(34, 211, 238, 0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 90% 80%, rgba(251, 146, 60, 0.08) 0%, transparent 50%),
                linear-gradient(180deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        header {
            text-align: center;
            margin-bottom: 3rem;
            animation: fadeInDown 0.6s ease-out;
        }

        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .logo {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .logo-icon {
            width: 60px;
            height: 60px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-orange));
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.8rem;
            box-shadow: 0 8px 32px rgba(34, 211, 238, 0.3);
        }

        h1 {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-orange));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .subtitle {
            color: var(--text-secondary);
            font-size: 1.1rem;
            margin-top: 0.5rem;
        }

        .main-card {
            background: var(--bg-card);
            border-radius: 20px;
            border: 1px solid var(--border-color);
            padding: 2rem;
            margin-bottom: 2rem;
            animation: fadeInUp 0.6s ease-out 0.2s both;
        }

        .button-group {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }

        .btn {
            padding: 1rem 2rem;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-family: inherit;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--accent-cyan), #06b6d4);
            color: var(--bg-primary);
            box-shadow: 0 4px 20px rgba(34, 211, 238, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(34, 211, 238, 0.4);
        }

        .btn-secondary {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            border-color: var(--accent-cyan);
            background: rgba(34, 211, 238, 0.1);
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        .tab-btn {
            padding: 0.75rem 1.5rem;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: var(--bg-secondary);
            color: var(--text-secondary);
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s ease;
            font-family: inherit;
        }

        .tab-btn:hover {
            border-color: var(--accent-cyan);
            color: var(--text-primary);
        }

        .tab-btn.active {
            background: linear-gradient(135deg, rgba(34, 211, 238, 0.2), rgba(251, 146, 60, 0.2));
            border-color: var(--accent-cyan);
            color: var(--text-primary);
        }

        .status-bar {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
            padding: 1rem;
            margin-top: 1.5rem;
            border-radius: 10px;
            background: var(--bg-secondary);
            font-size: 0.95rem;
        }

        .status-bar.loading {
            color: var(--accent-cyan);
        }

        .status-bar.success {
            color: var(--accent-green);
        }

        .status-bar.error {
            color: var(--accent-red);
        }

        .spinner {
            width: 20px;
            height: 20px;
            border: 2px solid transparent;
            border-top-color: currentColor;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .results-section {
            display: none;
            animation: fadeInUp 0.6s ease-out;
        }

        .results-section.visible {
            display: block;
        }

        .section-title {
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            color: var(--text-primary);
        }

        .section-title .icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
        }

        .section-title .icon.ec2 { background: rgba(34, 211, 238, 0.2); }
        .section-title .icon.rds { background: rgba(251, 146, 60, 0.2); }
        .section-title .icon.redis { background: rgba(248, 113, 113, 0.2); }
        .section-title .icon.docdb { background: rgba(74, 222, 128, 0.2); }
        .section-title .icon.memcache { background: rgba(167, 139, 250, 0.2); }

        .data-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
        }

        .data-table th {
            background: var(--bg-secondary);
            padding: 0.75rem 1rem;
            text-align: left;
            font-weight: 500;
            color: var(--text-secondary);
            border-bottom: 2px solid var(--border-color);
            white-space: nowrap;
        }

        .data-table td {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        .data-table tr:hover {
            background: rgba(34, 211, 238, 0.05);
        }

        .cpu-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-weight: 500;
            font-size: 0.8rem;
        }

        .cpu-low { background: rgba(74, 222, 128, 0.2); color: var(--accent-green); }
        .cpu-medium { background: rgba(251, 146, 60, 0.2); color: var(--accent-orange); }
        .cpu-high { background: rgba(248, 113, 113, 0.2); color: var(--accent-red); }

        /* コストテーブル（横長） */
        .cost-table-wrapper {
            overflow-x: auto;
            margin: 0 -1rem;
            padding: 0 1rem;
        }
        
        .cost-table {
            width: 100%;
            min-width: 1000px;
            border-collapse: collapse;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
        }
        
        .cost-table .header-group th {
            background: var(--bg-secondary);
            padding: 0.6rem 0.8rem;
            text-align: center;
            font-weight: 600;
            color: var(--text-primary);
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
        }
        
        .cost-table .header-group .group-current {
            background: rgba(34, 211, 238, 0.15);
            color: var(--accent-cyan);
        }
        
        .cost-table .header-group .group-recommend {
            background: rgba(74, 222, 128, 0.15);
            color: var(--accent-green);
        }
        
        .cost-table .header-detail th {
            background: var(--bg-secondary);
            padding: 0.5rem 0.6rem;
            text-align: center;
            font-weight: 500;
            font-size: 0.75rem;
            color: var(--text-secondary);
            border-bottom: 2px solid var(--border-color);
            white-space: nowrap;
        }
        
        .cost-table td {
            padding: 0.6rem 0.8rem;
            border-bottom: 1px solid var(--border-color);
            text-align: center;
        }
        
        .cost-table tr:hover {
            background: rgba(34, 211, 238, 0.05);
        }
        
        .cost-table .name-cell {
            text-align: left;
            font-weight: 500;
            color: var(--text-primary);
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .cost-table .id-cell {
            text-align: left;
            font-size: 0.7rem;
            color: var(--text-secondary);
        }
        
        .cost-table .num-cell {
            text-align: right;
        }
        
        .cost-table .money-cell {
            text-align: right;
            font-weight: 500;
            color: var(--accent-cyan);
        }
        
        .cost-table .recommend-cell {
            color: var(--accent-green);
            font-weight: 500;
        }
        
        .cost-table .savings-cell {
            font-weight: 600;
        }
        
        .cost-table .savings-cell.positive {
            color: var(--accent-green);
            background: rgba(74, 222, 128, 0.1);
        }
        
        .cost-table .ai-comment-cell {
            text-align: left;
            font-size: 0.75rem;
            color: var(--text-secondary);
            max-width: 150px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .analysis-card {
            background: var(--bg-card);
            border-radius: 20px;
            border: 1px solid var(--border-color);
            padding: 2rem;
            margin-top: 2rem;
        }

        .analysis-content {
            font-size: 1rem;
            line-height: 1.8;
            color: var(--text-secondary);
            white-space: pre-wrap;
        }

        .analysis-content strong {
            color: var(--accent-cyan);
        }

        .empty-state {
            text-align: center;
            padding: 3rem;
            color: var(--text-secondary);
        }

        .empty-state .icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            opacity: 0.5;
        }

        .resource-cards {
            display: grid;
            gap: 1.5rem;
        }

        .resource-card {
            background: var(--bg-card);
            border-radius: 16px;
            border: 1px solid var(--border-color);
            overflow: hidden;
        }

        .resource-card-header {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
            background: var(--bg-secondary);
        }

        .resource-card-body {
            overflow-x: auto;
        }

        .timestamp {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }

            h1 {
                font-size: 1.8rem;
            }

            .button-group {
                flex-direction: column;
            }

            .btn {
                width: 100%;
                justify-content: center;
            }

            .data-table {
                font-size: 0.75rem;
            }

            .data-table th,
            .data-table td {
                padding: 0.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <div class="logo-icon">📊</div>
                <h1>AWS インフラコスト削減</h1>
            </div>
            <p class="subtitle">EC2・RDS・ElastiCache・DocumentDB のサイジング最適化提案</p>
        </header>

        <div class="main-card">
            <div class="button-group">
                <button class="btn btn-primary" onclick="runAnalysis()" id="analyzeBtn">
                    <span>🔍</span>
                    分析を実行
                </button>
                <button class="btn btn-secondary" onclick="clearResults()" id="clearBtn">
                    <span>🗑️</span>
                    結果をクリア
                </button>
            </div>

            <div class="status-bar" id="statusBar" style="display: none;">
                <div class="spinner"></div>
                <span id="statusText">処理中...</span>
            </div>
        </div>

        <div class="results-section" id="resultsSection">
            <div class="resource-cards" id="resourceCards">
                <!-- 動的に生成 -->
            </div>

            <div class="analysis-card" id="analysisCard" style="display: none;">
                <div class="section-title">
                    <div class="icon" style="background: linear-gradient(135deg, var(--accent-cyan), var(--accent-orange));">🤖</div>
                    AI サイジング提案
                </div>
                <div class="analysis-content" id="analysisContent"></div>
            </div>
        </div>
    </div>

    <script>
        function getCpuClass(cpu) {
            if (cpu === null || cpu === undefined) return '';
            if (cpu < 40) return 'cpu-low';
            if (cpu < 70) return 'cpu-medium';
            return 'cpu-high';
        }

        function formatCpu(cpu) {
            if (cpu === null || cpu === undefined) return '-';
            return cpu.toFixed(2) + '%';
        }

        function formatTimestamp(ts) {
            if (!ts) return '-';
            const date = new Date(ts);
            return date.toLocaleString('ja-JP');
        }

        function showStatus(message, type) {
            const statusBar = document.getElementById('statusBar');
            const statusText = document.getElementById('statusText');
            statusBar.style.display = 'flex';
            statusBar.className = 'status-bar ' + type;
            statusText.textContent = message;
            
            if (type === 'loading') {
                statusBar.querySelector('.spinner').style.display = 'block';
            } else {
                statusBar.querySelector('.spinner').style.display = 'none';
            }
        }

        function hideStatus() {
            document.getElementById('statusBar').style.display = 'none';
        }

        // MCP から取得した動的価格データ
        let mcpPricing = { ec2: {}, rds: {}, elasticache: {}, docdb: {} };
        
        // フォールバック用の固定価格データ
        const FALLBACK_PRICES = {
            ec2: {
                't3.nano': 0.0052, 't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416, 't3.large': 0.0832,
                't3a.nano': 0.0047, 't3a.micro': 0.0094, 't3a.small': 0.0188, 't3a.medium': 0.0376, 't3a.large': 0.0752,
                't4g.nano': 0.0042, 't4g.micro': 0.0084, 't4g.small': 0.0168, 't4g.medium': 0.0336, 't4g.large': 0.0672,
                'm5.large': 0.096, 'm5.xlarge': 0.192, 'm6i.large': 0.096,
                'c5.large': 0.085, 'c5.xlarge': 0.17, 'r5.large': 0.126
            },
            rds: {
                'db.t3.micro': 0.018, 'db.t3.small': 0.036, 'db.t3.medium': 0.072, 'db.t3.large': 0.144,
                'db.t4g.micro': 0.016, 'db.t4g.small': 0.032, 'db.t4g.medium': 0.065, 'db.t4g.large': 0.129,
                'db.r5.large': 0.25, 'db.r5.xlarge': 0.50, 'db.r6g.large': 0.218
            },
            elasticache: {
                'cache.t3.micro': 0.017, 'cache.t3.small': 0.034, 'cache.t3.medium': 0.068,
                'cache.t4g.micro': 0.016, 'cache.t4g.small': 0.032, 'cache.t4g.medium': 0.064,
                'cache.r5.large': 0.24, 'cache.r6g.large': 0.218
            },
            docdb: {
                'db.t3.medium': 0.072, 'db.r5.large': 0.25, 'db.r6g.large': 0.218
            }
        };
        
        const EBS_PRICES = { 'gp2': 0.10, 'gp3': 0.08, 'io1': 0.125, 'io2': 0.125, 'st1': 0.045, 'sc1': 0.025 };

        function getInstancePrice(type, service = 'ec2') {
            // まずMCPから取得した価格をチェック
            const serviceKey = (service === 'redis' || service === 'memcache') ? 'elasticache' : service;
            if (mcpPricing[serviceKey] && mcpPricing[serviceKey][type]) {
                return mcpPricing[serviceKey][type];
            }
            // フォールバック価格を使用
            const fallbackKey = (service === 'redis' || service === 'memcache') ? 'elasticache' : service;
            if (FALLBACK_PRICES[fallbackKey] && FALLBACK_PRICES[fallbackKey][type]) {
                return FALLBACK_PRICES[fallbackKey][type];
            }
            // デフォルト価格
            if (service === 'ec2') return 0.05;
            if (service === 'rds' || service === 'docdb') return 0.10;
            return 0.05;
        }
        
        function setPricingData(pricing) {
            if (pricing) {
                mcpPricing = pricing;
                console.log('MCP pricing data loaded:', Object.keys(pricing).map(k => `${k}: ${Object.keys(pricing[k]).length} types`).join(', '));
            }
        }
        
        function getEbsPrice(type) {
            return EBS_PRICES[type] || 0.08;
        }
        
        function formatMoney(amount) {
            if (amount === null || amount === undefined) return '-';
            return '$' + amount.toFixed(2);
        }

        function createCostTable(data, service, aiRecommendations) {
            if (!data || data.length === 0) {
                return '<div class="empty-state"><div class="icon">📭</div><p>データがありません</p></div>';
            }
            
            const isEc2 = service === 'ec2';
            const HOURS_PER_MONTH = 730;
            
            let html = '<div class="cost-table-wrapper"><table class="cost-table"><thead>';
            
            // ヘッダー1行目（グループ）
            html += '<tr class="header-group">';
            html += '<th rowspan="2">名前</th>';
            if (isEc2) html += '<th rowspan="2">ID</th>';
            html += '<th colspan="' + (isEc2 ? '6' : '3') + '" class="group-current">現状</th>';
            html += '<th colspan="3" class="group-recommend">変更提案</th>';
            html += '<th rowspan="2">CPU AvgMax</th>';
            html += '<th rowspan="2">CPU Max</th>';
            html += '<th rowspan="2">AIコメント</th>';
            html += '</tr>';
            
            // ヘッダー2行目（詳細）
            html += '<tr class="header-detail">';
            html += '<th>タイプ</th><th>台数</th><th>月額</th>';
            if (isEc2) html += '<th>EBS</th><th>GB</th><th>EBS料金</th>';
            html += '<th>提案タイプ</th><th>月額</th><th>削減額</th>';
            html += '</tr></thead><tbody>';
            
            data.forEach(item => {
                const name = item.name || '-';
                const instanceId = item.instance_id || '-';
                const instanceType = item.instance_type || '-';
                const count = item.count || 1;
                const ebsType = item.ebs_type || '-';
                const ebsSize = parseInt(item.ebs_size) || 0;
                const cpuAvgMax = item.cpu_avg_max;
                const cpuMax = item.cpu_max;
                
                // 現状コスト計算
                const hourlyPrice = getInstancePrice(instanceType, service);
                const monthlyInstance = hourlyPrice * HOURS_PER_MONTH * count;
                const monthlyEbs = isEc2 ? getEbsPrice(ebsType) * ebsSize * count : 0;
                const monthlyTotal = monthlyInstance + monthlyEbs;
                
                // AI提案を検索
                const rec = aiRecommendations ? aiRecommendations.find(r => 
                    r.name === name || (item.instance_id && r.instance_id === item.instance_id)
                ) : null;
                
                const recType = rec ? rec.recommended_type : '-';
                const recPrice = rec && rec.recommended_type !== '-' ? getInstancePrice(rec.recommended_type, service) : null;
                const recMonthly = recPrice ? recPrice * HOURS_PER_MONTH * count + monthlyEbs : null;
                const savings = recMonthly !== null ? monthlyTotal - recMonthly : null;
                const aiComment = rec ? rec.note || (rec.recommended_type !== '-' ? '変更推奨' : '変更不要') : '-';
                
                html += '<tr>';
                html += `<td class="name-cell">${name}</td>`;
                if (isEc2) html += `<td class="id-cell">${instanceId !== 'None' ? instanceId : '-'}</td>`;
                html += `<td>${instanceType}</td>`;
                html += `<td class="num-cell">${count}</td>`;
                html += `<td class="money-cell">${formatMoney(monthlyInstance)}</td>`;
                if (isEc2) {
                    html += `<td>${ebsType}</td>`;
                    html += `<td class="num-cell">${ebsSize || '-'}</td>`;
                    html += `<td class="money-cell">${ebsSize ? formatMoney(monthlyEbs) : '-'}</td>`;
                }
                html += `<td class="recommend-cell">${recType}</td>`;
                html += `<td class="money-cell">${recMonthly !== null ? formatMoney(recMonthly) : '-'}</td>`;
                html += `<td class="savings-cell ${savings > 0 ? 'positive' : ''}">${savings !== null && savings > 0 ? '-' + formatMoney(savings) + '/月' : '-'}</td>`;
                html += `<td><span class="cpu-badge ${getCpuClass(cpuAvgMax)}">${formatCpu(cpuAvgMax)}</span></td>`;
                html += `<td><span class="cpu-badge ${getCpuClass(cpuMax)}">${formatCpu(cpuMax)}</span></td>`;
                html += `<td class="ai-comment-cell">${aiComment}</td>`;
                html += '</tr>';
            });
            
            html += '</tbody></table></div>';
            return html;
        }

        function createTable(data, columns) {
            if (!data || data.length === 0) {
                return '<div class="empty-state"><div class="icon">📭</div><p>データがありません</p></div>';
            }

            let html = '<table class="data-table"><thead><tr>';
            columns.forEach(col => {
                html += `<th>${col.label}</th>`;
            });
            html += '</tr></thead><tbody>';

            data.forEach(item => {
                html += '<tr>';
                columns.forEach(col => {
                    let value = item[col.key];
                    if (col.key === 'cpu_avg_max' || col.key === 'cpu_max' || col.key === 'max_cpu') {
                        const cpuClass = getCpuClass(value);
                        html += `<td><span class="cpu-badge ${cpuClass}">${formatCpu(value)}</span></td>`;
                    } else if (col.key === 'timestamp' || col.key === 'max_cpu_time') {
                        html += `<td class="timestamp">${formatTimestamp(value)}</td>`;
                    } else {
                        html += `<td>${value ?? '-'}</td>`;
                    }
                });
                html += '</tr>';
            });

            html += '</tbody></table>';
            return html;
        }

        // グローバル変数
        let globalAiRecommendations = {};
        let globalResources = null;
        
        // AI分析結果から提案を抽出
        function parseAiRecommendations(analysisText) {
            const recommendations = { ec2: [], rds: [], redis: [], memcache: [], docdb: [] };
            if (!analysisText) return recommendations;
            
            const lines = analysisText.split('\\n');
            let currentSection = null;
            let currentInstance = null;
            
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                
                // セクション検出
                if (line.includes('### EC2')) currentSection = 'ec2';
                else if (line.includes('### RDS')) currentSection = 'rds';
                else if (line.includes('### DocumentDB')) currentSection = 'docdb';
                else if (line.includes('### Redis')) currentSection = 'redis';
                else if (line.includes('### Memcached')) currentSection = 'memcache';
                
                // インスタンス名を検出（**name**: 形式）
                const nameMatch = line.match(/^-\\s*\\*\\*(?:インスタンス名|クラスター名)?\\s*:?\\*\\*:?\\s*(.+)/);
                if (nameMatch && currentSection) {
                    currentInstance = {
                        name: nameMatch[1].trim().replace(/\\*\\*/g, ''),
                        recommended_type: '-',
                        note: '',
                        judgment: ''
                    };
                }
                
                // 判定行を検出
                if (currentInstance && line.includes('判定:')) {
                    const judgmentMatch = line.match(/判定:\\s*(.+)/);
                    if (judgmentMatch) {
                        const judgment = judgmentMatch[1].trim();
                        if (judgment.includes('過剰')) {
                            currentInstance.judgment = '過剰スペック';
                        } else if (judgment.includes('適正')) {
                            currentInstance.judgment = '適正';
                        } else if (judgment.includes('不足')) {
                            currentInstance.judgment = 'スペック不足';
                        }
                    }
                }
                
                // 提案行を検出
                if (currentInstance && line.includes('提案:')) {
                    const proposalMatch = line.match(/提案:\\s*(.+)/);
                    if (proposalMatch) {
                        const proposal = proposalMatch[1].trim();
                        
                        // スペック不足の場合は変更提案しない（コメントのみ）
                        if (currentInstance.judgment === 'スペック不足') {
                            currentInstance.recommended_type = '-';
                            currentInstance.note = 'スペック不足';
                        } else if (proposal.includes('変更不要') || proposal.includes('維持')) {
                            currentInstance.note = currentInstance.judgment || '適正';
                        } else {
                            // タイプ抽出 (t3.medium, db.t3.medium, cache.t3.medium など) - スケールダウンのみ
                            const typeMatch = proposal.match(/((?:db\\.|cache\\.)?[a-z][a-z0-9]*\\.[a-z0-9]+)/i);
                            if (typeMatch) {
                                currentInstance.recommended_type = typeMatch[1];
                                currentInstance.note = currentInstance.judgment || '過剰スペック';
                            } else {
                                currentInstance.note = currentInstance.judgment || proposal.substring(0, 20);
                            }
                        }
                        
                        // 現在のセクションに追加
                        if (currentSection && currentInstance.name) {
                            recommendations[currentSection].push({...currentInstance});
                        }
                        currentInstance = null;
                    }
                }
            }
            
            return recommendations;
        }

        function renderResources(resources, aiRecommendations = null) {
            const container = document.getElementById('resourceCards');
            container.innerHTML = '';

            // グローバルに保存
            globalResources = resources;
            if (aiRecommendations) {
                globalAiRecommendations = aiRecommendations;
            }

            const sections = [
                { key: 'ec2', title: 'EC2 インスタンス', emoji: '💻' },
                { key: 'rds', title: 'RDS クラスター', emoji: '🗄️' },
                { key: 'redis', title: 'Redis (ElastiCache)', emoji: '⚡' },
                { key: 'memcache', title: 'Memcached (ElastiCache)', emoji: '🚀' },
                { key: 'docdb', title: 'DocumentDB', emoji: '📑' }
            ];

            sections.forEach(section => {
                const data = resources[section.key];
                if (data && data.length > 0) {
                    const recs = globalAiRecommendations[section.key] || [];
                    const card = document.createElement('div');
                    card.className = 'resource-card';
                    card.innerHTML = `
                        <div class="resource-card-header">
                            <div class="section-title">
                                <div class="icon ${section.key}">${section.emoji}</div>
                                ${section.title}
                                <span style="color: var(--text-secondary); font-weight: 400; font-size: 0.9rem;">(${data.length}件)</span>
                            </div>
                        </div>
                        <div class="resource-card-body">
                            ${createCostTable(data, section.key, recs)}
                        </div>
                    `;
                    container.appendChild(card);
                }
            });

            document.getElementById('resultsSection').classList.add('visible');
        }

        function renderAnalysis(text, tokenUsage = null) {
            const card = document.getElementById('analysisCard');
            const content = document.getElementById('analysisContent');
            content.textContent = text;
            card.style.display = 'block';
            
            // AI提案を抽出してリソース表示を更新
            const recommendations = parseAiRecommendations(text);
            if (globalResources) {
                renderResources(globalResources, recommendations);
            }
            
            // トークン使用量を表示
            let costHtml = document.getElementById('tokenUsageInfo');
            if (!costHtml) {
                costHtml = document.createElement('div');
                costHtml.id = 'tokenUsageInfo';
                costHtml.style.cssText = 'margin-top: 1rem; padding: 0.75rem 1rem; background: var(--bg-secondary); border-radius: 6px; font-size: 0.85rem; color: var(--text-secondary); display: flex; gap: 1.5rem; flex-wrap: wrap;';
                card.appendChild(costHtml);
            }
            
            if (tokenUsage) {
                const inputTokens = tokenUsage.input_tokens || 0;
                const outputTokens = tokenUsage.output_tokens || 0;
                const totalTokens = tokenUsage.total_tokens || 0;
                const costUsd = tokenUsage.total_cost_usd || 0;
                const costJpy = tokenUsage.total_cost_jpy || 0;
                
                costHtml.innerHTML = `
                    <span>📊 <strong>トークン:</strong> ${inputTokens.toLocaleString()} in + ${outputTokens.toLocaleString()} out = ${totalTokens.toLocaleString()} total</span>
                    <span>💰 <strong>コスト:</strong> $${costUsd.toFixed(6)} (約${costJpy.toFixed(4)}円)</span>
                    <span>🤖 <strong>モデル:</strong> ${tokenUsage.model_id || 'N/A'}</span>
                `;
                costHtml.style.display = 'flex';
            } else {
                costHtml.style.display = 'none';
            }
        }

        async function runAnalysis() {
            const analyzeBtn = document.getElementById('analyzeBtn');
            analyzeBtn.disabled = true;

            try {
                showStatus('AWSリソース情報を収集中...', 'loading');
                
                const response = await fetch(window.location.href, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ action: 'analyze' })
                });

                if (!response.ok) {
                    throw new Error('API request failed');
                }

                const data = await response.json();
                
                // MCP から取得した価格データを設定
                if (data.pricing) {
                    setPricingData(data.pricing);
                }
                
                showStatus('リソース情報を表示中...', 'loading');
                renderResources(data.resources);

                if (data.analysis) {
                    renderAnalysis(data.analysis, data.token_usage);
                }

                showStatus('分析が完了しました', 'success');
                setTimeout(hideStatus, 3000);

            } catch (error) {
                console.error('Error:', error);
                showStatus('エラーが発生しました: ' + error.message, 'error');
            } finally {
                analyzeBtn.disabled = false;
            }
        }

        function clearResults() {
            document.getElementById('resourceCards').innerHTML = '';
            document.getElementById('analysisCard').style.display = 'none';
            document.getElementById('resultsSection').classList.remove('visible');
            hideStatus();
        }

        // ページ読み込み時の処理
        document.addEventListener('DOMContentLoaded', function() {
            console.log('Page loaded');
        });
    </script>
</body>
</html>'''


def lambda_handler(event, context):
    """Lambda関数のメインハンドラー"""
    
    # Function URLからのリクエストを処理
    http_method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    
    # CORSヘッダー（キャッシュ無効化含む）
    headers = {
        'Content-Type': 'text/html; charset=utf-8',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    
    # OPTIONSリクエスト（CORS preflight）
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': ''
        }
    
    # GETリクエスト - HTMLまたはスクリプトを返す
    if http_method == 'GET':
        # パスをチェック
        path = event.get('rawPath', '') or event.get('requestContext', {}).get('http', {}).get('path', '')
        
        # 通常のHTMLページ
        return {
            'statusCode': 200,
            'headers': headers,
            'body': get_html_template()
        }
    
    # POSTリクエスト - 分析を実行
    if http_method == 'POST':
        headers['Content-Type'] = 'application/json'
        
        try:
            # リクエストボディをパース
            body = {}
            if event.get('body'):
                body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            
            # リソース情報を収集
            resources = collect_all_resources()
            
            # MCP サーバーから価格情報を取得
            pricing_info = collect_pricing_info(resources)
            
            # Bedrock用にフォーマット（価格情報含む）
            resource_text = format_resources_for_bedrock(resources, pricing_info)
            
            # Bedrockで分析
            analysis_result = get_bedrock_analysis(resource_text)
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'resources': resources,
                    'pricing': pricing_info,
                    'analysis': analysis_result['text'],
                    'token_usage': analysis_result['token_usage']
                }, ensure_ascii=False, default=str)
            }
            
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({
                    'error': str(e)
                }, ensure_ascii=False)
            }
    
    # その他のメソッド
    return {
        'statusCode': 405,
        'headers': headers,
        'body': 'Method Not Allowed'
    }

