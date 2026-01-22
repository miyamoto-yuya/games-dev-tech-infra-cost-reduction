import boto3
import json
import os
import uuid
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone


# SSO プロファイル設定（~/.aws/config から抽出）
SSO_PROFILES = {
    'crave': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '555109320113',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'polaris': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '590183989053',
        'sso_role_name': 'ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'vivid': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '228493844662',
        'sso_role_name': 'ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'seng': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '694512004038',
        'sso_role_name': 'ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'doo': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '396695244664',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'routine': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '145023108898',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'enkuri': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '121763773786',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'leg': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '149762279086',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'meteo': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '104238392782',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'monmusu': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '513395620689',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'aigisu': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '758002851130',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'twinkle': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '953444013299',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'techronos': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '219129075341',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'cthulhu': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '472156860599',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'tlo': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '497458598267',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'koihime': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '590183922525',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'roman': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '339712958905',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'osrr': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '306033979130',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
    'bngo': {
        'sso_start_url': 'https://ex-tsuchinoko.awsapps.com/start/',
        'sso_account_id': '346325158211',
        'sso_role_name': 'EXNOA_ReadOnlyAccess',
        'region': 'ap-northeast-1'
    },
}


def start_sso_login(profile_name: str) -> dict:
    """SSO デバイス認証フローを開始"""
    if profile_name not in SSO_PROFILES:
        return {'error': f'Unknown profile: {profile_name}'}
    
    profile = SSO_PROFILES[profile_name]
    region = profile['region']
    
    try:
        oidc_client = boto3.client('sso-oidc', region_name=region)
        
        # 1. クライアント登録（認証不要）
        register_response = oidc_client.register_client(
            clientName='infra-cost-reduction-tool',
            clientType='public'
        )
        
        # 2. デバイス認証を開始
        device_auth = oidc_client.start_device_authorization(
            clientId=register_response['clientId'],
            clientSecret=register_response['clientSecret'],
            startUrl=profile['sso_start_url']
        )
        
        return {
            'success': True,
            'profile': profile_name,
            'clientId': register_response['clientId'],
            'clientSecret': register_response['clientSecret'],
            'deviceCode': device_auth['deviceCode'],
            'userCode': device_auth['userCode'],
            'verificationUri': device_auth['verificationUri'],
            'verificationUriComplete': device_auth.get('verificationUriComplete', ''),
            'expiresIn': device_auth['expiresIn'],
            'interval': device_auth.get('interval', 5)
        }
    except Exception as e:
        return {'error': str(e)}


def complete_sso_login(profile_name: str, client_id: str, client_secret: str, device_code: str) -> dict:
    """SSO 認証完了後、AWS 認証情報を取得"""
    if profile_name not in SSO_PROFILES:
        return {'error': f'Unknown profile: {profile_name}'}
    
    profile = SSO_PROFILES[profile_name]
    region = profile['region']
    
    try:
        oidc_client = boto3.client('sso-oidc', region_name=region)
        sso_client = boto3.client('sso', region_name=region)
        
        # 3. アクセストークンを取得
        token_response = oidc_client.create_token(
            clientId=client_id,
            clientSecret=client_secret,
            grantType='urn:ietf:params:oauth:grant-type:device_code',
            deviceCode=device_code
        )
        
        access_token = token_response['accessToken']
        
        # 4. AWS 認証情報を取得
        credentials_response = sso_client.get_role_credentials(
            roleName=profile['sso_role_name'],
            accountId=profile['sso_account_id'],
            accessToken=access_token
        )
        
        role_credentials = credentials_response['roleCredentials']
        
        return {
            'success': True,
            'profile': profile_name,
            'accountId': profile['sso_account_id'],
            'credentials': {
                'accessKeyId': role_credentials['accessKeyId'],
                'secretAccessKey': role_credentials['secretAccessKey'],
                'sessionToken': role_credentials['sessionToken'],
                'expiration': role_credentials['expiration']
            }
        }
    except oidc_client.exceptions.AuthorizationPendingException:
        return {'error': 'authorization_pending', 'message': 'ユーザーがまだ認証を完了していません'}
    except oidc_client.exceptions.SlowDownException:
        return {'error': 'slow_down', 'message': 'リクエストが多すぎます。しばらく待ってください'}
    except oidc_client.exceptions.ExpiredTokenException:
        return {'error': 'expired', 'message': '認証の有効期限が切れました。再度ログインしてください'}
    except Exception as e:
        return {'error': str(e)}


def collect_resources_with_credentials(credentials: dict, region: str = 'ap-northeast-1') -> dict:
    """ユーザーの認証情報を使ってリソースを収集"""
    session = boto3.Session(
        aws_access_key_id=credentials['accessKeyId'],
        aws_secret_access_key=credentials['secretAccessKey'],
        aws_session_token=credentials['sessionToken'],
        region_name=region
    )
    
    resources = {
        'ec2': [],
        'rds': [],
        'docdb': [],
        'redis': [],
        'memcache': []
    }
    
    # EC2
    try:
        ec2 = session.client('ec2')
        response = ec2.describe_instances()
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                if instance.get('State', {}).get('Name') != 'running':
                    continue
                
                name = ''
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break
                
                # EBS情報
                ebs_type = ''
                ebs_size = 0
                for bdm in instance.get('BlockDeviceMappings', []):
                    if 'Ebs' in bdm:
                        vol_id = bdm['Ebs'].get('VolumeId')
                        if vol_id:
                            try:
                                vol_resp = ec2.describe_volumes(VolumeIds=[vol_id])
                                for vol in vol_resp.get('Volumes', []):
                                    ebs_type = vol.get('VolumeType', '')
                                    ebs_size = vol.get('Size', 0)
                                    break
                            except:
                                pass
                        break
                
                # CPU使用率（ユーザーセッションのCloudWatch）
                cpu_avg_max, cpu_max, timestamp = get_max_cpu_with_session(
                    session, instance['InstanceId'], 'AWS/EC2', 'InstanceId'
                )
                
                resources['ec2'].append({
                    'name': name,
                    'instance_id': instance['InstanceId'],
                    'instance_type': instance['InstanceType'],
                    'count': 1,
                    'ebs_type': ebs_type,
                    'ebs_size_gb': ebs_size,
                    'cpu_avg_max': round(cpu_avg_max, 2) if cpu_avg_max is not None else None,
                    'cpu_max': round(cpu_max, 2) if cpu_max is not None else None,
                    'timestamp': timestamp.isoformat() if timestamp else ''
                })
    except Exception as e:
        print(f"EC2 collection error: {e}")
    
    # RDS
    try:
        rds = session.client('rds')
        response = rds.describe_db_instances()
        cluster_instances = defaultdict(list)
        
        for db in response.get('DBInstances', []):
            # DocumentDBを除外（RDSセクションには含めない）
            engine = db.get('Engine', '')
            if 'docdb' in engine.lower():
                print(f"Skipping DocumentDB instance in RDS: {db.get('DBInstanceIdentifier')}")
                continue
            
            cluster_id = db.get('DBClusterIdentifier') or db.get('DBInstanceIdentifier')
            cluster_instances[cluster_id].append(db)
        
        for cluster_id, instances in cluster_instances.items():
            if instances:
                inst = instances[0]
                is_cluster = inst.get('DBClusterIdentifier') is not None
                cpu_avg_max, cpu_max, timestamp = None, None, None
                
                # Auroraクラスターの場合
                if is_cluster:
                    # 1. CPUUtilization (DBClusterIdentifier)
                    cpu_avg_max, cpu_max, timestamp = get_max_cpu_with_session(
                        session, cluster_id, 'AWS/RDS', 'DBClusterIdentifier'
                    )
                    print(f"RDS Cluster {cluster_id} CPU (DBClusterIdentifier): {cpu_avg_max}")
                    
                    # 2. ACUUtilization (Aurora Serverless v2)
                    if cpu_avg_max is None:
                        cpu_avg_max, cpu_max, timestamp = get_serverless_acu_with_session(
                            session, cluster_id
                        )
                    
                    # 3. CPUUtilization (DBInstanceIdentifier)
                    if cpu_avg_max is None:
                        cpu_avg_max, cpu_max, timestamp = get_max_cpu_with_session(
                            session, inst['DBInstanceIdentifier'], 'AWS/RDS', 'DBInstanceIdentifier'
                        )
                        print(f"RDS Cluster {cluster_id} CPU (DBInstanceIdentifier): {cpu_avg_max}")
                else:
                    cpu_avg_max, cpu_max, timestamp = get_max_cpu_with_session(
                        session, inst['DBInstanceIdentifier'], 'AWS/RDS', 'DBInstanceIdentifier'
                    )
                    print(f"RDS Instance {cluster_id} CPU: {cpu_avg_max}")
                
                resources['rds'].append({
                    'name': cluster_id,
                    'instance_type': inst['DBInstanceClass'],
                    'count': len(instances),
                    'cpu_avg_max': round(cpu_avg_max, 2) if cpu_avg_max is not None else None,
                    'cpu_max': round(cpu_max, 2) if cpu_max is not None else None,
                    'timestamp': timestamp.isoformat() if timestamp else ''
                })
    except Exception as e:
        print(f"RDS collection error: {e}")
    
    # DocumentDB
    try:
        docdb = session.client('docdb')
        response = docdb.describe_db_clusters()
        
        for cluster in response.get('DBClusters', []):
            # DocumentDBのみ対象（RDS Auroraは除外）
            engine = cluster.get('Engine', '').lower()
            cluster_id = cluster.get('DBClusterIdentifier', '')
            if engine != 'docdb':
                print(f"[DocumentDB] SKIP non-docdb cluster: {cluster_id} (engine='{engine}')")
                continue
            
            print(f"[DocumentDB] INCLUDE: {cluster_id} (engine='{engine}')")
            members = cluster.get('DBClusterMembers', [])
            if members:
                member_id = members[0].get('DBInstanceIdentifier')
                inst_resp = docdb.describe_db_instances(DBInstanceIdentifier=member_id)
                inst = inst_resp['DBInstances'][0] if inst_resp.get('DBInstances') else {}
                
                cpu_avg_max, cpu_max, timestamp = get_max_cpu_with_session(
                    session, member_id, 'AWS/DocDB', 'DBInstanceIdentifier'
                )
                resources['docdb'].append({
                    'name': cluster_id,
                    'instance_type': inst.get('DBInstanceClass', ''),
                    'count': len(members),
                    'cpu_avg_max': round(cpu_avg_max, 2) if cpu_avg_max is not None else None,
                    'cpu_max': round(cpu_max, 2) if cpu_max is not None else None,
                    'timestamp': timestamp.isoformat() if timestamp else ''
                })
    except Exception as e:
        print(f"DocumentDB collection error: {e}")
    
    # ElastiCache (Redis)
    try:
        elasticache = session.client('elasticache')
        response = elasticache.describe_replication_groups()
        
        for rg in response.get('ReplicationGroups', []):
            node_groups = rg.get('NodeGroups', [])
            if node_groups:
                members = node_groups[0].get('NodeGroupMembers', [])
                if members:
                    cache_cluster_id = members[0].get('CacheClusterId')
                    cc_resp = elasticache.describe_cache_clusters(CacheClusterId=cache_cluster_id)
                    cc = cc_resp['CacheClusters'][0] if cc_resp.get('CacheClusters') else {}
                    
                    cpu_avg_max, cpu_max, timestamp = get_max_cpu_with_session(
                        session, cache_cluster_id, 'AWS/ElastiCache', 'CacheClusterId'
                    )
                    total_nodes = sum(len(ng.get('NodeGroupMembers', [])) for ng in node_groups)
                    
                    resources['redis'].append({
                        'name': rg['ReplicationGroupId'],
                        'instance_type': cc.get('CacheNodeType', ''),
                        'count': total_nodes,
                        'cpu_avg_max': round(cpu_avg_max, 2) if cpu_avg_max is not None else None,
                        'cpu_max': round(cpu_max, 2) if cpu_max is not None else None,
                        'timestamp': timestamp.isoformat() if timestamp else ''
                    })
    except Exception as e:
        print(f"Redis collection error: {e}")
    
    # ElastiCache (Memcached)
    try:
        elasticache = session.client('elasticache')
        response = elasticache.describe_cache_clusters()
        
        for cc in response.get('CacheClusters', []):
            if cc.get('Engine') == 'memcached':
                cpu_avg_max, cpu_max, timestamp = get_max_cpu_with_session(
                    session, cc['CacheClusterId'], 'AWS/ElastiCache', 'CacheClusterId'
                )
                resources['memcache'].append({
                    'name': cc['CacheClusterId'],
                    'instance_type': cc.get('CacheNodeType', ''),
                    'count': cc.get('NumCacheNodes', 1),
                    'cpu_avg_max': round(cpu_avg_max, 2) if cpu_avg_max is not None else None,
                    'cpu_max': round(cpu_max, 2) if cpu_max is not None else None,
                    'timestamp': timestamp.isoformat() if timestamp else ''
                })
    except Exception as e:
        print(f"Memcached collection error: {e}")
    
    return resources


