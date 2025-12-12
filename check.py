import boto3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# CloudWatchから最大CPU使用率を取得（30日間、5分平均）
def get_max_cpu_utilization(instance_id, namespace='AWS/EC2', dimension_name='InstanceId'):
    cloudwatch = boto3.client('cloudwatch')

    period = 300  # 5分の期間
    days = 30  # 取得する期間（30日）

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    max_avg_cpu = 0.0
    max_avg_cpu_timestamp = None
    max_cpu = 0.0
    max_cpu_timestamp = None
    
    interval = timedelta(days=5)
    current_start = start_time

    #all_datapoints = []  # すべてのデータポイントを格納するリスト

    while current_start < end_time:
        current_end = min(current_start + interval, end_time)

        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName='CPUUtilization',
            Dimensions=[{'Name': dimension_name, 'Value': instance_id}],
            StartTime=current_start,
            EndTime=current_end,
            Period=period,
            Statistics=['Average', 'Maximum'],
            Unit='Percent'
        )

        datapoints = response.get('Datapoints', [])

        #all_datapoints.extend(datapoints)

        # 各データポイントを表示（インスタンスIDとオートスケールグループ名も表示）
        # for dp in datapoints:
        #     print(f"Instance ID: {instance_id}")
        #     print(f"Timestamp: {dp['Timestamp']}, Average CPU: {dp['Average']}%")

        # 最大CPU使用率の計算（平均値と最大値の両方）
        for dp in datapoints:
            # 平均値の最大値を追跡
            if 'Average' in dp and dp['Average'] > max_avg_cpu:
                max_avg_cpu = dp['Average']
                max_avg_cpu_timestamp = dp['Timestamp']
            
            # 最大値統計の最大値を追跡
            if 'Maximum' in dp and dp['Maximum'] > max_cpu:
                max_cpu = dp['Maximum']
                max_cpu_timestamp = dp['Timestamp']

        current_start = current_end
    
    max_avg_cpu_result = round(max_avg_cpu, 2) if max_avg_cpu > 0 else None
    max_cpu_result = round(max_cpu, 2) if max_cpu > 0 else None
    
    return (max_avg_cpu_result, max_avg_cpu_timestamp, max_cpu_result, max_cpu_timestamp)

