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
            Statistics=['Average'],
            Unit='Percent'
        )

        datapoints = response.get('Datapoints', [])

        #all_datapoints.extend(datapoints)

        # 各データポイントを表示（インスタンスIDとオートスケールグループ名も表示）
        # for dp in datapoints:
        #     print(f"Instance ID: {instance_id}")
        #     print(f"Timestamp: {dp['Timestamp']}, Average CPU: {dp['Average']}%")

        # 最大CPU使用率の計算
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
            # インスタンスステータスが終了済みの場合、スキップ
            if instance["State"]["Name"] == "terminated":
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
                instances_info.append([
                    instance_name,
                    instance_id_display,
                    instance_type,
                    count,
                    ebs[0],
                    ebs[1],
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

        instance_type_display = ", ".join(sorted(instance_types)) if len(instance_types) > 1 else next(iter(instance_types))
        cpu, ts = get_max_cpu_utilization(cluster_name, namespace='AWS/RDS', dimension_name='DBClusterIdentifier')

        clusters_info.append([cluster_name, instance_type_display, node_count, cpu, ts.isoformat() if ts else None])

    # 単体のRDSインスタンス情報（クラスターに属していないもの）を取得
    response = rds.describe_db_instances()
    for instance in response["DBInstances"]:
        instance_id = instance["DBInstanceIdentifier"]
        if instance_id in cluster_instance_ids:
            continue  # 既にクラスターで処理済みのインスタンスはスキップ

        if instance["Engine"] == "docdb":
            continue

        instance_type = instance["DBInstanceClass"]
        cpu, ts = get_max_cpu_utilization(instance_id, namespace='AWS/RDS', dimension_name='DBInstanceIdentifier')
        clusters_info.append([instance_id, instance_type, 1, cpu, ts.isoformat() if ts else None])

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
        
        if len(instance_types) > 1:
            instance_type_display = ", ".join(sorted(instance_types))
        else:
            instance_type_display = next(iter(instance_types))
        
        node_count = len(cluster["DBClusterMembers"])
        cpu, ts = get_max_cpu_utilization(cluster_name, namespace='AWS/DocDB', dimension_name='DBClusterIdentifier')
        clusters_info.append([cluster_name, instance_type_display, node_count, cpu, ts.isoformat() if ts else None])
    
    return clusters_info

def get_redis_clusters():
    elasticache = boto3.client("elasticache")
    response = elasticache.describe_replication_groups()
    clusters_info = []

    for cluster in response["ReplicationGroups"]:
        cluster_name = cluster["ReplicationGroupId"]
        instance_type = cluster["CacheNodeType"]
        node_count = len(cluster["MemberClusters"])

        for node_id in cluster["MemberClusters"]:
            cpu, ts = get_max_cpu_utilization(
                node_id,
                namespace='AWS/ElastiCache',
                dimension_name='CacheClusterId'
            )

        clusters_info.append([
            cluster_name,
            instance_type,
            node_count,
            cpu,
            ts.isoformat() if ts else None
        ])

    return clusters_info

import sys
def main():
    ec2_instances = get_ec2_instances()
    rds_clusters = get_rds_clusters()
    docdb_clusters = get_docdb_clusters()
    redis_clusters = get_redis_clusters()

    with open("output.txt", "w", encoding="utf-8") as f:

        sys.stdout = f

        print("\nEC2 :")
        print("Instance Name\tInstance ID\tInstance Type\t台数\tEBS Type\tEBS Size\tMax CPU\tMax CPU Time")
        for instance in ec2_instances:
            print("\t".join(map(str, instance)))

        print("\nRedis :")
        print("Cluster Name\tInstance Type\t台数\tMax CPU\tMax CPU Time")
        for cluster in redis_clusters:
            print("\t".join(map(str, cluster)))

        print("\nRDS :")
        print("Cluster Name\tInstance Type\t台数\tMax CPU\tMax CPU Time")
        for cluster in rds_clusters:
            print("\t".join(map(str, cluster)))

        print("\nDocumentDB :")
        print("Cluster Name\tInstance Type\t台数\tMax CPU\tMax CPU Time")
        for cluster in docdb_clusters:
            print("\t".join(map(str, cluster)))

if __name__ == "__main__":
    main()