def get_serverless_acu_with_session(session, cluster_id: str):
    """Aurora Serverless v2のACU使用率を取得"""
    cloudwatch = session.client('cloudwatch')
    
    period = 300
    days = 30
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    max_avg = None
    max_max = None
    max_timestamp = None
    
    print(f"[CloudWatch] Getting Serverless ACU: cluster={cluster_id}")
    
    interval = timedelta(days=5)
    current_start = start_time
    total_datapoints = 0
    
    while current_start < end_time:
        current_end = min(current_start + interval, end_time)
        
        try:
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName='ACUUtilization',
                Dimensions=[{'Name': 'DBClusterIdentifier', 'Value': cluster_id}],
                StartTime=current_start,
                EndTime=current_end,
                Period=period,
                Statistics=['Average', 'Maximum'],
                Unit='Percent'
            )
            
            datapoints = response.get('Datapoints', [])
            total_datapoints += len(datapoints)
            
            for dp in datapoints:
                avg = dp.get('Average', 0)
                maximum = dp.get('Maximum', 0)
                if max_avg is None or avg > max_avg:
                    max_avg = avg
                    max_max = maximum
                    max_timestamp = dp['Timestamp']
        except Exception as e:
            print(f"[CloudWatch] Serverless ACU error for {cluster_id}: {e}")
        
        current_start = current_end
    
    print(f"[CloudWatch] Serverless ACU result for {cluster_id}: datapoints={total_datapoints}, max_avg={max_avg}")
    return max_avg, max_max, max_timestamp


def get_max_cpu_with_session(session, instance_id: str, namespace: str, dimension_name: str):
    """セッションを使用してCPU使用率を取得"""
    cloudwatch = session.client('cloudwatch')
    
    period = 300
    days = 30
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    max_avg = None  # データがない場合はNone
    max_max = None
    max_timestamp = None
    
    print(f"[CloudWatch] Getting metrics: namespace={namespace}, dimension={dimension_name}, value={instance_id}")
    
    interval = timedelta(days=5)
    current_start = start_time
    total_datapoints = 0
    
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
                Statistics=['Average', 'Maximum'],
                Unit='Percent'
            )
            
            datapoints = response.get('Datapoints', [])
            total_datapoints += len(datapoints)
            
            for dp in datapoints:
                avg = dp.get('Average', 0)
                maximum = dp.get('Maximum', 0)
                if max_avg is None or avg > max_avg:
                    max_avg = avg
                    max_max = maximum
                    max_timestamp = dp['Timestamp']
        except Exception as e:
            print(f"[CloudWatch] Error for {instance_id}: {e}")
        
        current_start = current_end
    
    print(f"[CloudWatch] Result for {instance_id}: datapoints={total_datapoints}, max_avg={max_avg}")
    return max_avg, max_max, max_timestamp


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
        raw_content = ''.join(content)
        
        # デバッグログ
        print(f"[MCP Debug] Tool: {tool_name}, Raw response length: {len(raw_content)}")
        
        result = json.loads(raw_content)
        
        # デバッグ: レスポンス構造を確認
        print(f"[MCP Debug] Response keys: {list(result.keys())}")
        
        if "result" in result and "content" in result["result"]:
            text_content = result["result"]["content"][0]["text"]
            print(f"[MCP Debug] Parsed content length: {len(text_content)}")
            return json.loads(text_content)
        
        # エラー詳細をログ出力
        print(f"[MCP Debug] Unexpected format: {raw_content[:500]}")
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
# cpu_avg_max: 5分間平均値の最大（判定用）
# cpu_max: 5分間最大値の最大（参考）
def get_max_cpu_utilization(instance_id, namespace='AWS/EC2', dimension_name='InstanceId'):
    cloudwatch = boto3.client('cloudwatch')

    period = 300  # 5分の期間
    days = 30  # 取得する期間（30日）

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    cpu_avg_max = 0.0  # 平均値の最大
    cpu_max = 0.0      # 最大値の最大
    max_timestamp = None
    
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
                Statistics=['Average', 'Maximum'],  # 両方取得
                Unit='Percent'
            )

            for dp in response.get('Datapoints', []):
                avg = dp.get('Average', 0)
                maximum = dp.get('Maximum', 0)
                if avg > cpu_avg_max:
                    cpu_avg_max = avg
                    cpu_max = maximum
                    max_timestamp = dp['Timestamp']
        except Exception as e:
            print(f"CloudWatch error for {instance_id}: {e}")

        current_start = current_end
    
    if cpu_avg_max > 0:
        return {
            'cpu_avg_max': round(cpu_avg_max, 2),
            'cpu_max': round(cpu_max, 2),
            'timestamp': max_timestamp
        }
    return {'cpu_avg_max': None, 'cpu_max': None, 'timestamp': None}


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

        cpu_metrics = {'cpu_avg_max': None, 'cpu_max': None, 'timestamp': None}

        if auto_scaling_group_name:
            # Auto Scaling Group のメトリクスを使用（ASG全体のCPU）
            cpu_metrics = get_max_cpu_utilization(
                auto_scaling_group_name, 
                namespace='AWS/EC2', 
                dimension_name='AutoScalingGroupName'
            )
            print(f"ASG metrics for {instance_name} ({auto_scaling_group_name}): {cpu_metrics}")
        elif instance_ids:
            # 個別インスタンスのメトリクスを集約
            best_avg_max = 0.0
            best_cpu_max = 0.0
            best_timestamp = None
            
            for iid in instance_ids:
                metrics = get_max_cpu_utilization(iid)
                if metrics['cpu_avg_max'] is not None and metrics['cpu_avg_max'] > best_avg_max:
                    best_avg_max = metrics['cpu_avg_max']
                    best_cpu_max = metrics['cpu_max']
                    best_timestamp = metrics['timestamp']
            
            if best_avg_max > 0:
                cpu_metrics = {
                    'cpu_avg_max': best_avg_max,
                    'cpu_max': best_cpu_max,
                    'timestamp': best_timestamp
                }

        if ebs_info:
            for ebs in ebs_info:
                instances_info.append({
                    "name": instance_name,
                    "instance_id": instance_id_display,
                    "instance_type": instance_type,
                    "count": count,
                    "ebs_type": ebs[0],
                    "ebs_size": ebs[1],
                    "cpu_avg_max": cpu_metrics['cpu_avg_max'],
                    "cpu_max": cpu_metrics['cpu_max'],
                    "timestamp": cpu_metrics['timestamp'].isoformat() if cpu_metrics['timestamp'] else None,
                    "is_auto_scaling": bool(auto_scaling_group_name),
                    "auto_scaling_group": auto_scaling_group_name
                })

    return instances_info


def get_rds_clusters():
    """RDS Aurora/MySQLクラスターのみを取得（DocumentDBは除外）"""
    rds = boto3.client("rds")
    clusters_info = []

    response = rds.describe_db_clusters()
    cluster_instance_ids = set()

    # デバッグ: 全クラスターのエンジン名を出力
    print(f"[RDS] Total clusters from API: {len(response.get('DBClusters', []))}")
    
    for cluster in response.get("DBClusters", []):
        engine = cluster.get("Engine", "").lower()
        cluster_id = cluster.get("DBClusterIdentifier", "")
        
        # DocumentDBは除外（get_docdb_clustersで取得する）
        # RDS Auroraのエンジン名は "aurora-mysql", "aurora-postgresql" など
        if engine == "docdb":
            print(f"[RDS] SKIP DocumentDB: {cluster_id} (engine='{engine}')")
            continue
        
        print(f"[RDS] INCLUDE: {cluster_id} (engine='{engine}')")
        cluster_name = cluster_id
        node_count = len(cluster["DBClusterMembers"])

        instance_types = set()
        for member in cluster["DBClusterMembers"]:
            db_instance_identifier = member["DBInstanceIdentifier"]
            cluster_instance_ids.add(db_instance_identifier)
            db_instance = rds.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)["DBInstances"][0]
            instance_type = db_instance["DBInstanceClass"]
            instance_types.add(instance_type)

        instance_type_display = ", ".join(sorted(instance_types)) if len(instance_types) > 1 else next(iter(instance_types))
        cpu_data = get_max_cpu_utilization(cluster_name, namespace='AWS/RDS', dimension_name='DBClusterIdentifier')

        clusters_info.append({
            "name": cluster_name,
            "instance_type": instance_type_display,
            "count": node_count,
            "cpu_avg_max": cpu_data.get('cpu_avg_max'),
            "cpu_max": cpu_data.get('cpu_max'),
            "max_cpu_time": cpu_data.get('timestamp').isoformat() if cpu_data.get('timestamp') else None
        })

    # スタンドアロンRDSインスタンス（クラスターに属さないもの）
    response = rds.describe_db_instances()
    for instance in response.get("DBInstances", []):
        instance_id = instance["DBInstanceIdentifier"]
        if instance_id in cluster_instance_ids:
            continue

        engine = instance.get("Engine", "").lower()
        # DocumentDBは除外
        if engine == "docdb":
            print(f"[RDS] Skipping DocumentDB instance: {instance_id}")
            continue

        print(f"[RDS] Found standalone instance: {instance_id} (engine={engine})")
        instance_type = instance["DBInstanceClass"]
        cpu_data = get_max_cpu_utilization(instance_id, namespace='AWS/RDS', dimension_name='DBInstanceIdentifier')
        clusters_info.append({
            "name": instance_id,
            "instance_type": instance_type,
            "count": 1,
            "cpu_avg_max": cpu_data.get('cpu_avg_max'),
            "cpu_max": cpu_data.get('cpu_max'),
            "max_cpu_time": cpu_data.get('timestamp').isoformat() if cpu_data.get('timestamp') else None
        })

    print(f"[RDS] Total clusters/instances found: {len(clusters_info)}")
    return clusters_info