# CloudWatchから最大メモリ使用率を取得（30日間、5分平均）
def get_max_memory_utilization(instance_id, namespace='AWS/ElastiCache', dimension_name='CacheClusterId'):
    cloudwatch = boto3.client('cloudwatch')

    period = 300  # 5分の期間
    days = 30  # 取得する期間（30日）

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    max_avg_memory = 0.0
    max_avg_memory_timestamp = None
    max_memory = 0.0
    max_memory_timestamp = None
    
    interval = timedelta(days=5)
    current_start = start_time

    while current_start < end_time:
        current_end = min(current_start + interval, end_time)

        # Redisの場合はDatabaseMemoryUsagePercentageを使用
        # Memcachedの場合はFreeableMemoryとCacheClusterMemoryから計算
        try:
            response = cloudwatch.get_metric_statistics(
                Namespace=namespace,
                MetricName='DatabaseMemoryUsagePercentage',
                Dimensions=[{'Name': dimension_name, 'Value': instance_id}],
                StartTime=current_start,
                EndTime=current_end,
                Period=period,
                Statistics=['Average', 'Maximum'],
                Unit='Percent'
            )

            datapoints = response.get('Datapoints', [])

            # 最大メモリ使用率の計算（平均値と最大値の両方）
            for dp in datapoints:
                # 平均値の最大値を追跡
                if 'Average' in dp and dp['Average'] > max_avg_memory:
                    max_avg_memory = dp['Average']
                    max_avg_memory_timestamp = dp['Timestamp']
                
                # 最大値統計の最大値を追跡
                if 'Maximum' in dp and dp['Maximum'] > max_memory:
                    max_memory = dp['Maximum']
                    max_memory_timestamp = dp['Timestamp']
        except Exception:
            # DatabaseMemoryUsagePercentageが利用できない場合（Memcachedなど）、
            # FreeableMemoryとCacheClusterMemoryから計算を試みる
            try:
                # FreeableMemoryを取得
                freeable_response = cloudwatch.get_metric_statistics(
                    Namespace=namespace,
                    MetricName='FreeableMemory',
                    Dimensions=[{'Name': dimension_name, 'Value': instance_id}],
                    StartTime=current_start,
                    EndTime=current_end,
                    Period=period,
                    Statistics=['Average', 'Maximum'],
                    Unit='Bytes'
                )
                
                # CacheClusterMemoryを取得
                total_response = cloudwatch.get_metric_statistics(
                    Namespace=namespace,
                    MetricName='CacheClusterMemory',
                    Dimensions=[{'Name': dimension_name, 'Value': instance_id}],
                    StartTime=current_start,
                    EndTime=current_end,
                    Period=period,
                    Statistics=['Average', 'Maximum'],
                    Unit='Bytes'
                )
                
                freeable_datapoints = freeable_response.get('Datapoints', [])
                total_datapoints = total_response.get('Datapoints', [])
                
                # タイムスタンプでマッチングしてメモリ使用率を計算
                freeable_dict = {dp['Timestamp']: dp for dp in freeable_datapoints}
                total_dict = {dp['Timestamp']: dp for dp in total_datapoints}
                
                for timestamp in set(freeable_dict.keys()) & set(total_dict.keys()):
                    freeable_avg = freeable_dict[timestamp].get('Average', 0)
                    total_avg = total_dict[timestamp].get('Average', 0)
                    freeable_max = freeable_dict[timestamp].get('Maximum', 0)
                    total_max = total_dict[timestamp].get('Maximum', 0)
                    
                    if total_avg > 0:
                        memory_usage_avg = ((total_avg - freeable_avg) / total_avg) * 100
                        if memory_usage_avg > max_avg_memory:
                            max_avg_memory = memory_usage_avg
                            max_avg_memory_timestamp = timestamp
                    
                    if total_max > 0:
                        memory_usage_max = ((total_max - freeable_max) / total_max) * 100
                        if memory_usage_max > max_memory:
                            max_memory = memory_usage_max
                            max_memory_timestamp = timestamp
            except Exception:
                # メモリ使用率が取得できない場合はNoneを返す
                pass

        current_start = current_end
    
    max_avg_memory_result = round(max_avg_memory, 2) if max_avg_memory > 0 else None
    max_memory_result = round(max_memory, 2) if max_memory > 0 else None
    
    return (max_avg_memory_result, max_avg_memory_timestamp, max_memory_result, max_memory_timestamp)

