import boto3
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# グローバル変数でセッションを管理
_session = None

def get_session():
    """現在のセッションを取得"""
    global _session
    if _session is None:
        _session = boto3.Session()
    return _session

def set_profile(profile_name):
    """プロファイルを設定してセッションを作成"""
    global _session
    _session = boto3.Session(profile_name=profile_name)
    print(f"Using AWS profile: {profile_name}")

def get_client(service_name):
    """指定されたサービスのクライアントを取得"""
    return get_session().client(service_name)

# CloudWatchから最大CPU使用率を取得（30日間、5分平均 & 5分最大）
def get_max_cpu_utilization(instance_id, namespace='AWS/EC2', dimension_name='InstanceId'):
    cloudwatch = get_client('cloudwatch')

    period = 300  # 5分の期間
    days = 30  # 取得する期間（30日）

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    # 5分平均の最大値
    max_avg_cpu = 0.0
    max_avg_timestamp = None
    
    # 5分最大の最大値
    max_max_cpu = 0.0
    max_max_timestamp = None
    
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
            Statistics=['Average', 'Maximum'],  # 平均と最大の両方を取得
            Unit='Percent'
        )

        datapoints = response.get('Datapoints', [])

        for dp in datapoints:
            # 5分平均の最大値を追跡
            if dp.get('Average', 0) > max_avg_cpu:
                max_avg_cpu = dp['Average']
                max_avg_timestamp = dp['Timestamp']
            
            # 5分最大の最大値を追跡
            if dp.get('Maximum', 0) > max_max_cpu:
                max_max_cpu = dp['Maximum']
                max_max_timestamp = dp['Timestamp']

        current_start = current_end
    
    return {
        'avg': (round(max_avg_cpu, 2), max_avg_timestamp) if max_avg_cpu > 0 else (None, None),
        'max': (round(max_max_cpu, 2), max_max_timestamp) if max_max_cpu > 0 else (None, None)
    }

def get_ec2_instances():
    ec2 = get_client("ec2")
    
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

        # CPU使用率を取得（avg: 5分平均の最大, max: 5分最大の最大）
        cpu_avg, cpu_avg_ts = None, None
        cpu_max, cpu_max_ts = None, None

        if auto_scaling_group_name:
            result = get_max_cpu_utilization(auto_scaling_group_name, namespace='AWS/EC2', dimension_name='AutoScalingGroupName')
            cpu_avg, cpu_avg_ts = result['avg']
            cpu_max, cpu_max_ts = result['max']
        elif instance_ids:
            for iid in instance_ids:
                result = get_max_cpu_utilization(iid)
                avg_cpu, avg_ts = result['avg']
                max_cpu, max_ts = result['max']
                if avg_cpu is not None and (cpu_avg is None or avg_cpu > cpu_avg):
                    cpu_avg, cpu_avg_ts = avg_cpu, avg_ts
                if max_cpu is not None and (cpu_max is None or max_cpu > cpu_max):
                    cpu_max, cpu_max_ts = max_cpu, max_ts

        if ebs_info:
            for ebs in ebs_info:
                instances_info.append([
                    instance_name,
                    instance_id_display,
                    instance_type,
                    count,
                    ebs[0],
                    ebs[1],
                    cpu_avg,  # 5分平均の最大
                    cpu_max,  # 5分最大の最大
                    cpu_avg_ts.isoformat() if cpu_avg_ts else "N/A"
                ])

    return instances_info


def get_rds_clusters():
    rds = get_client("rds")
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
        result = get_max_cpu_utilization(cluster_name, namespace='AWS/RDS', dimension_name='DBClusterIdentifier')
        cpu_avg, cpu_avg_ts = result['avg']
        cpu_max, _ = result['max']

        clusters_info.append([cluster_name, instance_type_display, node_count, cpu_avg, cpu_max, cpu_avg_ts.isoformat() if cpu_avg_ts else None])

    # 単体のRDSインスタンス情報（クラスターに属していないもの）を取得
    response = rds.describe_db_instances()
    for instance in response["DBInstances"]:
        instance_id = instance["DBInstanceIdentifier"]
        if instance_id in cluster_instance_ids:
            continue  # 既にクラスターで処理済みのインスタンスはスキップ

        if instance["Engine"] == "docdb":
            continue

        instance_type = instance["DBInstanceClass"]
        result = get_max_cpu_utilization(instance_id, namespace='AWS/RDS', dimension_name='DBInstanceIdentifier')
        cpu_avg, cpu_avg_ts = result['avg']
        cpu_max, _ = result['max']
        clusters_info.append([instance_id, instance_type, 1, cpu_avg, cpu_max, cpu_avg_ts.isoformat() if cpu_avg_ts else None])

    return clusters_info