def get_docdb_clusters():
    """DocumentDBクラスターのみを取得（RDS Auroraは除外）"""
    # RDSクライアントを使用（docdbクライアントも同じAPI）
    rds = boto3.client("rds")
    clusters_info = []
    
    response = rds.describe_db_clusters()
    
    # デバッグ: 全クラスターのエンジン名を出力
    print(f"[DocumentDB] Total clusters from API: {len(response.get('DBClusters', []))}")
    for c in response.get("DBClusters", []):
        print(f"[DocumentDB DEBUG] Cluster: {c.get('DBClusterIdentifier')} | Engine: '{c.get('Engine')}' | EngineMode: '{c.get('EngineMode', 'N/A')}'")
    
    for cluster in response.get("DBClusters", []):
        engine = cluster.get("Engine", "").lower()
        cluster_id = cluster.get("DBClusterIdentifier", "")
        
        # DocumentDBのみ対象（エンジン名で厳密にフィルタ）
        # DocumentDBのエンジン名は "docdb"
        if engine != "docdb":
            print(f"[DocumentDB] SKIP: {cluster_id} (engine='{engine}' != 'docdb')")
            continue
        
        print(f"[DocumentDB] INCLUDE: {cluster_id} (engine={engine})")
        
        instance_types = set()
        for member in cluster.get("DBClusterMembers", []):
            db_instance_identifier = member["DBInstanceIdentifier"]
            try:
                db_instance = rds.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)["DBInstances"][0]
                instance_type = db_instance["DBInstanceClass"]
                instance_types.add(instance_type)
            except Exception as e:
                print(f"Error getting DocumentDB instance {db_instance_identifier}: {e}")
        
        if not instance_types:
            continue
            
        instance_type_display = ", ".join(sorted(instance_types)) if len(instance_types) > 1 else next(iter(instance_types))
        
        node_count = len(cluster.get("DBClusterMembers", []))
        cpu_data = get_max_cpu_utilization(cluster_id, namespace='AWS/DocDB', dimension_name='DBClusterIdentifier')
        clusters_info.append({
            "name": cluster_id,
            "instance_type": instance_type_display,
            "count": node_count,
            "cpu_avg_max": cpu_data.get('cpu_avg_max'),
            "cpu_max": cpu_data.get('cpu_max'),
            "max_cpu_time": cpu_data.get('timestamp').isoformat() if cpu_data.get('timestamp') else None
        })
    
    print(f"[DocumentDB] Total clusters found: {len(clusters_info)}")
    return clusters_info