def get_ec2_instances():
    ec2 = boto3.client("ec2")
    
    response = ec2.describe_instances()
    instances_info = []
    instance_data = defaultdict(lambda: {"count": 0, "ebs_info": set(), "instance_ids": [], "auto_scaling_group": None})

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            # インスタンスステータスが終了済みの場合、スキップ
            if instance["State"]["Name"] == "terminated":
                continue

            if instance["State"]["Name"] == "stopped":
                continue
            
            instance_id = instance["InstanceId"]
            instance_type = instance["InstanceType"]
            
            # インスタンス名の取得
            instance_name = "N/A"
            for tag in instance.get("Tags", []):
                if tag["Key"] == "Name":
                    instance_name = tag["Value"]
                    break
            
            # AutoScalingグループ名の取得（ある場合）
            auto_scaling_group_name = None
            for tag in instance.get("Tags", []):
                if tag["Key"] == "aws:autoscaling:groupName":
                    auto_scaling_group_name = tag["Value"]
                    break
            
            # インスタンス名とインスタンスタイプごとに集計
            key = (instance_name, instance_type)
            instance_data[key]["count"] += 1
            instance_data[key]["instance_ids"].append(instance_id)  # インスタンスIDをリストに追加
            instance_data[key]["auto_scaling_group"] = auto_scaling_group_name  # Auto Scaling グループ名を追加
            
            # EBS情報の取得
            for block_device in instance.get("BlockDeviceMappings", []):
                volume_id = block_device.get("Ebs", {}).get("VolumeId", "N/A")
                if volume_id != "N/A":
                    volume = ec2.describe_volumes(VolumeIds=[volume_id])["Volumes"][0]
                    ebs_type = volume["VolumeType"]
                    storage_size = volume["Size"]
                    instance_data[key]["ebs_info"].add((ebs_type, storage_size))  # setで重複防止
    
    # 結果の整理 + CPU使用率の取得
    for (instance_name, instance_type), data in instance_data.items():
        count = data["count"]
        ebs_info = data["ebs_info"]
        instance_ids = data["instance_ids"]
        auto_scaling_group_name = data["auto_scaling_group"]

        # 表示するインスタンスIDの設定
        instance_id_display = instance_ids[0] if count == 1 else None

        # インスタンスIDがNoneの場合、Auto Scaling グループ名でCPU使用率を取得
        max_avg_cpu = 0.0
        max_avg_cpu_timestamp = None
        max_cpu = 0.0
        max_cpu_timestamp = None

        if auto_scaling_group_name:
            max_avg_cpu, max_avg_cpu_ts, max_cpu, max_cpu_ts = get_max_cpu_utilization(auto_scaling_group_name, namespace='AWS/EC2', dimension_name='AutoScalingGroupName')
            if max_avg_cpu_ts:
                max_avg_cpu_timestamp = max_avg_cpu_ts
            if max_cpu_ts:
                max_cpu_timestamp = max_cpu_ts
        elif instance_ids:
            cpu_usages = [get_max_cpu_utilization(iid) for iid in instance_ids]
            for avg_cpu, avg_ts, cpu, ts in cpu_usages:
                if avg_cpu is not None and avg_cpu > max_avg_cpu:
                    max_avg_cpu = avg_cpu
                    max_avg_cpu_timestamp = avg_ts
                if cpu is not None and cpu > max_cpu:
                    max_cpu = cpu
                    max_cpu_timestamp = ts
        else:
            max_avg_cpu = None
            max_avg_cpu_timestamp = None
            max_cpu = None
            max_cpu_timestamp = None


        if ebs_info:
            for ebs in ebs_info:
                instances_info.append([
                    instance_name,
                    instance_id_display,
                    instance_type,
                    count,
                    ebs[0],
                    ebs[1],
                    max_avg_cpu,
                    max_avg_cpu_timestamp.isoformat() if max_avg_cpu_timestamp else "N/A",
                    max_cpu,
                    max_cpu_timestamp.isoformat() if max_cpu_timestamp else "N/A"
                ])

    return instances_info


def get_rds_clusters():
    rds = boto3.client("rds")
    clusters_info = []

    # RDS クラスターの情報を取得
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

        if len(instance_types) == 0:
            instance_type_display = "N/A"
        elif len(instance_types) > 1:
            instance_type_display = ", ".join(sorted(instance_types))
        else:
            instance_type_display = next(iter(instance_types))
        max_avg_cpu, max_avg_cpu_ts, max_cpu, max_cpu_ts = get_max_cpu_utilization(cluster_name, namespace='AWS/RDS', dimension_name='DBClusterIdentifier')

        clusters_info.append([cluster_name, instance_type_display, node_count, max_avg_cpu, max_avg_cpu_ts.isoformat() if max_avg_cpu_ts else None, max_cpu, max_cpu_ts.isoformat() if max_cpu_ts else None])

    # 単体のRDSインスタンス情報（クラスターに属していないもの）を取得
    response = rds.describe_db_instances()
    for instance in response["DBInstances"]:
        instance_id = instance["DBInstanceIdentifier"]
        if instance_id in cluster_instance_ids:
            continue  # 既にクラスターで処理済みのインスタンスはスキップ

        if instance["Engine"] == "docdb":
            continue

        instance_type = instance["DBInstanceClass"]
        max_avg_cpu, max_avg_cpu_ts, max_cpu, max_cpu_ts = get_max_cpu_utilization(instance_id, namespace='AWS/RDS', dimension_name='DBInstanceIdentifier')
        clusters_info.append([instance_id, instance_type, 1, max_avg_cpu, max_avg_cpu_ts.isoformat() if max_avg_cpu_ts else None, max_cpu, max_cpu_ts.isoformat() if max_cpu_ts else None])

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
        
        if len(instance_types) == 0:
            instance_type_display = "N/A"
        elif len(instance_types) > 1:
            instance_type_display = ", ".join(sorted(instance_types))
        else:
            instance_type_display = next(iter(instance_types))
        
        node_count = len(cluster["DBClusterMembers"])
        max_avg_cpu, max_avg_cpu_ts, max_cpu, max_cpu_ts = get_max_cpu_utilization(cluster_name, namespace='AWS/DocDB', dimension_name='DBClusterIdentifier')
        clusters_info.append([cluster_name, instance_type_display, node_count, max_avg_cpu, max_avg_cpu_ts.isoformat() if max_avg_cpu_ts else None, max_cpu, max_cpu_ts.isoformat() if max_cpu_ts else None])
    
    return clusters_info