def get_docdb_clusters():
    docdb = get_client("docdb")
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
        result = get_max_cpu_utilization(cluster_name, namespace='AWS/DocDB', dimension_name='DBClusterIdentifier')
        cpu_avg, cpu_avg_ts = result['avg']
        cpu_max, _ = result['max']
        clusters_info.append([cluster_name, instance_type_display, node_count, cpu_avg, cpu_max, cpu_avg_ts.isoformat() if cpu_avg_ts else None])
    
    return clusters_info

def get_redis_clusters():
    elasticache = get_client("elasticache")
    response = elasticache.describe_replication_groups()
    clusters_info = []

    for cluster in response["ReplicationGroups"]:
        cluster_name = cluster["ReplicationGroupId"]
        instance_type = cluster["CacheNodeType"]
        node_count = len(cluster["MemberClusters"])

        cpu_avg, cpu_avg_ts = None, None
        cpu_max = None
        for node_id in cluster["MemberClusters"]:
            result = get_max_cpu_utilization(
                node_id,
                namespace='AWS/ElastiCache',
                dimension_name='CacheClusterId'
            )
            avg, ts = result['avg']
            mx, _ = result['max']
            if avg is not None and (cpu_avg is None or avg > cpu_avg):
                cpu_avg, cpu_avg_ts = avg, ts
            if mx is not None and (cpu_max is None or mx > cpu_max):
                cpu_max = mx

        clusters_info.append([
            cluster_name,
            instance_type,
            node_count,
            cpu_avg,
            cpu_max,
            cpu_avg_ts.isoformat() if cpu_avg_ts else None
        ])

    return clusters_info

def get_memcache_clusters():
    elasticache = get_client("elasticache")
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
        result = get_max_cpu_utilization(
            cluster_name,
            namespace='AWS/ElastiCache',
            dimension_name='CacheClusterId'
        )
        cpu_avg, cpu_avg_ts = result['avg']
        cpu_max, _ = result['max']

        clusters_info.append([
            cluster_name,
            instance_type,
            node_count,
            cpu_avg,
            cpu_max,
            cpu_avg_ts.isoformat() if cpu_avg_ts else None
        ])

    return clusters_info

import sys
import json
import io
import base64
import webbrowser
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote

# デフォルトのアップロード先URL
DEFAULT_UPLOAD_URL = "https://oprto2mpbwtacfhzaql7phb5ay0rxifk.lambda-url.ap-northeast-1.on.aws/"