def get_redis_clusters():
    elasticache = boto3.client("elasticache")
    response = elasticache.describe_replication_groups()
    clusters_info = []

    for cluster in response["ReplicationGroups"]:
        cluster_name = cluster["ReplicationGroupId"]
        instance_type = cluster["CacheNodeType"]
        node_count = len(cluster["MemberClusters"])

        cpu_avg_max = None
        cpu_max = None
        max_timestamp = None
        for node_id in cluster["MemberClusters"]:
            cpu_data = get_max_cpu_utilization(
                node_id,
                namespace='AWS/ElastiCache',
                dimension_name='CacheClusterId'
            )
            if cpu_data.get('cpu_avg_max') is not None:
                if cpu_avg_max is None or cpu_data['cpu_avg_max'] > cpu_avg_max:
                    cpu_avg_max = cpu_data['cpu_avg_max']
                    cpu_max = cpu_data.get('cpu_max')
                    max_timestamp = cpu_data.get('timestamp')

        clusters_info.append({
            "name": cluster_name,
            "instance_type": instance_type,
            "count": node_count,
            "cpu_avg_max": cpu_avg_max,
            "cpu_max": cpu_max,
            "max_cpu_time": max_timestamp.isoformat() if max_timestamp else None
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
        
        cpu_data = get_max_cpu_utilization(
            cluster_name,
            namespace='AWS/ElastiCache',
            dimension_name='CacheClusterId'
        )

        clusters_info.append({
            "name": cluster_name,
            "instance_type": instance_type,
            "count": node_count,
            "cpu_avg_max": cpu_data.get('cpu_avg_max'),
            "cpu_max": cpu_data.get('cpu_max'),
            "max_cpu_time": cpu_data.get('timestamp').isoformat() if cpu_data.get('timestamp') else None
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
    
    # リストまたは辞書からデータを取得するヘルパー
    def get_field(item, field, list_index=None):
        if isinstance(item, dict):
            # 辞書の場合
            if field == 'cpu':
                return item.get('cpu_avg_max') or item.get('max_cpu') or 0
            return item.get(field, '')
        elif isinstance(item, (list, tuple)):
            # リストの場合
            if list_index is not None and list_index < len(item):
                return item[list_index] or ''
            return ''
        return ''
    
    output.append("EC2 :")
    output.append("Instance Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources.get("ec2", []):
        # EC2: [name, id, type, count, ebs_type, ebs_size, cpu, ts] or dict
        if isinstance(item, dict):
            name, itype, count, cpu = item.get('name', ''), item.get('instance_type', ''), item.get('count', 1), get_field(item, 'cpu')
        else:
            name, itype, count, cpu = item[0], item[2], item[3], item[6] or 0
        monthly = get_monthly_cost(itype, 'ec2')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{name}\t{itype}\t{count}\t{cpu}\t{monthly_str}")

    output.append("\nRDS :")
    output.append("Cluster Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources.get("rds", []):
        # RDS: [name, type, count, cpu, ts] or dict
        if isinstance(item, dict):
            name, itype, count, cpu = item.get('name', ''), item.get('instance_type', ''), item.get('count', 1), get_field(item, 'cpu')
        else:
            name, itype, count, cpu = item[0], item[1], item[2], item[3] or 0
        monthly = get_monthly_cost(itype, 'rds')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{name}\t{itype}\t{count}\t{cpu}\t{monthly_str}")

    output.append("\nDocumentDB :")
    output.append("Cluster Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources.get("docdb", []):
        # DocDB: [name, type, count, cpu, ts] or dict
        if isinstance(item, dict):
            name, itype, count, cpu = item.get('name', ''), item.get('instance_type', ''), item.get('count', 1), get_field(item, 'cpu')
        else:
            name, itype, count, cpu = item[0], item[1], item[2], item[3] or 0
        monthly = get_monthly_cost(itype, 'docdb')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{name}\t{itype}\t{count}\t{cpu}\t{monthly_str}")

    output.append("\nRedis (ElastiCache) :")
    output.append("Cluster Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources.get("redis", []):
        # Redis: [name, type, count, cpu, ts] or dict
        if isinstance(item, dict):
            name, itype, count, cpu = item.get('name', ''), item.get('instance_type', ''), item.get('count', 1), get_field(item, 'cpu')
        else:
            name, itype, count, cpu = item[0], item[1], item[2], item[3] or 0
        monthly = get_monthly_cost(itype, 'redis')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{name}\t{itype}\t{count}\t{cpu}\t{monthly_str}")

    output.append("\nMemcached (ElastiCache) :")
    output.append("Cluster Name\tInstance Type\t台数\tCPU AvgMax\t月額(USD)")
    for item in resources.get("memcache", []):
        # Memcache: [name, type, count, cpu, ts] or dict
        if isinstance(item, dict):
            name, itype, count, cpu = item.get('name', ''), item.get('instance_type', ''), item.get('count', 1), get_field(item, 'cpu')
        else:
            name, itype, count, cpu = item[0], item[1], item[2], item[3] or 0
        monthly = get_monthly_cost(itype, 'memcache')
        monthly_str = f"${monthly}" if monthly else "N/A"
        output.append(f"{name}\t{itype}\t{count}\t{cpu}\t{monthly_str}")

    return "\n".join(output)


def get_mcp_batch_recommendations(resources):
    """MCPから全リソースの一括スケールダウン提案を取得"""
    instances = []
    
    # リストまたは辞書からフィールドを取得するヘルパー
    def get_field(item, dict_key, list_index, is_ec2=False):
        if isinstance(item, dict):
            return item.get(dict_key)
        elif isinstance(item, (list, tuple)):
            # EC2はリストのインデックスが異なる
            actual_index = list_index + (1 if is_ec2 and list_index >= 2 else 0)
            return item[actual_index] if len(item) > actual_index else None
        return None
    
    def get_instance_type(item, is_ec2=False):
        if isinstance(item, dict):
            return item.get("instance_type")
        elif isinstance(item, (list, tuple)):
            idx = 2 if is_ec2 else 1
            return item[idx] if len(item) > idx else None
        return None
    
    def get_cpu_avg_max(item):
        if isinstance(item, dict):
            cpu = item.get("cpu_avg_max")
            if cpu is None:
                cpu = item.get("max_cpu")
            return cpu
        return None
    
    # EC2
    for item in resources.get("ec2", []):
        if isinstance(item, dict):
            name = item.get("name", "")
            instance_type = item.get("instance_type", "")
            cpu = get_cpu_avg_max(item)
            if name and instance_type and cpu is not None:
                instances.append({
                    "name": name,
                    "instance_type": instance_type,
                    "cpu_avg_max": cpu,
                    "service": "ec2"
                })
    
    # RDS
    for item in resources.get("rds", []):
        if isinstance(item, dict):
            name = item.get("name", "")
            instance_type = item.get("instance_type", "")
            cpu = get_cpu_avg_max(item)
            if name and instance_type and cpu is not None:
                instances.append({
                    "name": name,
                    "instance_type": instance_type,
                    "cpu_avg_max": cpu,
                    "service": "rds"
                })
    
    # DocumentDB
    for item in resources.get("docdb", []):
        if isinstance(item, dict):
            name = item.get("name", "")
            instance_type = item.get("instance_type", "")
            cpu = get_cpu_avg_max(item)
            if name and instance_type and cpu is not None:
                instances.append({
                    "name": name,
                    "instance_type": instance_type,
                    "cpu_avg_max": cpu,
                    "service": "docdb"
                })
    
    # Redis / Memcache
    for service_key in ["redis", "memcache"]:
        for item in resources.get(service_key, []):
            if isinstance(item, dict):
                name = item.get("name", "")
                instance_type = item.get("instance_type", "")
                cpu = get_cpu_avg_max(item)
                if name and instance_type and cpu is not None:
                    instances.append({
                        "name": name,
                        "instance_type": instance_type,
                        "cpu_avg_max": cpu,
                        "service": "elasticache"
                    })
    
    if not instances:
        print("No instances with CPU data for MCP batch recommendations")
        return {}
    
    # AgentCore経由でMCP呼び出し
    try:
        print(f"Calling MCP get_batch_recommendations with {len(instances)} instances")
        result = call_mcp_tool("get_batch_recommendations", {
            "instances": instances,
            "region": "ap-northeast-1"
        })
        
        if "error" in result:
            print(f"MCP batch recommendations error: {result['error']}")
            return {}
        
        recommendations = result.get("recommendations", [])
        
        # 名前をキーにした辞書に変換
        rec_dict = {}
        for rec in recommendations:
            name = rec.get("name", "")
            if name:
                rec_dict[name] = rec
        
        print(f"MCP batch recommendations: {len(rec_dict)} items")
        return rec_dict
    except Exception as e:
        print(f"Error getting MCP batch recommendations: {e}")
    
    return {}


def collect_pricing_info(resources):
    """リソースの価格情報を収集（EC2/RDS/ElastiCache/DocDB）- 一括取得で高速化"""
    pricing_info = {
        'ec2': {},
        'rds': {},
        'elasticache': {},
        'docdb': {}
    }
    
    # リストまたは辞書からinstance_typeを取得
    def get_instance_type(item, is_ec2=False):
        if isinstance(item, dict):
            return item.get("instance_type")
        elif isinstance(item, (list, tuple)):
            # EC2: [name, id, type, count, ...] -> index 2
            # Others: [name, type, count, ...] -> index 1
            idx = 2 if is_ec2 else 1
            return item[idx] if len(item) > idx else None
        return None
    
    # 全インスタンスタイプを収集
    instance_types_to_fetch = []
    seen = set()
    
    service_mapping = [
        ('ec2', 'ec2', resources.get("ec2", []), True),
        ('rds', 'rds', resources.get("rds", []), False),
        ('docdb', 'docdb', resources.get("docdb", []), False),
        ('elasticache', 'redis', resources.get("redis", []), False),
        ('elasticache', 'memcache', resources.get("memcache", []), False),
    ]
    
    for service_key, resource_key, items, is_ec2 in service_mapping:
        for item in items:
            instance_type = get_instance_type(item, is_ec2)
            if instance_type and instance_type not in seen:
                seen.add(instance_type)
                instance_types_to_fetch.append({
                    "instance_type": instance_type,
                    "service": service_key
                })
    
    # MCPサーバーで一括取得
    if instance_types_to_fetch:
        try:
            result = call_mcp_tool("get_batch_prices", {
                "instance_types": instance_types_to_fetch,
                "region": "ap-northeast-1"
            })
            prices = result.get("prices", {})
            
            # 結果をサービス別に振り分け
            for item in instance_types_to_fetch:
                instance_type = item["instance_type"]
                service_key = item["service"]
                price_info = prices.get(instance_type, {})
                hourly_price = price_info.get("hourly_price_usd")
                if hourly_price and hourly_price > 0:
                    pricing_info[service_key][instance_type] = hourly_price
        except Exception as e:
            print(f"Error getting batch prices: {e}")
    
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
| 40%未満 | 過剰 | 小さいタイプへ変更（コスト削減） |
| 40%〜70% | 適正 | 変更不要 |
| 70%以上 | 不足 | 変更不要（コメントのみ） |

★★★ 重要：目標CPU使用率 40〜70% ★★★
- これはコスト削減ツールです
- スケールダウン（小さいタイプへの変更）のみ提案してください
- 変更後の予測CPU使用率が40〜70%になるタイプを選んでください
- 予測CPU = 現在CPU × (現在vCPU数 / 提案vCPU数)
- スペック不足の場合は「変更不要」とし、コメントで「スペック不足」と記載するだけでOK

例：
- CPU AvgMax = 10% (t3.medium/2vCPU) → 過剰 → t3.micro (1vCPU) へ変更で予測20%...まだ低い → t3.nano (0.5vCPU相当) で予測40%程度 → 採用
- CPU AvgMax = 25% (t3.large/2vCPU) → 過剰 → t3.medium (2vCPU) で予測50%程度 → 採用
- CPU AvgMax = 45% → 適正 → 変更不要
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

def get_html_template():
    """フロントエンドHTMLを返す"""
    return '''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS費用削減ツール</title>
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
            max-width: 1800px;
            margin: 0 auto;
            padding: 1.5rem;
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

        /* SSO Login Section */
        .sso-section {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }

        .sso-section h3 {
            color: var(--accent-cyan);
            margin-bottom: 1rem;
            font-size: 1.1rem;
        }

        .profile-select-group {
            display: flex;
            gap: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }

        .profile-select {
            flex: 1;
            min-width: 200px;
            padding: 0.75rem 1rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 1rem;
            cursor: pointer;
        }

        .profile-select:focus {
            outline: none;
            border-color: var(--accent-cyan);
        }

        .profile-select option {
            background: var(--bg-secondary);
            color: var(--text-primary);
        }

        .sso-status {
            margin-top: 1rem;
            padding: 1rem;
            background: var(--bg-secondary);
            border-radius: 8px;
            display: none;
        }

        .sso-status.visible {
            display: block;
            animation: fadeInUp 0.3s ease-out;
        }

        .sso-code {
            font-family: 'JetBrains Mono', monospace;
            font-size: 2rem;
            color: var(--accent-orange);
            text-align: center;
            padding: 1rem;
            background: var(--bg-primary);
            border-radius: 8px;
            margin: 1rem 0;
            letter-spacing: 0.3em;
        }

        .sso-link {
            color: var(--accent-cyan);
            text-decoration: none;
            word-break: break-all;
        }

        .sso-link:hover {
            text-decoration: underline;
        }

        .btn-sso {
            background: linear-gradient(135deg, var(--accent-purple), var(--accent-cyan));
        }

        .btn-sso:hover {
            box-shadow: 0 8px 30px rgba(167, 139, 250, 0.4);
        }

        .account-badge {
            display: inline-block;
            background: var(--bg-secondary);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-left: 0.5rem;
        }

        .current-profile {
            background: rgba(34, 211, 238, 0.1);
            border: 1px solid var(--accent-cyan);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin-bottom: 1rem;
            display: none;
        }

        .current-profile.visible {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .current-profile .profile-name {
            color: var(--accent-cyan);
            font-weight: 500;
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
            margin: 0;
            padding: 0 0.5rem;
        }
        
        .cost-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.7rem;
        }
        
        .cost-table .header-group th {
            background: var(--bg-secondary);
            padding: 0.3rem 0.4rem;
            text-align: center;
            font-weight: 600;
            color: var(--text-primary);
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
        }
        
        .cost-table .header-group .group-name {
            background: var(--bg-secondary);
        }
        
        .cost-table .header-group .group-current {
            background: rgba(34, 211, 238, 0.2);
            color: var(--accent-cyan);
            border-left: 2px solid var(--accent-cyan);
            font-size: 0.75rem;
        }
        
        .cost-table .header-group .group-recommend {
            background: rgba(74, 222, 128, 0.2);
            color: var(--accent-green);
            border-left: 2px solid var(--accent-green);
            font-size: 0.75rem;
        }
        
        .cost-table .header-group .group-cpu {
            background: rgba(251, 146, 60, 0.2);
            color: var(--accent-orange);
            border-left: 2px solid var(--accent-orange);
            font-size: 0.75rem;
        }
        
        .cost-table .header-group .group-comment {
            background: var(--bg-secondary);
            position: sticky;
            right: 0;
            box-shadow: -2px 0 4px rgba(0,0,0,0.3);
        }
        
        .cost-table .cpu-section {
            background: rgba(251, 146, 60, 0.03);
        }
        
        .cost-table .header-detail th {
            background: var(--bg-secondary);
            padding: 0.25rem 0.3rem;
            text-align: center;
            font-weight: 500;
            font-size: 0.65rem;
            color: var(--text-secondary);
            border-bottom: 2px solid var(--border-color);
            white-space: nowrap;
        }
        
        .cost-table td {
            padding: 0.35rem 0.4rem;
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
            max-width: 130px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .cost-table .group-badge {
            display: inline-block;
            font-size: 0.7rem;
            padding: 0.1rem 0.3rem;
            background: rgba(168, 85, 247, 0.2);
            color: #a855f7;
            border-radius: 4px;
            margin-left: 0.3rem;
            vertical-align: middle;
        }
        
        .cost-table .asg-badge {
            display: inline-block;
            font-size: 0.7rem;
            padding: 0.1rem 0.3rem;
            background: rgba(251, 191, 36, 0.2);
            color: #f59e0b;
            border-radius: 4px;
            margin-left: 0.3rem;
            vertical-align: middle;
        }
        
        .cost-table .grouped-row {
            background: rgba(168, 85, 247, 0.03);
        }
        
        .cost-table .asg-row {
            background: rgba(251, 191, 36, 0.03);
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
        
        .cost-table .type-cell {
            font-weight: 500;
        }
        
        .cost-table .savings-cell {
            text-align: right;
            font-weight: 600;
        }
        
        .cost-table .savings-cell.positive {
            color: var(--accent-green);
        }
        
        .cost-table .ai-comment-cell {
            text-align: left;
            font-size: 0.7rem;
            color: var(--text-secondary);
            min-width: 100px;
            max-width: 130px;
            white-space: normal;
            word-break: break-word;
            position: sticky;
            right: 0;
            background: var(--bg-primary);
            box-shadow: -2px 0 4px rgba(0,0,0,0.3);
        }
        
        .cost-table tr:hover .ai-comment-cell {
            background: var(--bg-secondary);
        }
        
        /* セクション区切り */
        .cost-table .current-section {
            background: rgba(34, 211, 238, 0.03);
        }
        
        .cost-table .recommend-section {
            background: rgba(74, 222, 128, 0.03);
        }
        
        .cost-table .section-border-right {
            border-right: 2px solid var(--border-color);
        }
        
        /* 予測CPU値のスタイル - 現状と同じ見た目 */
        .cpu-badge.predicted {
            /* ~プレフィックスで予測を区別 */
        }
        
        /* ヘッダー2行目のセクション背景 */
        .cost-table .header-detail th:nth-child(n+1):nth-child(-n+8) {
            background: rgba(34, 211, 238, 0.05);
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
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            background: var(--bg-secondary);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .copy-btn {
            padding: 0.4rem 0.8rem;
            font-size: 0.8rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }
        
        .copy-btn:hover {
            background: var(--accent-cyan);
            color: var(--bg-primary);
            border-color: var(--accent-cyan);
        }
        
        .copy-btn.copied {
            background: var(--accent-green);
            color: var(--bg-primary);
            border-color: var(--accent-green);
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
                <h1>AWS費用削減ツール</h1>
            </div>
        </header>

        <!-- SSO ログインセクション -->
        <div class="sso-section">
            <h3>🔐 アカウント選択 & SSO ログイン</h3>
            
            <div class="current-profile" id="currentProfile">
                <span>✅ ログイン中:</span>
                <span class="profile-name" id="currentProfileName"></span>
                <span class="account-badge" id="currentAccountId"></span>
                <button onclick="logout()" style="margin-left: auto; padding: 0.25rem 0.5rem; font-size: 0.85rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-secondary); cursor: pointer;">ログアウト</button>
            </div>
            
            <div class="profile-select-group">
                <select class="profile-select" id="profileSelect">
                    <option value="">-- アカウントを選択 --</option>
                </select>
                <button class="btn btn-sso" onclick="startSsoLogin()" id="ssoLoginBtn">
                    <span>🔑</span>
                    SSO ログイン
                </button>
            </div>
            
            <div class="sso-status" id="ssoStatus">
                <p id="ssoMessage">以下のリンクを開いて認証してください:</p>
                <div class="sso-code" id="ssoCode">XXXX-XXXX</div>
                <p>
                    <a class="sso-link" id="ssoLink" href="#" target="_blank">認証ページを開く</a>
                </p>
                <p style="margin-top: 1rem; color: var(--text-secondary); font-size: 0.9rem;">
                    認証が完了したら下のボタンをクリックしてください
                </p>
                <button class="btn btn-primary" onclick="completeSsoLogin()" id="completeLoginBtn" style="margin-top: 1rem;">
                    <span>✅</span>
                    認証完了
                </button>
            </div>
        </div>

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
                't3.nano': 0.0052, 't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416, 't3.large': 0.0832, 't3.xlarge': 0.1664, 't3.2xlarge': 0.3328,
                't3a.nano': 0.0047, 't3a.micro': 0.0094, 't3a.small': 0.0188, 't3a.medium': 0.0376, 't3a.large': 0.0752, 't3a.xlarge': 0.1504, 't3a.2xlarge': 0.3008,
                't4g.nano': 0.0042, 't4g.micro': 0.0084, 't4g.small': 0.0168, 't4g.medium': 0.0336, 't4g.large': 0.0672, 't4g.xlarge': 0.1344, 't4g.2xlarge': 0.2688,
                'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm6i.large': 0.096, 'm6i.xlarge': 0.192,
                'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34, 'c5.4xlarge': 0.68,
                'c5a.large': 0.077, 'c5a.xlarge': 0.154, 'c5a.2xlarge': 0.308, 'c5a.4xlarge': 0.616,
                'c6i.large': 0.085, 'c6i.xlarge': 0.17, 'c6i.2xlarge': 0.34,
                'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504
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
        
        // スケールダウン（価格が下がる）かどうかをチェック
        function isScaleDown(currentType, recommendedType, service = 'ec2') {
            if (!currentType || !recommendedType || currentType === recommendedType) {
                return false;
            }
            const currentPrice = getInstancePrice(currentType, service);
            const recommendedPrice = getInstancePrice(recommendedType, service);
            // 推奨価格が現在価格より低い場合のみスケールダウンとみなす
            return recommendedPrice < currentPrice;
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
        
        // セクションデータをクリップボードにコピー
        function copySectionData(sectionKey, btn) {
            if (!globalResources || !globalResources[sectionKey]) {
                alert('データがありません');
                return;
            }
            
            const data = globalResources[sectionKey];
            const isEc2 = sectionKey === 'ec2';
            
            let rows = [];
            
            // グループ化されたデータを取得
            const processedData = isEc2 ? groupAutoScaleInstances(data) : data;
            
            processedData.forEach(item => {
                const name = item.name || '-';
                const instanceId = item.instance_id || '-';
                const instanceType = item.instance_type || '-';
                const count = item.count || 1;
                
                // MCP提案を取得
                const mcpRec = globalMcpRecommendations ? globalMcpRecommendations[name] : null;
                let recType = '';  // 提案がない場合は空
                let recCount = '';  // 提案がない場合は空
                
                if (mcpRec && mcpRec.recommendation) {
                    recType = mcpRec.recommendation.recommended_type;
                    recCount = count;  // 台数は現状と同じ
                }
                
                // 行を作成: インスタンス名, インスタンスID, サイズ, 台数, (EBS), (月額), (合計), (空), (空), 提案サイズ, 提案台数
                // EBS・月額・合計は計算式なので空欄でスキップ
                let row;
                if (isEc2) {
                    row = `${name}\\t${instanceId}\\t${instanceType}\\t${count}\\t\\t\\t\\t\\t\\t${recType}\\t${recCount}`;
                } else {
                    // RDS/DocDB/ElastiCacheはIDがないので空欄
                    row = `${name}\\t\\t${instanceType}\\t${count}\\t\\t\\t\\t\\t\\t${recType}\\t${recCount}`;
                }
                rows.push(row);
            });
            
            const text = rows.join('\\n');
            
            // クリップボードにコピー
            navigator.clipboard.writeText(text).then(() => {
                // ボタンのスタイルを一時的に変更
                const originalText = btn.textContent;
                btn.textContent = '✓ コピー完了';
                btn.classList.add('copied');
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.classList.remove('copied');
                }, 2000);
            }).catch(err => {
                console.error('Copy failed:', err);
                alert('コピーに失敗しました');
            });
        }

        // サイズ順序定義（共通）
        const SIZE_ORDER = {
            'nano': 0.25, 'micro': 0.5, 'small': 1, 'medium': 2, 
            'large': 4, 'xlarge': 8, '2xlarge': 16, '4xlarge': 32, 
            '8xlarge': 64, '12xlarge': 96, '16xlarge': 128, '24xlarge': 192
        };
        const SIZE_NAMES = ['nano', 'micro', 'small', 'medium', 'large', 'xlarge', '2xlarge', '4xlarge', '8xlarge', '12xlarge', '16xlarge', '24xlarge'];
        
        // インスタンスタイプからサイズ係数を推定（CPU予測用）
        function getInstanceSizeRatio(fromType, toType) {
            if (!fromType || !toType || fromType === '-' || toType === '-') return null;
            
            // タイプからサイズを抽出 (例: t3.medium -> medium, db.r5.large -> large)
            const getSize = (type) => {
                const parts = type.split('.');
                const sizePart = parts[parts.length - 1];
                return SIZE_ORDER[sizePart] || null;
            };
            
            const fromSize = getSize(fromType);
            const toSize = getSize(toType);
            
            if (fromSize && toSize && toSize > 0) {
                return fromSize / toSize;
            }
            return null;
        }
        
        // 自動スケールダウン候補を計算（Bedrockの提案がない場合用）
        // ファミリー別の最小サイズ
        const FAMILY_MIN_SIZE = {
            // EC2 - C/M/R系は large が最小
            'c5': 'large', 'c5a': 'large', 'c5n': 'large', 'c6i': 'large', 'c6a': 'large', 'c6g': 'large', 'c7g': 'large',
            'm5': 'large', 'm5a': 'large', 'm5n': 'large', 'm6i': 'large', 'm6a': 'large', 'm6g': 'large', 'm7g': 'large',
            'r5': 'large', 'r5a': 'large', 'r5n': 'large', 'r6i': 'large', 'r6a': 'large', 'r6g': 'large', 'r7g': 'large',
            // EC2 T系は nano が最小
            't3': 'nano', 't3a': 'nano', 't4g': 'nano',
            // RDS/DocumentDB - R/M系は large が最小、T系は medium が最小
            'db.r5': 'large', 'db.r6g': 'large', 'db.m5': 'large', 'db.m6g': 'large',
            'db.t3': 'medium', 'db.t4g': 'medium',
            // ElastiCache - R/M系は large が最小、T系は micro が最小
            'cache.r5': 'large', 'cache.r6g': 'large', 'cache.m5': 'large', 'cache.m6g': 'large',
            'cache.t3': 'micro', 'cache.t4g': 'micro',
        };
        
        function calculateAutoScaleDown(instanceType, cpuAvgMax, service = 'ec2') {
            if (!instanceType || cpuAvgMax === null || cpuAvgMax >= 40) {
                return null;  // 過剰スペックでない場合は提案しない
            }
            
            // インスタンスタイプをパース（例: t3a.large -> {prefix: 't3a', family: 't3a', size: 'large'}）
            const parts = instanceType.split('.');
            if (parts.length < 2) return null;
            
            const prefix = parts.slice(0, -1).join('.');  // db.t3, cache.t3, t3a など
            const currentSize = parts[parts.length - 1];
            const currentSizeValue = SIZE_ORDER[currentSize];
            if (!currentSizeValue) return null;
            
            // ファミリーの最小サイズを取得
            const minSize = FAMILY_MIN_SIZE[prefix] || 'nano';
            const minSizeIndex = SIZE_NAMES.indexOf(minSize);
            
            // 小さいサイズを順番に試す
            const currentSizeIndex = SIZE_NAMES.indexOf(currentSize);
            if (currentSizeIndex <= minSizeIndex) return null;  // 既に最小サイズ
            
            let bestCandidate = null;
            
            // 最小サイズまでしか試さない
            for (let i = currentSizeIndex - 1; i >= minSizeIndex; i--) {
                const candidateSize = SIZE_NAMES[i];
                const candidateType = prefix + '.' + candidateSize;
                const candidateSizeValue = SIZE_ORDER[candidateSize];
                
                // 予測CPU計算
                const ratio = currentSizeValue / candidateSizeValue;
                const predictedCpu = cpuAvgMax * ratio;
                
                // 価格が取得できるか確認
                const candidatePrice = getInstancePrice(candidateType, service);
                const currentPrice = getInstancePrice(instanceType, service);
                
                // 価格が下がり、予測CPUが70%以下なら候補
                if (candidatePrice < currentPrice && predictedCpu <= 70) {
                    bestCandidate = {
                        type: candidateType,
                        predictedCpu: predictedCpu,
                        price: candidatePrice
                    };
                    // 予測CPUが40-70%なら理想的なのでここで終了
                    if (predictedCpu >= 40) {
                        break;
                    }
                    // 40%未満でも続けて、より小さいサイズを探す
                } else if (predictedCpu > 70) {
                    // これ以上小さくするとCPU高すぎ、前の候補を使う
                    break;
                }
            }
            
            return bestCandidate;
        }
        
        // オートスケールインスタンスを名前でグループ化
        function groupAutoScaleInstances(data) {
            if (!data || data.length === 0) return [];
            
            const groups = {};
            
            data.forEach(item => {
                const name = item.name || '-';
                
                if (!groups[name]) {
                    groups[name] = {
                        name: name,
                        instance_type: item.instance_type,
                        count: 0,
                        instances: [],
                        ebs_type: item.ebs_type,
                        ebs_size: parseInt(item.ebs_size) || parseInt(item.ebs_size_gb) || 0,
                        cpu_avg_max_values: [],
                        cpu_max_values: []
                    };
                }
                
                const group = groups[name];
                group.count += (item.count || 1);
                group.instances.push(item.instance_id || '-');
                
                const cpuAvgMax = item.cpu_avg_max ?? item.max_cpu ?? null;
                const cpuMax = item.cpu_max ?? null;
                
                if (cpuAvgMax !== null) group.cpu_avg_max_values.push(cpuAvgMax);
                if (cpuMax !== null) group.cpu_max_values.push(cpuMax);
            });
            
            // グループを配列に変換し、集計値を計算
            return Object.values(groups).map(group => {
                // CPU AvgMax: グループ内の平均（オートスケールの場合、全体の平均が意味を持つ）
                const avgMaxAvg = group.cpu_avg_max_values.length > 0
                    ? group.cpu_avg_max_values.reduce((a, b) => a + b, 0) / group.cpu_avg_max_values.length
                    : null;
                
                // CPU Max: グループ内の最大値
                const maxMax = group.cpu_max_values.length > 0
                    ? Math.max(...group.cpu_max_values)
                    : null;
                
                return {
                    name: group.name,
                    instance_id: group.instances.length > 1 
                        ? `(${group.instances.length}台)` 
                        : group.instances[0],
                    instance_type: group.instance_type,
                    count: group.count,
                    ebs_type: group.ebs_type,
                    ebs_size: group.ebs_size,
                    ebs_size_gb: group.ebs_size,
                    cpu_avg_max: avgMaxAvg,
                    cpu_max: maxMax,
                    _instance_count: group.instances.length,
                    _is_grouped: group.instances.length > 1
                };
            });
        }
        
        function createCostTable(data, service, aiRecommendations) {
            if (!data || data.length === 0) {
                return '<div class="empty-state"><div class="icon">📭</div><p>データがありません</p></div>';
            }
            
            const isEc2 = service === 'ec2';
            const HOURS_PER_MONTH = 730;
            
            // EC2の場合、同名インスタンス（オートスケール等）をグループ化
            const processedData = isEc2 ? groupAutoScaleInstances(data) : data;
            
            let html = '<div class="cost-table-wrapper"><table class="cost-table"><thead>';
            
            // ヘッダー1行目（グループ）- 現状、変更提案、CPU使用率を分離
            html += '<tr class="header-group">';
            html += '<th rowspan="2" class="group-name">名前</th>';
            if (isEc2) html += '<th rowspan="2" class="group-name">ID</th>';
            // 現状グループ: EC2は6列（タイプ、台数、月額、EBS、GB、EBS料金）、その他は3列
            html += '<th colspan="' + (isEc2 ? '6' : '3') + '" class="group-current">📊 現状</th>';
            // 変更提案グループ: 3列（タイプ、月額、削減額）
            html += '<th colspan="3" class="group-recommend">💡 変更提案</th>';
            // CPU使用率グループ: 4列（AvgMax、Max、予測AvgMax、予測Max）
            html += '<th colspan="4" class="group-cpu">📈 CPU使用率</th>';
            html += '<th rowspan="2" class="group-comment">AIコメント</th>';
            html += '</tr>';
            
            // ヘッダー2行目（詳細）
            html += '<tr class="header-detail">';
            // 現状の詳細
            html += '<th>タイプ</th><th>台数</th><th>月額</th>';
            if (isEc2) html += '<th>EBS</th><th>GB</th><th>EBS料金</th>';
            // 変更提案の詳細
            html += '<th>提案タイプ</th><th>月額</th><th>削減額</th>';
            // CPU使用率の詳細
            html += '<th>AvgMax</th><th>Max</th><th>予測Avg</th><th>予測Max</th>';
            html += '</tr></thead><tbody>';
            
            processedData.forEach(item => {
                const name = item.name || '-';
                const instanceId = item.instance_id || '-';
                const instanceType = item.instance_type || '-';
                const count = item.count || 1;
                const ebsType = item.ebs_type || '-';
                const ebsSize = parseInt(item.ebs_size) || parseInt(item.ebs_size_gb) || 0;
                const cpuAvgMax = item.cpu_avg_max ?? item.max_cpu ?? null;
                const cpuMax = item.cpu_max ?? null;
                
                // 現状コスト計算
                const hourlyPrice = getInstancePrice(instanceType, service);
                const monthlyInstance = hourlyPrice * HOURS_PER_MONTH * count;
                const monthlyEbs = isEc2 ? getEbsPrice(ebsType) * ebsSize * count : 0;
                const monthlyTotal = monthlyInstance + monthlyEbs;
                
                // MCP提案を優先検索（名前で検索）
                const mcpRec = globalMcpRecommendations ? globalMcpRecommendations[name] : null;
                
                // AI提案を検索（部分一致・正規化対応）- MCPがない場合のフォールバック
                const normalizeNameForMatch = (n) => {
                    if (!n) return '';
                    return n.toLowerCase()
                        .replace(/[《》【】\[\]\(\)「」『』]/g, '')  // 括弧類を削除
                        .replace(/[\s\-_]/g, '')  // 空白・ハイフン・アンダースコアを削除
                        .trim();
                };
                const normalizedName = normalizeNameForMatch(name);
                const rec = aiRecommendations ? aiRecommendations.find(r => {
                    const normalizedRecName = normalizeNameForMatch(r.name);
                    // 完全一致、または正規化後の部分一致
                    return r.name === name || 
                           normalizedRecName === normalizedName ||
                           normalizedName.includes(normalizedRecName) ||
                           normalizedRecName.includes(normalizedName) ||
                           (item.instance_id && r.instance_id === item.instance_id);
                }) : null;
                
                // CPU予測とコスト計算用の変数
                let predictedCpuAvg = null;
                let predictedCpuMax = null;
                let actualRecType = '-';
                let actualRecMonthly = null;
                let actualSavings = null;
                let actualAiComment = '-';
                
                // CPU値に基づいて正しい判定を決定（40-70%が適正）
                if (cpuAvgMax !== null && cpuAvgMax !== undefined) {
                    if (cpuAvgMax < 40) {
                        actualAiComment = '過剰スペック';
                    } else if (cpuAvgMax <= 70) {
                        actualAiComment = '適正';
                    } else {
                        actualAiComment = 'スペック不足';
                    }
                } else {
                    // CPUデータがない場合
                    actualAiComment = '-';
                }
                
                // 1. MCP提案を優先使用（サーバーサイドで計算済み）
                if (mcpRec && mcpRec.recommendation) {
                    const mcpData = mcpRec.recommendation;
                    actualRecType = mcpData.recommended_type;
                    predictedCpuAvg = mcpData.predicted_cpu;
                    
                    // 価格計算
                    const recPrice = mcpData.recommended_price || getInstancePrice(actualRecType, service);
                    actualRecMonthly = recPrice * HOURS_PER_MONTH * count + monthlyEbs;
                    actualSavings = monthlyTotal - actualRecMonthly;
                    
                    // Max予測
                    if (cpuMax !== null) {
                        const ratio = getInstanceSizeRatio(instanceType, actualRecType);
                        if (ratio) predictedCpuMax = Math.min(cpuMax * ratio, 100);
                    }
                    
                    // コメント設定
                    actualAiComment = mcpRec.reason || (predictedCpuAvg >= 40 ? '変更推奨' : '過剰（更に削減余地あり）');
                    console.log('Using MCP recommendation:', name, instanceType, '->', actualRecType, 'predicted:', predictedCpuAvg + '%');
                }
                // 2. MCPに提案がなく、reasonがある場合はそれを表示
                else if (mcpRec && mcpRec.reason) {
                    actualAiComment = mcpRec.reason;
                }
                // 3. Bedrockの提案（フォールバック）
                else if (rec && rec.recommended_type && rec.recommended_type !== '-' && cpuAvgMax !== null) {
                    // 提案されたインスタンスタイプが存在するか検証
                    const isValidInstanceType = (recType) => {
                        const parts = recType.split('.');
                        if (parts.length < 2) return false;
                        const family = parts.slice(0, -1).join('.');
                        const size = parts[parts.length - 1];
                        const minSize = FAMILY_MIN_SIZE[family];
                        if (minSize) {
                            const minIdx = SIZE_NAMES.indexOf(minSize);
                            const sizeIdx = SIZE_NAMES.indexOf(size);
                            if (sizeIdx < minIdx) return false;  // 最小サイズより小さい → 存在しない
                        }
                        return true;
                    };
                    
                    if (!isValidInstanceType(rec.recommended_type)) {
                        console.log('Rejected invalid instance type:', rec.recommended_type);
                    } else {
                        const ratio = getInstanceSizeRatio(instanceType, rec.recommended_type);
                        if (ratio !== null) {
                            predictedCpuAvg = Math.min(cpuAvgMax * ratio, 100);
                            if (cpuMax !== null) {
                                predictedCpuMax = Math.min(cpuMax * ratio, 100);
                            }
                            
                            // 予測CPUが70%超の場合のみ却下
                            if (predictedCpuAvg > 70) {
                                console.log('Rejected Bedrock recommendation (predicted CPU > 70%):', instanceType, '->', rec.recommended_type);
                            } else {
                                actualRecType = rec.recommended_type;
                                const recPrice = getInstancePrice(actualRecType, service);
                                actualRecMonthly = recPrice * HOURS_PER_MONTH * count + monthlyEbs;
                                actualSavings = monthlyTotal - actualRecMonthly;
                                actualAiComment = predictedCpuAvg >= 40 ? '変更推奨' : '過剰（更に削減余地あり）';
                            }
                        }
                    }
                }
                // 4. ローカル自動計算（最終フォールバック）
                else if (cpuAvgMax !== null && cpuAvgMax < 40) {
                    const autoRec = calculateAutoScaleDown(instanceType, cpuAvgMax, service);
                    if (autoRec) {
                        actualRecType = autoRec.type;
                        const autoRecMonthly = autoRec.price * HOURS_PER_MONTH * count + monthlyEbs;
                        actualRecMonthly = autoRecMonthly;
                        actualSavings = monthlyTotal - autoRecMonthly;
                        predictedCpuAvg = autoRec.predictedCpu;
                        if (cpuMax !== null) {
                            const ratio = getInstanceSizeRatio(instanceType, autoRec.type);
                            if (ratio) predictedCpuMax = Math.min(cpuMax * ratio, 100);
                        }
                        actualAiComment = predictedCpuAvg >= 40 ? '変更推奨（ローカル計算）' : '過剰（更に削減余地あり）';
                        console.log('Using local auto-calculation:', instanceType, '->', autoRec.type);
                    } else {
                        // 自動計算でも提案がない場合は最小構成の可能性
                        const sizePart = instanceType.split('.').pop();
                        if (sizePart === 'nano' || sizePart === 'micro') {
                            actualAiComment = '最小構成';
                        }
                    }
                }
                
                // 最小構成チェック（MCPやBedrockで提案がない場合）
                if (actualRecType === '-' && (cpuAvgMax === null || cpuAvgMax < 40)) {
                    const sizePart = instanceType.split('.').pop();
                    // ファミリー別の最小サイズ判定
                    const isMinSize = (() => {
                        // db.r系, db.m系, cache.r系, cache.m系 は large が最小
                        if (instanceType.match(/^(db\.|cache\.)(r|m)\d+g?\./)) {
                            return sizePart === 'large';
                        }
                        // RDS/DocumentDB T系は medium が最小
                        if (instanceType.match(/^db\.t\d+g?\./)) {
                            return sizePart === 'medium';
                        }
                        // ElastiCache T系は micro が最小
                        if (instanceType.match(/^cache\.t\d+g?\./)) {
                            return sizePart === 'micro';
                        }
                        // EC2 c系, m系, r系 は large が最小
                        if (instanceType.match(/^(c5|c5a|c5n|c6|c7|m5|m5a|m6|m7|r5|r5a|r6|r7)/)) {
                            return sizePart === 'large';
                        }
                        // EC2 t系は nano が最小
                        return sizePart === 'nano';
                    })();
                    
                    if (isMinSize) {
                        actualAiComment = '最小構成';
                    } else if (cpuAvgMax === null) {
                        // CPUデータなし
                        actualAiComment = 'CPU取得不可';
                    } else if (cpuAvgMax < 40) {
                        // CPU < 40%だが、スケールダウンするとCPU超過のため提案なし
                        actualAiComment = 'スケールダウン候補なし';
                    }
                }
                
                // 変更提案がない場合はCPU予測をクリア
                if (actualRecType === '-') {
                    predictedCpuAvg = null;
                    predictedCpuMax = null;
                }
                
                const isAsg = item.is_auto_scaling || item.auto_scaling_group;
                const rowClass = isAsg ? 'asg-row' : (item._is_grouped ? 'grouped-row' : '');
                html += '<tr' + (rowClass ? ` class="${rowClass}"` : '') + '>';
                // 名前・ID
                const badge = isAsg 
                    ? ' <span class="asg-badge">⚡ASG</span>'
                    : (item._is_grouped ? ' <span class="group-badge">🔗グループ</span>' : '');
                html += `<td class="name-cell">${name}${badge}</td>`;
                if (isEc2) html += `<td class="id-cell">${instanceId !== 'None' ? instanceId : '-'}</td>`;
                // 現状セクション（CPU以外）
                html += `<td class="current-section type-cell">${instanceType}</td>`;
                html += `<td class="current-section num-cell">${count}</td>`;
                if (isEc2) {
                    html += `<td class="current-section money-cell">${formatMoney(monthlyInstance)}</td>`;
                    html += `<td class="current-section">${ebsType}</td>`;
                    html += `<td class="current-section num-cell">${ebsSize || '-'}</td>`;
                    html += `<td class="current-section section-border-right money-cell">${ebsSize ? formatMoney(monthlyEbs) : '-'}</td>`;
                } else {
                    html += `<td class="current-section section-border-right money-cell">${formatMoney(monthlyInstance)}</td>`;
                }
                // 変更提案セクション（CPU予測以外）
                html += `<td class="recommend-section type-cell">${actualRecType}</td>`;
                html += `<td class="recommend-section money-cell">${actualRecMonthly !== null ? formatMoney(actualRecMonthly) : '-'}</td>`;
                html += `<td class="recommend-section section-border-right savings-cell ${actualSavings > 0 ? 'positive' : ''}">${actualSavings !== null && actualSavings > 0 ? '-' + formatMoney(actualSavings) + '/月' : '-'}</td>`;
                // CPU使用率セクション（AvgMax/Maxは常に表示、予測値は提案がある場合のみ）
                const hasCpuData = cpuAvgMax !== null && cpuAvgMax !== undefined;
                const showPredicted = actualRecType !== '-';
                html += `<td class="cpu-section">${hasCpuData ? `<span class="cpu-badge ${getCpuClass(cpuAvgMax)}">${formatCpu(cpuAvgMax)}</span>` : '-'}</td>`;
                html += `<td class="cpu-section">${hasCpuData && cpuMax !== null ? `<span class="cpu-badge ${getCpuClass(cpuMax)}">${formatCpu(cpuMax)}</span>` : '-'}</td>`;
                html += `<td class="cpu-section">${showPredicted && predictedCpuAvg !== null ? `<span class="cpu-badge ${getCpuClass(predictedCpuAvg)} predicted">~${predictedCpuAvg.toFixed(1)}%</span>` : '-'}</td>`;
                html += `<td class="cpu-section section-border-right">${showPredicted && predictedCpuMax !== null ? `<span class="cpu-badge ${getCpuClass(predictedCpuMax)} predicted">~${predictedCpuMax.toFixed(1)}%</span>` : '-'}</td>`;
                // AIコメント
                html += `<td class="ai-comment-cell">${actualAiComment}</td>`;
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
        let globalMcpRecommendations = {};  // MCPからの推奨
        
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
                        judgment: '',
                        current_type: ''
                    };
                }
                
                // 現在のタイプを検出（現在: タイプ 形式）
                if (currentInstance && line.includes('現在:')) {
                    const typeMatch = line.match(/現在:\\s*((?:db\\.|cache\\.)?[a-z][a-z0-9]*\\.[a-z0-9]+)/i);
                    if (typeMatch) {
                        currentInstance.current_type = typeMatch[1];
                    }
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
                            // タイプ抽出 (t3.medium, db.t3.medium, cache.t3.medium など)
                            const typeMatch = proposal.match(/((?:db\\.|cache\\.)?[a-z][a-z0-9]*\\.[a-z0-9]+)/i);
                            if (typeMatch) {
                                const recommendedType = typeMatch[1];
                                // スケールダウンかチェック（価格が下がる場合のみ採用）
                                if (isScaleDown(currentInstance.current_type, recommendedType, currentSection)) {
                                    currentInstance.recommended_type = recommendedType;
                                    currentInstance.note = currentInstance.judgment || '過剰スペック';
                                } else {
                                    // スケールアップまたは同等の場合は無視
                                    console.log('Rejected scale-up proposal:', currentInstance.current_type, '->', recommendedType);
                                    currentInstance.recommended_type = '-';
                                    currentInstance.note = currentInstance.judgment || '適正';
                                }
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
                    card.dataset.sectionKey = section.key;
                    card.innerHTML = `
                        <div class="resource-card-header">
                            <div class="section-title">
                                <div class="icon ${section.key}">${section.emoji}</div>
                                ${section.title}
                                <span style="color: var(--text-secondary); font-weight: 400; font-size: 0.9rem;">(${data.length}件)</span>
                            </div>
                            <button class="copy-btn" onclick="copySectionData('${section.key}', this)" title="データをコピー">
                                📋 コピー
                            </button>
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

        // SSO 関連のグローバル変数（sessionStorage から復元）
        let ssoState = null;
        let currentCredentials = JSON.parse(sessionStorage.getItem('ssoCredentials') || 'null');
        let currentProfile = sessionStorage.getItem('ssoProfile') || null;
        
        // 認証情報を保存する関数
        function saveCredentials(credentials, profile) {
            currentCredentials = credentials;
            currentProfile = profile;
            if (credentials) {
                sessionStorage.setItem('ssoCredentials', JSON.stringify(credentials));
                sessionStorage.setItem('ssoProfile', profile);
            } else {
                sessionStorage.removeItem('ssoCredentials');
                sessionStorage.removeItem('ssoProfile');
            }
        }
        
        // ログアウト
        function logout() {
            saveCredentials(null, null);
            ssoState = null;
            document.getElementById('currentProfile').classList.remove('visible');
            document.getElementById('ssoStatus').classList.remove('visible');
            showStatus('ログアウトしました', 'success');
        }

        // プロファイル一覧を読み込み
        async function loadProfiles() {
            try {
                const response = await fetch(window.location.href, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'get_profiles' })
                });
                const data = await response.json();
                
                const select = document.getElementById('profileSelect');
                select.innerHTML = '<option value="">-- アカウントを選択 --</option>';
                
                for (const profile of data.profiles) {
                    const option = document.createElement('option');
                    option.value = profile.name;
                    option.textContent = `${profile.name} (${profile.accountId})`;
                    select.appendChild(option);
                }
            } catch (e) {
                console.error('Failed to load profiles:', e);
            }
        }

        // SSO ログイン開始
        async function startSsoLogin() {
            const profileSelect = document.getElementById('profileSelect');
            const profile = profileSelect.value;
            
            if (!profile) {
                alert('アカウントを選択してください');
                return;
            }
            
            const ssoLoginBtn = document.getElementById('ssoLoginBtn');
            ssoLoginBtn.disabled = true;
            
            try {
                showStatus('SSO ログインを開始中...', 'loading');
                
                const response = await fetch(window.location.href, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'start_sso_login', profile })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    throw new Error(data.error);
                }
                
                // SSO 状態を保存
                ssoState = {
                    profile,
                    clientId: data.clientId,
                    clientSecret: data.clientSecret,
                    deviceCode: data.deviceCode
                };
                
                // UI を更新
                document.getElementById('ssoCode').textContent = data.userCode;
                document.getElementById('ssoLink').href = data.verificationUriComplete || data.verificationUri;
                document.getElementById('ssoLink').textContent = data.verificationUri;
                document.getElementById('ssoStatus').classList.add('visible');
                
                hideStatus();
                
                // 認証ページを新しいタブで開く
                window.open(data.verificationUriComplete || data.verificationUri, '_blank');
                
            } catch (e) {
                showStatus('SSO エラー: ' + e.message, 'error');
            } finally {
                ssoLoginBtn.disabled = false;
            }
        }

        // SSO ログイン完了
        async function completeSsoLogin() {
            if (!ssoState) {
                alert('先に SSO ログインを開始してください');
                return;
            }
            
            const completeBtn = document.getElementById('completeLoginBtn');
            completeBtn.disabled = true;
            
            try {
                showStatus('認証を確認中...', 'loading');
                
                const response = await fetch(window.location.href, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: 'complete_sso_login',
                        profile: ssoState.profile,
                        clientId: ssoState.clientId,
                        clientSecret: ssoState.clientSecret,
                        deviceCode: ssoState.deviceCode
                    })
                });
                
                const data = await response.json();
                
                if (data.error === 'authorization_pending') {
                    showStatus('まだ認証が完了していません。ブラウザで認証を完了してください。', 'error');
                    completeBtn.disabled = false;
                    return;
                }
                
                if (data.error) {
                    throw new Error(data.error);
                }
                
                // 認証情報を保存（sessionStorage にも保存）
                console.log('SSO login response:', data);
                console.log('Credentials received:', data.credentials);
                saveCredentials(data.credentials, data.profile);
                console.log('currentCredentials set to:', currentCredentials);
                
                // UI を更新
                document.getElementById('ssoStatus').classList.remove('visible');
                document.getElementById('currentProfile').classList.add('visible');
                document.getElementById('currentProfileName').textContent = data.profile;
                document.getElementById('currentAccountId').textContent = data.accountId;
                
                showStatus('✅ ログイン成功！「分析を実行」をクリックしてください。', 'success');
                
            } catch (e) {
                showStatus('認証エラー: ' + e.message, 'error');
            } finally {
                completeBtn.disabled = false;
            }
        }

        async function runAnalysis() {
            const analyzeBtn = document.getElementById('analyzeBtn');
            analyzeBtn.disabled = true;

            try {
                showStatus('AWSリソース情報を収集中...', 'loading');
                
                // SSO 認証情報がある場合はそれを使用
                let requestBody = { action: 'analyze' };
                console.log('currentCredentials:', currentCredentials);
                console.log('currentProfile:', currentProfile);
                
                if (currentCredentials && currentCredentials.accessKeyId) {
                    console.log('Using SSO credentials for analysis');
                    requestBody = {
                        action: 'analyze_with_credentials',
                        credentials: currentCredentials,
                        profile: currentProfile
                    };
                } else {
                    console.log('No SSO credentials, using Lambda role');
                }
                
                console.log('Request body:', JSON.stringify(requestBody));
                
                const response = await fetch(window.location.href, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestBody)
                });

                if (!response.ok) {
                    throw new Error('API request failed');
                }

                const data = await response.json();
                
                // MCP から取得した価格データを設定
                if (data.pricing) {
                    setPricingData(data.pricing);
                }
                
                // MCP から取得した推奨を設定
                if (data.mcp_recommendations) {
                    globalMcpRecommendations = data.mcp_recommendations;
                    console.log('MCP recommendations loaded:', Object.keys(globalMcpRecommendations).length, 'items');
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

        // テキスト形式のリソースデータをオブジェクト形式に変換
        function parseResourceText(text) {
            const resources = { ec2: [], rds: [], redis: [], memcache: [], docdb: [] };
            if (!text) return resources;
            
            const lines = text.split('\\n');
            let currentSection = null;
            let headers = [];
            
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                
                // セクション判定
                if (trimmed.startsWith('EC2 :') || trimmed === 'EC2 :') {
                    currentSection = 'ec2';
                    headers = [];
                    continue;
                } else if (trimmed.startsWith('RDS :') || trimmed === 'RDS :') {
                    currentSection = 'rds';
                    headers = [];
                    continue;
                } else if (trimmed.startsWith('Redis :') || trimmed === 'Redis :') {
                    currentSection = 'redis';
                    headers = [];
                    continue;
                } else if (trimmed.startsWith('Memcached :') || trimmed === 'Memcached :') {
                    currentSection = 'memcache';
                    headers = [];
                    continue;
                } else if (trimmed.startsWith('DocumentDB :') || trimmed === 'DocumentDB :') {
                    currentSection = 'docdb';
                    headers = [];
                    continue;
                }
                
                if (!currentSection) continue;
                
                const cols = trimmed.split('\\t');
                
                // ヘッダー行
                if (cols[0] === 'Instance Name' || cols[0] === 'Cluster Name') {
                    headers = cols;
                    continue;
                }
                
                if (headers.length === 0 || cols.length < 4) continue;
                
                // データ行をパース
                if (currentSection === 'ec2') {
                    resources.ec2.push({
                        name: cols[0] || '',
                        instance_id: cols[1] || '',
                        instance_type: cols[2] || '',
                        count: parseInt(cols[3]) || 1,
                        ebs_type: cols[4] || '',
                        ebs_size_gb: parseInt(cols[5]) || 0,
                        cpu_avg_max: parseFloat(cols[6]) || 0,
                        cpu_max: parseFloat(cols[7]) || 0,
                        timestamp: cols[8] || ''
                    });
                } else {
                    // RDS, Redis, Memcache, DocumentDB
                    resources[currentSection].push({
                        name: cols[0] || '',
                        instance_type: cols[1] || '',
                        count: parseInt(cols[2]) || 1,
                        cpu_avg_max: parseFloat(cols[3]) || 0,
                        cpu_max: parseFloat(cols[4]) || 0,
                        timestamp: cols[5] || ''
                    });
                }
            }
            
            return resources;
        }
        
        // URLハッシュからデータを読み取る
        function loadFromUrlHash() {
            const hash = window.location.hash;
            if (!hash || !hash.startsWith('#data=')) {
                return null;
            }
            
            try {
                const encoded = hash.substring(6); // '#data=' を削除
                const jsonStr = atob(encoded);
                const data = JSON.parse(jsonStr);
                return data;
            } catch (e) {
                console.error('Failed to parse URL hash data:', e);
                return null;
            }
        }

        // ページ読み込み時の処理
        document.addEventListener('DOMContentLoaded', function() {
            console.log('Page loaded');
            
            // プロファイル一覧を読み込み
            loadProfiles();
            
            // sessionStorage から認証情報を復元した場合、UI を更新
            if (currentCredentials && currentProfile) {
                console.log('Restored credentials from sessionStorage for profile:', currentProfile);
                document.getElementById('currentProfile').classList.add('visible');
                document.getElementById('currentProfileName').textContent = currentProfile;
                // accountId は credentials に含まれていないので、profiles から取得する必要がある
                fetch(window.location.href, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'get_profiles' })
                }).then(r => r.json()).then(data => {
                    const profile = data.profiles.find(p => p.name === currentProfile);
                    if (profile) {
                        document.getElementById('currentAccountId').textContent = profile.accountId;
                    }
                });
            }
            
            // URLハッシュからデータを読み取り
            const hashData = loadFromUrlHash();
            if (hashData) {
                console.log('Loading data from URL hash:', hashData.profile, hashData.timestamp);
                
                // リソーステキストをパース
                const resources = parseResourceText(hashData.resources);
                console.log('Parsed resources:', resources);
                
                // AI分析結果があればパース
                let aiRecommendations = null;
                if (hashData.analysis) {
                    aiRecommendations = parseAiRecommendations(hashData.analysis);
                }
                
                // 表示
                renderResources(resources, aiRecommendations);
                document.getElementById('resultsSection').classList.add('visible');
                
                // AI分析結果を表示
                if (hashData.analysis) {
                    renderAnalysis(hashData.analysis, hashData.token_usage);
                }
                
                // プロファイル情報を表示
                if (hashData.profile && hashData.profile !== 'unknown') {
                    showStatus('プロファイル: ' + hashData.profile + ' (' + (hashData.timestamp || '') + ')', 'success');
                }
            }
        });
    </script>
</body>
</html>'''


# 許可するIPアドレスリスト
ALLOWED_IPS = [
    '111.108.92.4',
]


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
    
    # IP制限チェック
    source_ip = event.get('requestContext', {}).get('http', {}).get('sourceIp', '')
    if source_ip not in ALLOWED_IPS:
        print(f"Access denied for IP: {source_ip}")
        return {
            'statusCode': 403,
            'headers': {'Content-Type': 'text/plain'},
            'body': f'Access denied. Your IP: {source_ip}'
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
            
            action = body.get('action', 'analyze')
            print(f"Received action: {action}")
            print(f"Request body keys: {list(body.keys())}")
            
            # SSO ログイン開始
            if action == 'start_sso_login':
                profile = body.get('profile')
                if not profile:
                    return {
                        'statusCode': 400,
                        'headers': headers,
                        'body': json.dumps({'error': 'profile is required'})
                    }
                result = start_sso_login(profile)
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps(result, ensure_ascii=False)
                }
            
            # SSO ログイン完了
            if action == 'complete_sso_login':
                profile = body.get('profile')
                client_id = body.get('clientId')
                client_secret = body.get('clientSecret')
                device_code = body.get('deviceCode')
                
                if not all([profile, client_id, client_secret, device_code]):
                    return {
                        'statusCode': 400,
                        'headers': headers,
                        'body': json.dumps({'error': 'Missing required parameters'})
                    }
                
                result = complete_sso_login(profile, client_id, client_secret, device_code)
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps(result, ensure_ascii=False, default=str)
                }
            
            # SSO プロファイル一覧取得
            if action == 'get_profiles':
                profiles = [
                    {'name': name, 'accountId': profile['sso_account_id']}
                    for name, profile in SSO_PROFILES.items()
                ]
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps({'profiles': profiles}, ensure_ascii=False)
                }
            
            # ユーザー認証情報を使って分析
            if action == 'analyze_with_credentials':
                print("Processing analyze_with_credentials action")
                credentials = body.get('credentials')
                profile = body.get('profile', 'unknown')
                print(f"Profile: {profile}")
                print(f"Credentials keys: {list(credentials.keys()) if credentials else 'None'}")
                
                if not credentials:
                    return {
                        'statusCode': 400,
                        'headers': headers,
                        'body': json.dumps({'error': 'credentials is required'})
                    }
                
                # ユーザーの認証情報でリソース収集
                print("Step 1: Collecting resources with credentials...")
                resources = collect_resources_with_credentials(credentials)
                print(f"Step 1 done: EC2={len(resources.get('ec2', []))}, RDS={len(resources.get('rds', []))}")
                
                # MCP サーバーから価格情報を取得
                print("Step 2: Collecting pricing info...")
                pricing_info = collect_pricing_info(resources)
                print(f"Step 2 done: pricing keys = {list(pricing_info.keys())}")
                
                # MCP サーバーから一括スケールダウン提案を取得
                print("Step 2.5: Getting MCP batch recommendations...")
                mcp_recommendations = get_mcp_batch_recommendations(resources)
                print(f"Step 2.5 done: {len(mcp_recommendations)} recommendations")
                
                # Bedrock用にフォーマット（価格情報含む）
                print("Step 3: Formatting for Bedrock...")
                resource_text = format_resources_for_bedrock(resources, pricing_info)
                print(f"Step 3 done: text length = {len(resource_text)}")
                
                # Bedrockで分析（サマリーのみ使用）
                print("Step 4: Getting Bedrock analysis...")
                analysis_result = get_bedrock_analysis(resource_text)
                print(f"Step 4 done: analysis length = {len(analysis_result.get('text', ''))}")
                
                print("Step 5: Preparing response...")
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps({
                        'resources': resources,
                        'pricing': pricing_info,
                        'analysis': analysis_result['text'],
                        'token_usage': analysis_result['token_usage'],
                        'profile': profile,
                        'mcp_recommendations': mcp_recommendations
                    }, ensure_ascii=False, default=str)
                }
            
            # デフォルト: Lambda の IAM ロールでリソース収集
            resources = collect_all_resources()
            
            # MCP サーバーから価格情報を取得
            pricing_info = collect_pricing_info(resources)
            
            # MCP サーバーから一括スケールダウン提案を取得
            mcp_recommendations = get_mcp_batch_recommendations(resources)
            
            # Bedrock用にフォーマット（価格情報含む）
            resource_text = format_resources_for_bedrock(resources, pricing_info)
            
            # Bedrockで分析（サマリーのみ使用）
            analysis_result = get_bedrock_analysis(resource_text)
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'resources': resources,
                    'pricing': pricing_info,
                    'analysis': analysis_result['text'],
                    'token_usage': analysis_result['token_usage'],
                    'mcp_recommendations': mcp_recommendations
                }, ensure_ascii=False, default=str)
            }
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            tb = traceback.format_exc()
            print(f"ERROR: {error_msg}")
            print(f"TRACEBACK: {tb}")
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({
                    'error': error_msg,
                    'traceback': tb
                }, ensure_ascii=False)
            }
    
    # その他のメソッド
    return {
        'statusCode': 405,
        'headers': headers,
        'body': 'Method Not Allowed'
    }