def get_redis_clusters():
    elasticache = boto3.client("elasticache")
    response = elasticache.describe_replication_groups()
    clusters_info = []

    for cluster in response["ReplicationGroups"]:
        cluster_name = cluster["ReplicationGroupId"]
        instance_type = cluster["CacheNodeType"]
        node_count = len(cluster["MemberClusters"])

        max_avg_cpu = 0.0
        max_avg_cpu_timestamp = None
        max_cpu = 0.0
        max_cpu_timestamp = None
        max_avg_memory = 0.0
        max_avg_memory_timestamp = None
        max_memory = 0.0
        max_memory_timestamp = None
        
        for node_id in cluster["MemberClusters"]:
            avg_cpu, avg_ts, cpu, ts = get_max_cpu_utilization(
                node_id,
                namespace='AWS/ElastiCache',
                dimension_name='CacheClusterId'
            )
            if avg_cpu is not None and avg_cpu > max_avg_cpu:
                max_avg_cpu = avg_cpu
                max_avg_cpu_timestamp = avg_ts
            if cpu is not None and cpu > max_cpu:
                max_cpu = cpu
                max_cpu_timestamp = ts
            
            avg_memory, avg_mem_ts, memory, mem_ts = get_max_memory_utilization(
                node_id,
                namespace='AWS/ElastiCache',
                dimension_name='CacheClusterId'
            )
            if avg_memory is not None and avg_memory > max_avg_memory:
                max_avg_memory = avg_memory
                max_avg_memory_timestamp = avg_mem_ts
            if memory is not None and memory > max_memory:
                max_memory = memory
                max_memory_timestamp = mem_ts

        clusters_info.append([
            cluster_name,
            instance_type,
            node_count,
            max_avg_cpu,
            max_avg_cpu_timestamp.isoformat() if max_avg_cpu_timestamp else None,
            max_cpu,
            max_cpu_timestamp.isoformat() if max_cpu_timestamp else None,
            max_avg_memory,
            max_avg_memory_timestamp.isoformat() if max_avg_memory_timestamp else None,
            max_memory,
            max_memory_timestamp.isoformat() if max_memory_timestamp else None
        ])

    return clusters_info

def get_memcache_clusters():
    elasticache = boto3.client("elasticache")
    response = elasticache.describe_cache_clusters()
    clusters_info = []

    for cluster in response["CacheClusters"]:
        # Memcachedクラスターのみを対象とする
        if cluster["Engine"] != "memcached":
            continue
            
        cluster_name = cluster["CacheClusterId"]
        instance_type = cluster["CacheNodeType"]
        node_count = cluster["NumCacheNodes"]
        
        # CPU使用率を取得
        max_avg_cpu, max_avg_cpu_ts, max_cpu, max_cpu_ts = get_max_cpu_utilization(
            cluster_name,
            namespace='AWS/ElastiCache',
            dimension_name='CacheClusterId'
        )
        
        # メモリ使用率を取得
        max_avg_memory, max_avg_memory_ts, max_memory, max_memory_ts = get_max_memory_utilization(
            cluster_name,
            namespace='AWS/ElastiCache',
            dimension_name='CacheClusterId'
        )

        clusters_info.append([
            cluster_name,
            instance_type,
            node_count,
            max_avg_cpu,
            max_avg_cpu_ts.isoformat() if max_avg_cpu_ts else None,
            max_cpu,
            max_cpu_ts.isoformat() if max_cpu_ts else None,
            max_avg_memory,
            max_avg_memory_ts.isoformat() if max_avg_memory_ts else None,
            max_memory,
            max_memory_ts.isoformat() if max_memory_ts else None
        ])

    return clusters_info