def parse_args():
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(
        description='AWS インフラリソース情報を収集するスクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  # 🚀 推奨: ブラウザで結果を表示
  python check.py --profile account-a --open
  
  # ブラウザ表示 + AI分析
  python check.py --profile account-a --open --analyze
  
  # 標準出力に出力（コピペ用）
  python check.py --profile account-a --stdout
  
  # ファイルに保存
  python check.py --profile account-a --output result-a.txt
  
  # 複数アカウント一括処理
  for p in account-a account-b account-c; do
    python check.py --profile $p --open --analyze
  done
'''
    )
    parser.add_argument(
        '--profile', '-p',
        type=str,
        default=None,
        help='使用するAWSプロファイル名 (例: --profile ii-dev)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='出力ファイル名 (例: --output result.txt)'
    )
    parser.add_argument(
        '--stdout', '-s',
        action='store_true',
        help='結果を標準出力に出力（ファイルではなくコンソールに表示）'
    )
    parser.add_argument(
        '--upload', '-u',
        action='store_true',
        help='結果を自動的にサーバーにアップロード'
    )
    parser.add_argument(
        '--open', '-O',
        action='store_true',
        dest='open_browser',
        help='結果をブラウザで自動的に開く（推奨）'
    )
    parser.add_argument(
        '--analyze', '-a',
        action='store_true',
        help='AI分析も実行'
    )
    parser.add_argument(
        '--url',
        type=str,
        default=DEFAULT_UPLOAD_URL,
        help=f'アップロード先URL (デフォルト: {DEFAULT_UPLOAD_URL})'
    )
    parser.add_argument(
        '--region', '-r',
        type=str,
        default=None,
        help='AWSリージョン (例: --region ap-northeast-1)'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='進捗メッセージを非表示にする'
    )
    return parser.parse_args()


def open_in_browser(url: str, resource_text: str, analysis: str = None, token_usage: dict = None, profile: str = None):
    """結果をブラウザで開く"""
    # データをJSON形式でエンコード
    data = {
        "resources": resource_text,
        "analysis": analysis,
        "token_usage": token_usage,
        "profile": profile or "unknown",
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    
    # Base64エンコード
    json_str = json.dumps(data, ensure_ascii=False)
    encoded = base64.b64encode(json_str.encode('utf-8')).decode('ascii')
    
    # URLハッシュとして追加
    full_url = f"{url.rstrip('/')}/#data={encoded}"
    
    # ブラウザを開く（失敗してもエラーにしない）
    browser_opened = False
    try:
        browser_opened = webbrowser.open(full_url)
    except Exception:
        pass
    
    # URLを常に表示（クリック可能なリンクとして）
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"🌐 ブラウザで開く:", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"\n{full_url}\n", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not browser_opened:
        print("💡 上記URLをブラウザにコピー&ペーストしてください", file=sys.stderr)
    
    return full_url


def upload_results(resource_text: str, url: str, analyze: bool = False) -> dict:
    """収集結果をサーバーにアップロードする"""
    payload = {
        "action": "analyze_text" if analyze else "upload_only",
        "resource_text": resource_text
    }
    
    data = json.dumps(payload).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    req = Request(url, data=data, headers=headers, method='POST')
    
    try:
        with urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result
    except HTTPError as e:
        return {"error": f"HTTP Error {e.code}: {e.reason}"}
    except URLError as e:
        return {"error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def output_results(ec2_instances, rds_clusters, docdb_clusters, redis_clusters, memcache_clusters, file=None):
    """収集結果を出力"""
    out = file or sys.stdout
    
    print("\nEC2 :", file=out)
    print("Instance Name\tInstance ID\tInstance Type\t台数\tEBS Type\tEBS Size\tCPU AvgMax\tCPU Max\tTimestamp", file=out)
    for instance in ec2_instances:
        print("\t".join(map(str, instance)), file=out)

    print("\nRedis :", file=out)
    print("Cluster Name\tInstance Type\t台数\tCPU AvgMax\tCPU Max\tTimestamp", file=out)
    for cluster in redis_clusters:
        print("\t".join(map(str, cluster)), file=out)

    print("\nMemcached :", file=out)
    print("Cluster Name\tInstance Type\t台数\tCPU AvgMax\tCPU Max\tTimestamp", file=out)
    for cluster in memcache_clusters:
        print("\t".join(map(str, cluster)), file=out)

    print("\nRDS :", file=out)
    print("Cluster Name\tInstance Type\t台数\tCPU AvgMax\tCPU Max\tTimestamp", file=out)
    for cluster in rds_clusters:
        print("\t".join(map(str, cluster)), file=out)

    print("\nDocumentDB :", file=out)
    print("Cluster Name\tInstance Type\t台数\tCPU AvgMax\tCPU Max\tTimestamp", file=out)
    for cluster in docdb_clusters:
        print("\t".join(map(str, cluster)), file=out)


def log(msg, quiet=False):
    """進捗メッセージを出力（quietモードでない場合のみ）"""
    if not quiet:
        print(msg, file=sys.stderr)


def get_result_text(ec2_instances, rds_clusters, docdb_clusters, redis_clusters, memcache_clusters):
    """収集結果をテキストとして取得"""
    buffer = io.StringIO()
    output_results(ec2_instances, rds_clusters, docdb_clusters, redis_clusters, memcache_clusters, file=buffer)
    return buffer.getvalue()


def format_analysis(analysis: str) -> str:
    """AI分析結果を見やすくフォーマット"""
    separator = "=" * 60
    return f"""
{separator}
🤖 AI サイジング提案
{separator}

{analysis}

{separator}
"""


def main():
    args = parse_args()
    quiet = args.quiet or args.stdout  # stdout出力時は自動的にquiet
    
    # プロファイルが指定された場合、セッションを設定
    if args.profile:
        global _session
        if args.region:
            _session = boto3.Session(profile_name=args.profile, region_name=args.region)
            log(f"Using AWS profile: {args.profile}, region: {args.region}", quiet)
        else:
            _session = boto3.Session(profile_name=args.profile)
            log(f"Using AWS profile: {args.profile}", quiet)
    elif args.region:
        _session = boto3.Session(region_name=args.region)
        log(f"Using AWS region: {args.region}", quiet)
    
    log("Collecting AWS resource information...", quiet)
    
    ec2_instances = get_ec2_instances()
    log(f"  EC2: {len(ec2_instances)} instances", quiet)
    
    rds_clusters = get_rds_clusters()
    log(f"  RDS: {len(rds_clusters)} clusters/instances", quiet)
    
    docdb_clusters = get_docdb_clusters()
    log(f"  DocumentDB: {len(docdb_clusters)} clusters", quiet)
    
    redis_clusters = get_redis_clusters()
    log(f"  Redis: {len(redis_clusters)} clusters", quiet)
    
    memcache_clusters = get_memcache_clusters()
    log(f"  Memcached: {len(memcache_clusters)} clusters", quiet)

    # 結果テキストを生成
    result_text = get_result_text(ec2_instances, rds_clusters, docdb_clusters, redis_clusters, memcache_clusters)

    # ブラウザで開くモード（推奨）
    if args.open_browser:
        analysis = None
        token_usage = None
        
        if args.analyze:
            log("\nRequesting AI analysis...", quiet)
            response = upload_results(result_text, args.url, analyze=True)
            if "error" not in response and "analysis" in response:
                analysis = response["analysis"]
                token_usage = response.get("token_usage")
                log("✅ AI analysis completed!", quiet)
                
                # トークン使用量を表示
                if token_usage:
                    log(f"   📊 Tokens: {token_usage.get('input_tokens', 0):,} in + {token_usage.get('output_tokens', 0):,} out = {token_usage.get('total_tokens', 0):,} total", quiet)
                    log(f"   💰 Cost: ${token_usage.get('total_cost_usd', 0):.6f} (約{token_usage.get('total_cost_jpy', 0):.4f}円)", quiet)
            else:
                log("⚠️ AI analysis failed, opening without analysis", quiet)
        
        open_in_browser(args.url, result_text, analysis, token_usage, args.profile)
        
        # ファイル出力も併用する場合
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result_text)
                if analysis:
                    f.write(format_analysis(analysis))
            log(f"   Also saved to: {args.output}", quiet)

    # アップロードモード（コンソール表示）
    elif args.upload:
        log(f"\nUploading to: {args.url}", quiet)
        
        if args.analyze:
            log("Requesting AI analysis...", quiet)
        
        response = upload_results(result_text, args.url, analyze=args.analyze)
        
        if "error" in response:
            log(f"❌ Upload failed: {response['error']}", quiet=False)
            sys.exit(1)
        else:
            log("✅ Upload successful!", quiet)
            
            # AI分析結果があれば表示
            if args.analyze and "analysis" in response:
                print(format_analysis(response["analysis"]))
            
            # ファイル出力も併用する場合
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(result_text)
                    if args.analyze and "analysis" in response:
                        f.write(format_analysis(response["analysis"]))
                log(f"Output also saved to: {args.output}", quiet)
    
    # 標準出力モード
    elif args.stdout:
        output_results(ec2_instances, rds_clusters, docdb_clusters, redis_clusters, memcache_clusters)
    
    # ファイル出力モード
    elif args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            output_results(ec2_instances, rds_clusters, docdb_clusters, redis_clusters, memcache_clusters, file=f)
        log(f"\nOutput saved to: {args.output}", quiet)
    
    # デフォルト: output.txtに出力
    else:
        output_file = 'output.txt'
        with open(output_file, "w", encoding="utf-8") as f:
            output_results(ec2_instances, rds_clusters, docdb_clusters, redis_clusters, memcache_clusters, file=f)
        log(f"\nOutput saved to: {output_file}", quiet)


if __name__ == "__main__":
    main()