def get_cost_optimization_recommendations():
    """
    AWS Cost Optimization Hubから削減提案を取得
    Cost Optimization Hubはus-east-1リージョンで利用します
    ActionType別にグループ化して返します
    """
    recommendations_by_action = defaultdict(list)
    
    try:
        # us-east-1リージョンでCost Optimization Hubに接続
        cost_optimization = boto3.client('cost-optimization-hub', region_name='us-east-1')
        
        # 推奨事項の一覧を取得
        paginator = cost_optimization.get_paginator('list_recommendations')
        
        for page in paginator.paginate():
            recommendations = page.get('items', [])
            
            for rec in recommendations:
                resource_id = rec.get('resourceId') or rec.get('resourceArn', 'N/A')
                resource_type = rec.get('resourceType', '')
                current_resource_type = rec.get('currentResourceType', '')
                action_type = rec.get('actionType', 'N/A')
                
                # リソース名を取得（resourceIdから抽出、またはタグから取得を試みる）
                resource_name = resource_id
                if resource_id and resource_id != 'N/A':
                    # リソースIDから名前を抽出（例: i-xxx -> インスタンス名を取得）
                    # または、resourceIdが名前の形式の場合
                    if '/' in resource_id:
                        # スラッシュ区切りの場合は最後の部分を名前として使用
                        resource_name = resource_id.split('/')[-1]
                    elif resource_id.startswith('i-'):
                        # EC2インスタンスIDの場合、名前を取得を試みる
                        try:
                            ec2 = boto3.client('ec2')
                            response = ec2.describe_instances(InstanceIds=[resource_id])
                            for reservation in response.get('Reservations', []):
                                for instance in reservation.get('Instances', []):
                                    for tag in instance.get('Tags', []):
                                        if tag.get('Key') == 'Name':
                                            resource_name = tag.get('Value', resource_id)
                                            break
                        except Exception:
                            resource_name = resource_id
                    elif resource_id.startswith('vol-'):
                        # EBSボリュームIDの場合
                        try:
                            ec2 = boto3.client('ec2')
                            response = ec2.describe_volumes(VolumeIds=[resource_id])
                            for volume in response.get('Volumes', []):
                                for tag in volume.get('Tags', []):
                                    if tag.get('Key') == 'Name':
                                        resource_name = tag.get('Value', resource_id)
                                        break
                        except Exception:
                            resource_name = resource_id
                    else:
                        resource_name = resource_id
                
                # 現在の費用を取得
                estimated_monthly_cost = rec.get('estimatedMonthlyCost', {})
                if isinstance(estimated_monthly_cost, dict) and estimated_monthly_cost:
                    current_cost_amount = estimated_monthly_cost.get('amount', '')
                    current_cost_currency = estimated_monthly_cost.get('currency', 'USD')
                    current_cost_display = f"{current_cost_currency} {current_cost_amount}" if current_cost_amount else ''
                else:
                    current_cost_display = ''
                    current_cost_amount = ''
                
                # 推定削減額を取得（複数の可能性を確認）
                estimated_monthly_savings = rec.get('estimatedMonthlySavings')
                savings_amount = ''
                savings_currency = 'USD'
                
                if estimated_monthly_savings is None:
                    # estimatedMonthlySavingsが存在しない場合、他のフィールドを確認
                    pass
                elif isinstance(estimated_monthly_savings, dict):
                    # 辞書形式の場合
                    savings_amount = estimated_monthly_savings.get('amount', '')
                    savings_currency = estimated_monthly_savings.get('currency', 'USD')
                elif isinstance(estimated_monthly_savings, (int, float)):
                    # 数値の場合
                    savings_amount = str(estimated_monthly_savings)
                elif estimated_monthly_savings:
                    # その他の場合（文字列など）
                    savings_amount = str(estimated_monthly_savings)
                
                # 金額の表示形式を決定
                if savings_amount:
                    try:
                        # 数値として扱える場合は、通貨と金額を表示
                        savings_float = float(savings_amount)
                        savings_display = f"{savings_currency} {savings_float:.2f}"
                    except (ValueError, TypeError):
                        # 数値でない場合はそのまま表示
                        savings_display = f"{savings_currency} {savings_amount}"
                else:
                    savings_display = ''
                
                # 推定削減率を取得（APIレスポンスから直接取得、なければ計算）
                estimated_savings_percentage = rec.get('estimatedSavingsPercentage', '')
                if not estimated_savings_percentage:
                    # APIレスポンスにない場合は計算
                    if current_cost_amount and savings_amount:
                        try:
                            current_cost_float = float(current_cost_amount)
                            savings_float = float(savings_amount)
                            if current_cost_float > 0:
                                percentage = (savings_float / current_cost_float) * 100
                                estimated_savings_percentage = f"{percentage:.1f}%"
                        except (ValueError, TypeError):
                            estimated_savings_percentage = ''
                else:
                    # APIレスポンスの値をパーセンテージ形式に変換
                    try:
                        if isinstance(estimated_savings_percentage, (int, float)):
                            estimated_savings_percentage = f"{estimated_savings_percentage:.1f}%"
                        elif isinstance(estimated_savings_percentage, str) and not estimated_savings_percentage.endswith('%'):
                            estimated_savings_percentage = f"{estimated_savings_percentage}%"
                    except (ValueError, TypeError):
                        estimated_savings_percentage = ''
                
                # 推奨事項の詳細を取得
                description = rec.get('description', '')
                reason = rec.get('reason', '')
                
                # 現在の設定と推奨設定から有用な情報を抽出
                current_config = rec.get('currentConfiguration', {})
                recommended_config = rec.get('recommendedConfiguration', {})
                
                # 設定情報から有用な情報を抽出（空でない場合のみ）
                current_config_info = []
                recommended_config_info = []
                
                if current_config:
                    # インスタンスタイプやボリュームタイプなど、有用な情報を抽出
                    if 'instanceType' in current_config:
                        current_config_info.append(f"InstanceType: {current_config['instanceType']}")
                    if 'volumeType' in current_config:
                        current_config_info.append(f"VolumeType: {current_config['volumeType']}")
                    if 'size' in current_config:
                        current_config_info.append(f"Size: {current_config['size']}")
                    if 'platform' in current_config:
                        current_config_info.append(f"Platform: {current_config['platform']}")
                
                if recommended_config:
                    if 'instanceType' in recommended_config:
                        recommended_config_info.append(f"InstanceType: {recommended_config['instanceType']}")
                    if 'volumeType' in recommended_config:
                        recommended_config_info.append(f"VolumeType: {recommended_config['volumeType']}")
                    if 'size' in recommended_config:
                        recommended_config_info.append(f"Size: {recommended_config['size']}")
                    if 'platform' in recommended_config:
                        recommended_config_info.append(f"Platform: {recommended_config['platform']}")
                
                current_config_str = ', '.join(current_config_info) if current_config_info else ''
                recommended_config_str = ', '.join(recommended_config_info) if recommended_config_info else ''
                
                # 説明と理由（空でない場合のみ）
                description_str = description[:200] if description else ''
                reason_str = reason[:200] if reason else ''
                
                # 実際に値がある情報のみを含める
                recommendations_by_action[action_type].append({
                    'resource_id': resource_id,
                    'resource_name': resource_name,
                    'resource_type': resource_type,
                    'current_resource_type': current_resource_type,
                    'action_type': action_type,
                    'current_cost': current_cost_display,
                    'estimated_monthly_savings': savings_display,
                    'estimated_savings_percentage': estimated_savings_percentage,
                    'description': description_str,
                    'reason': reason_str,
                    'current_config': current_config_str,
                    'recommended_config': recommended_config_str
                })
                
    except Exception as e:
        # Cost Optimization Hubが利用できない場合やエラーが発生した場合
        recommendations_by_action['Error'].append({
            'resource_id': 'Error',
            'resource_name': 'Error',
            'resource_type': '',
            'current_resource_type': '',
            'action_type': 'Error',
            'current_cost': '',
            'estimated_monthly_savings': '',
            'estimated_savings_percentage': '',
            'description': f'Failed to retrieve recommendations from Cost Optimization Hub (us-east-1): {str(e)}',
            'reason': '',
            'current_config': '',
            'recommended_config': ''
        })
    
    return recommendations_by_action

import sys
def main():
    ec2_instances = get_ec2_instances()
    rds_clusters = get_rds_clusters()
    docdb_clusters = get_docdb_clusters()
    redis_clusters = get_redis_clusters()
    memcache_clusters = get_memcache_clusters()
    cost_recommendations = get_cost_optimization_recommendations()

    with open("output.txt", "w", encoding="utf-8") as f:

        sys.stdout = f

        print("\nEC2 :")
        print("Instance Name\tInstance ID\tInstance Type\t台数\tEBS Type\tEBS Size\tMax Avg CPU\tMax Avg CPU Time\tMax CPU\tMax CPU Time")
        for instance in ec2_instances:
            print("\t".join(map(str, instance)))

        print("\nRedis :")
        print("Cluster Name\tInstance Type\t台数\tMax Avg CPU\tMax Avg CPU Time\tMax CPU\tMax CPU Time\tMax Avg Memory\tMax Avg Memory Time\tMax Memory\tMax Memory Time")
        for cluster in redis_clusters:
            print("\t".join(map(str, cluster)))

        print("\nMemcached :")
        print("Cluster Name\tInstance Type\t台数\tMax Avg CPU\tMax Avg CPU Time\tMax CPU\tMax CPU Time\tMax Avg Memory\tMax Avg Memory Time\tMax Memory\tMax Memory Time")
        for cluster in memcache_clusters:
            print("\t".join(map(str, cluster)))

        print("\nRDS :")
        print("Cluster Name\tInstance Type\t台数\tMax Avg CPU\tMax Avg CPU Time\tMax CPU\tMax CPU Time")
        for cluster in rds_clusters:
            print("\t".join(map(str, cluster)))

        print("\nDocumentDB :")
        print("Cluster Name\tInstance Type\t台数\tMax Avg CPU\tMax Avg CPU Time\tMax CPU\tMax CPU Time")
        for cluster in docdb_clusters:
            print("\t".join(map(str, cluster)))

        print("\n削減提案 :")
        # ActionType別にグループ化して表示
        for action_type in sorted(cost_recommendations.keys()):
            recommendations = cost_recommendations[action_type]
            if recommendations:
                print(f"\nAction Type: {action_type}")
                # resourceId、estimatedMonthlySavings、estimatedSavingsPercentage、currentResourceTypeを表示
                headers = ["Resource ID", "Estimated Monthly Savings", "Estimated Savings Percentage"]
                has_current_resource_type = any(r.get('current_resource_type') for r in recommendations)
                has_resource_type = any(r.get('resource_type') for r in recommendations)
                has_description = any(r.get('description') for r in recommendations)
                has_reason = any(r.get('reason') for r in recommendations)
                has_current_config = any(r.get('current_config') for r in recommendations)
                has_recommended_config = any(r.get('recommended_config') for r in recommendations)
                
                if has_current_resource_type:
                    headers.append("Current Resource Type")
                if has_resource_type:
                    headers.append("Resource Type")
                if has_description:
                    headers.append("Description")
                if has_reason:
                    headers.append("Reason")
                if has_current_config:
                    headers.append("Current Configuration")
                if has_recommended_config:
                    headers.append("Recommended Configuration")
                
                print("\t".join(headers))
                
                for rec in recommendations:
                    row = [
                        rec.get('resource_id', ''),
                        rec.get('estimated_monthly_savings', ''),
                        rec.get('estimated_savings_percentage', '')
                    ]
                    if has_current_resource_type:
                        row.append(rec.get('current_resource_type', ''))
                    if has_resource_type:
                        row.append(rec.get('resource_type', ''))
                    if has_description:
                        row.append(rec.get('description', ''))
                    if has_reason:
                        row.append(rec.get('reason', ''))
                    if has_current_config:
                        row.append(rec.get('current_config', ''))
                    if has_recommended_config:
                        row.append(rec.get('recommended_config', ''))
                    print("\t".join(map(str, row)))

if __name__ == "__main__":
    main()
