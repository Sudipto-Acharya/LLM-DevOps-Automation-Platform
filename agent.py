import boto3
import json
import time
import re
import signal
import sys
import requests
import paramiko
from datetime import datetime, timedelta
from groq import Groq
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# ============================================================
# Config — all values loaded from .env file
# ============================================================
GROQ_API_KEY        = os.getenv("GROQ_API_KEY")
AWS_REGION          = os.getenv("AWS_REGION", "us-east-1")
JENKINS_EC2_ID      = os.getenv("JENKINS_EC2_ID")
JENKINS_JOB_NAME    = os.getenv("JENKINS_JOB_NAME")
JENKINS_USER        = os.getenv("JENKINS_USER")
JENKINS_API_TOKEN   = os.getenv("JENKINS_API_TOKEN")
JENKINS_SSH_USER    = os.getenv("JENKINS_SSH_USER", "ec2-user")
BACKEND_EC2_ID      = os.getenv("BACKEND_EC2_ID")
BACKEND_SSH_USER    = os.getenv("BACKEND_SSH_USER", "ec2-user")
SSH_KEY_PATH        = os.getenv("SSH_KEY_PATH")
RDS_INSTANCE_ID     = os.getenv("RDS_INSTANCE_ID")
CLOUDFRONT_DIST_ID  = os.getenv("CLOUDFRONT_DIST_ID")
CLOUDFRONT_DOMAIN   = os.getenv("CLOUDFRONT_DOMAIN")

client = Groq(api_key=GROQ_API_KEY)


# Tracks what's active so Ctrl+C knows what to roll back
deployment_state = {
    "jenkins_started":    False,
    "backend_started":    False,
    "cloudfront_enabled": False,
    "rds_started":        False,
    "build_number":       None,
    "jenkins_url":        None,
    "backend_ip":         None,
}

# Tracks current infra status for menu
infra_status = {
    "ec2":        {},
    "cloudfront": {},
    "rds":        {},
    "s3":         [],
}


# ============================================================
# Ctrl+C Handler — full rollback
# ============================================================

def handle_interrupt(sig, frame):
    print("\n\n⛔ Ctrl+C detected — rolling back...\n")
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    cf  = boto3.client('cloudfront')
    rds = boto3.client('rds', region_name=AWS_REGION)

    if deployment_state["build_number"] and deployment_state["jenkins_url"]:
        try:
            crumb = get_jenkins_crumb(deployment_state["jenkins_url"])
            headers = {}
            if crumb:
                headers[crumb['crumbRequestField']] = crumb['crumb']
            requests.post(
                f"{deployment_state['jenkins_url']}/job/{JENKINS_JOB_NAME}"
                f"/{deployment_state['build_number']}/stop",
                auth=(JENKINS_USER, JENKINS_API_TOKEN),
                headers=headers, timeout=5
            )
            print("   ✅ Jenkins build stopped")
        except Exception as e:
            print(f"   ⚠️  Could not stop build: {e}")

    if deployment_state["jenkins_started"]:
        try:
            ec2.stop_instances(InstanceIds=[JENKINS_EC2_ID])
            print("   ✅ Jenkins EC2 stopping")
        except Exception as e:
            print(f"   ⚠️  {e}")

    if deployment_state["backend_started"]:
        try:
            ec2.stop_instances(InstanceIds=[BACKEND_EC2_ID])
            print("   ✅ Backend EC2 stopping")
        except Exception as e:
            print(f"   ⚠️  {e}")

    if deployment_state["rds_started"]:
        try:
            rds.stop_db_instance(DBInstanceIdentifier=RDS_INSTANCE_ID)
            print("   ✅ RDS stopping")
        except Exception as e:
            print(f"   ⚠️  {e}")

    if deployment_state["cloudfront_enabled"]:
        try:
            resp = cf.get_distribution_config(Id=CLOUDFRONT_DIST_ID)
            config = resp['DistributionConfig']
            etag = resp['ETag']
            config['Enabled'] = False
            cf.update_distribution(
                DistributionConfig=config,
                Id=CLOUDFRONT_DIST_ID,
                IfMatch=etag
            )
            print("   ✅ CloudFront disabled")
        except Exception as e:
            print(f"   ⚠️  {e}")

    print("\n🔴 Rollback complete. Exiting.\n")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_interrupt)


# ============================================================
# Infrastructure Check + Menu
# ============================================================

def fetch_infra_status():
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    cf  = boto3.client('cloudfront')

    try:
        resp = ec2.describe_instances()
        infra_status["ec2"] = {}
        for r in resp['Reservations']:
            for i in r['Instances']:
                iid  = i['InstanceId']
                name = next((t['Value'] for t in i.get('Tags', [])
                             if t['Key'] == 'Name'), 'Unnamed')
                infra_status["ec2"][iid] = {
                    "name":  name.strip(),
                    "state": i['State']['Name'],
                    "ip":    i.get('PublicIpAddress', '—'),
                    "type":  i['InstanceType'],
                }
    except Exception as e:
        print(f"   ⚠️  EC2: {e}")

    try:
        items = cf.list_distributions().get(
            'DistributionList', {}).get('Items', [])
        infra_status["cloudfront"] = {}
        for d in items:
            infra_status["cloudfront"][d['Id']] = {
                "enabled": d.get('Enabled', False),
                "domain":  d.get('DomainName', ''),
            }
    except Exception as e:
        print(f"   ⚠️  CloudFront: {e}")

    try:
        dbs = boto3.client('rds', region_name=AWS_REGION)\
                   .describe_db_instances().get('DBInstances', [])
        infra_status["rds"] = {}
        for db in dbs:
            infra_status["rds"][db['DBInstanceIdentifier']] = {
                "status": db['DBInstanceStatus']
            }
    except Exception as e:
        print(f"   ⚠️  RDS: {e}")

    try:
        infra_status["s3"] = [
            b['Name'] for b in
            boto3.client('s3').list_buckets().get('Buckets', [])
        ]
    except Exception as e:
        print(f"   ⚠️  S3: {e}")


def show_menu():
    print("\n" + "=" * 60)
    print("  🖥️   DevOps AI Agent — Infrastructure Status")
    print("=" * 60)

    print("\n  📦 EC2 INSTANCES")
    print("  " + "-" * 56)
    for iid, info in infra_status["ec2"].items():
        icon = "🟢" if info["state"] == "running" else "🔴"
        ip   = f"({info['ip']})" if info["state"] == "running" else ""
        print(f"  {icon}  {info['name']:<22} {info['state']:<12}"
              f"{info['type']:<16} {ip}")

    print("\n  🌐 CLOUDFRONT")
    print("  " + "-" * 56)
    for dist_id, info in infra_status["cloudfront"].items():
        icon   = "🟢" if info["enabled"] else "🔴"
        status = "enabled" if info["enabled"] else "disabled"
        print(f"  {icon}  {dist_id:<26} {status:<10} {info['domain']}")

    print("\n  🗄️  RDS")
    print("  " + "-" * 56)
    if not infra_status["rds"]:
        print("  —  No RDS instances found")
    for identifier, info in infra_status["rds"].items():
        icon = "🟢" if info["status"] == "available" else "🔴"
        print(f"  {icon}  {identifier:<32} {info['status']}")

    print("\n  🪣 S3 BUCKETS")
    print("  " + "-" * 56)
    for bucket in infra_status["s3"]:
        print(f"  📁  {bucket}")

    print("\n  🌍 LIVE FRONTEND URL")
    print("  " + "-" * 56)
    cf_enabled = any(
        v["enabled"] for v in infra_status["cloudfront"].values()
    )
    if cf_enabled:
        print(f"  🟢  {CLOUDFRONT_DOMAIN}")
    else:
        print(f"  🔴  {CLOUDFRONT_DOMAIN} (CloudFront disabled)")

    print("\n" + "=" * 60)
    print("  ⚡ QUICK COMMANDS")
    print("  " + "-" * 56)
    print("  deploy backend    — Start RDS + EC2 + verify containers")
    print("  deploy frontend   — Start Jenkins + CloudFront + build")
    print("  deploy all        — Deploy backend then frontend")
    print("  stop frontend     — Disable CloudFront only")
    print("  stop backend      — Stop EC2 + RDS")
    print("  stop all          — Stop everything")
    print("  status            — Refresh this menu")
    print("  exit              — Quit agent")
    print("=" * 60 + "\n")


def startup_check():
    print("\n🔍 Scanning your AWS infrastructure...\n")
    fetch_infra_status()
    show_menu()


# ============================================================
# SSH Helper
# ============================================================

def ssh_run_commands(ip, username, commands):
    try:
        key = paramiko.RSAKey.from_private_key_file(SSH_KEY_PATH)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=ip, username=username,
                    pkey=key, timeout=30)
        print(f"   ✅ SSH connected to {ip}")

        for label, cmd in commands:
            print(f"\n   🔧 {label}...")
            _, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            if out:
                for line in out.split('\n'):
                    print(f"      {line}")
            if err and 'warning' not in err.lower():
                print(f"      ⚠️  {err}")

        ssh.close()
        return True
    except Exception as e:
        print(f"   ❌ SSH error: {e}")
        return False


def ssh_restart_jenkins(ip):
    print(f"\n🔐 SSHing into Jenkins EC2 ({ip})...")
    return ssh_run_commands(ip, JENKINS_SSH_USER, [
        ("Fixing /tmp memory",
         "sudo mount -o remount,size=3G /tmp"),
        ("Restarting Jenkins",
         "sudo systemctl restart jenkins"),
        ("Checking Jenkins status",
         "sudo systemctl status jenkins --no-pager | tail -5"),
    ])


def ssh_restart_backend(ip):
    print(f"\n🔐 SSHing into Backend EC2 ({ip})...")
    return ssh_run_commands(ip, BACKEND_SSH_USER, [
        ("Restarting Docker",
         "sudo systemctl restart docker"),
        ("Restarting Nginx",
         "sudo systemctl restart nginx"),
        ("Checking Docker containers",
         "sudo docker ps --format "
         "'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"),
    ])


# ============================================================
# EC2 Helpers
# ============================================================

def wait_for_ec2_ip(instance_id, timeout=180):
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = ec2.describe_instances(InstanceIds=[instance_id])
            inst = resp['Reservations'][0]['Instances'][0]
            state = inst['State']['Name']
            ip = inst.get('PublicIpAddress', '')
            if state == 'running' and ip:
                return ip
            print(f"   ... state: {state} — waiting 10s")
        except Exception as e:
            print(f"   ⚠️  {e}")
        time.sleep(10)
    return None


def start_ec2(instance_id, label):
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        inst = resp['Reservations'][0]['Instances'][0]
        state = inst['State']['Name']
        if state == 'running':
            ip = inst.get('PublicIpAddress', '')
            print(f"   ✅ {label} already running — IP: {ip}")
            return ip
        ec2.start_instances(InstanceIds=[instance_id])
        print(f"   ✅ Start command sent to {label}")
    except Exception as e:
        print(f"   ⚠️  {e}")
    print(f"   ⏳ Waiting for {label} to boot...")
    ip = wait_for_ec2_ip(instance_id)
    if ip:
        print(f"   ✅ {label} running — IP: {ip}")
    return ip


def stop_ec2(instance_id, label):
    try:
        boto3.client('ec2', region_name=AWS_REGION)\
             .stop_instances(InstanceIds=[instance_id])
        print(f"   ✅ {label} stopping")
    except Exception as e:
        print(f"   ⚠️  {e}")


# ============================================================
# RDS Helpers
# ============================================================

def start_rds():
    rds = boto3.client('rds', region_name=AWS_REGION)
    print("🗄️  Starting RDS (awslearn-db)...")
    try:
        rds.start_db_instance(DBInstanceIdentifier=RDS_INSTANCE_ID)
        print("   ✅ RDS start command sent")
        deployment_state["rds_started"] = True
    except Exception as e:
        if 'InvalidDBInstanceState' in str(e):
            print("   ✅ RDS already running")
            return True
        print(f"   ⚠️  RDS: {e}")
        return False

    print("   ⏳ Waiting for RDS (~2-3 mins)...")
    for _ in range(24):
        try:
            resp = rds.describe_db_instances(
                DBInstanceIdentifier=RDS_INSTANCE_ID)
            status = resp['DBInstances'][0]['DBInstanceStatus']
            if status == 'available':
                print("   ✅ RDS available")
                return True
            print(f"   ... RDS: {status} — waiting 15s")
        except Exception as e:
            print(f"   ⚠️  {e}")
        time.sleep(15)
    print("   ⚠️  RDS not ready yet — continuing anyway")
    return False


def stop_rds():
    try:
        boto3.client('rds', region_name=AWS_REGION)\
             .stop_db_instance(DBInstanceIdentifier=RDS_INSTANCE_ID)
        print("   ✅ RDS stopping")
    except Exception as e:
        print(f"   ⚠️  RDS: {e}")


# ============================================================
# CloudFront Helpers
# ============================================================

def enable_cloudfront():
    cf = boto3.client('cloudfront')
    try:
        resp = cf.get_distribution_config(Id=CLOUDFRONT_DIST_ID)
        config = resp['DistributionConfig']
        etag = resp['ETag']
        if config['Enabled']:
            print("   ✅ CloudFront already enabled")
            return
        config['Enabled'] = True
        cf.update_distribution(
            DistributionConfig=config,
            Id=CLOUDFRONT_DIST_ID, IfMatch=etag)
        deployment_state["cloudfront_enabled"] = True
        print("   ✅ CloudFront enabled")
    except Exception as e:
        print(f"   ⚠️  {e}")


def disable_cloudfront():
    cf = boto3.client('cloudfront')
    try:
        resp = cf.get_distribution_config(Id=CLOUDFRONT_DIST_ID)
        config = resp['DistributionConfig']
        etag = resp['ETag']
        if not config['Enabled']:
            print("   ✅ CloudFront already disabled")
            return
        config['Enabled'] = False
        cf.update_distribution(
            DistributionConfig=config,
            Id=CLOUDFRONT_DIST_ID, IfMatch=etag)
        print("   ✅ CloudFront disabled")
    except Exception as e:
        print(f"   ⚠️  {e}")


# ============================================================
# Jenkins Helpers
# ============================================================

def get_jenkins_crumb(jenkins_url):
    try:
        r = requests.get(
            f"{jenkins_url}/crumbIssuer/api/json",
            auth=(JENKINS_USER, JENKINS_API_TOKEN), timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def wait_for_jenkins(jenkins_url, jenkins_ip, timeout=180):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(
                f"{jenkins_url}/login",
                auth=(JENKINS_USER, JENKINS_API_TOKEN), timeout=5)
            if r.status_code in [200, 403]:
                print("   ✅ Jenkins HTTP responding")
                break
        except Exception:
            pass
        print("   ... Jenkins not ready — waiting 10s")
        time.sleep(10)

    ssh_restart_jenkins(jenkins_ip)
    time.sleep(30)

    for _ in range(12):
        try:
            r = requests.get(
                f"{jenkins_url}/login",
                auth=(JENKINS_USER, JENKINS_API_TOKEN), timeout=5)
            if r.status_code in [200, 403]:
                print("   ✅ Jenkins ready")
                return
        except Exception:
            pass
        time.sleep(10)
    print("   ⚠️  Jenkins may still be starting")


def update_jenkins_backend_url(jenkins_url, backend_url):
    """Update REACT_APP_API_URL via Jenkins Script Console (Groovy)"""
    try:
        groovy_script = f"""
import com.cloudbees.plugins.credentials.*
import com.cloudbees.plugins.credentials.domains.*
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl
import hudson.util.Secret

def store = SystemCredentialsProvider.getInstance().getStore()
def creds = SystemCredentialsProvider.getInstance().getCredentials()
def c = creds.find {{ it.id == "REACT_APP_API_URL" }}

if (c == null) {{
    println("ERROR: Credential REACT_APP_API_URL not found")
    return
}}

def newCred = new StringCredentialsImpl(
    c.scope,
    c.id,
    c.description,
    Secret.fromString("{backend_url}")
)

store.updateCredentials(Domain.global(), c, newCred)
println("SUCCESS: REACT_APP_API_URL updated to {backend_url}")
"""

        crumb = get_jenkins_crumb(jenkins_url)
        headers = {}
        if crumb:
            headers[crumb['crumbRequestField']] = crumb['crumb']

        r = requests.post(
            f"{jenkins_url}/scriptText",
            auth=(JENKINS_USER, JENKINS_API_TOKEN),
            headers=headers,
            data={"script": groovy_script},
            timeout=15
        )

        if r.status_code == 200:
            output = r.text.strip()
            print(f"   📄 Script output: {output}")
            if "SUCCESS" in output:
                return f"✅ REACT_APP_API_URL updated → {backend_url}"
            elif "ERROR" in output:
                return f"⚠️  Script error: {output}"
            else:
                return f"⚠️  Unexpected output: {output}"
        else:
            return f"⚠️  Script Console: {r.status_code} — {r.text[:200]}"

    except Exception as e:
        return f"⚠️  Error: {e}"


def fetch_build_logs(jenkins_url, build_number):
    try:
        r = requests.get(
            f"{jenkins_url}/job/{JENKINS_JOB_NAME}"
            f"/{build_number}/consoleText",
            auth=(JENKINS_USER, JENKINS_API_TOKEN), timeout=10)
        if r.status_code == 200:
            return '\n'.join(r.text.strip().split('\n')[-50:])
    except Exception as e:
        return f"Log error: {e}"
    return "Could not fetch logs"


def monitor_jenkins_build(jenkins_url, timeout=300):
    print("\n📊 Monitoring build...")
    job_url = f"{jenkins_url}/job/{JENKINS_JOB_NAME}"
    build_number = None

    for _ in range(10):
        try:
            r = requests.get(
                f"{job_url}/api/json",
                auth=(JENKINS_USER, JENKINS_API_TOKEN), timeout=5)
            build_number = r.json().get('lastBuild', {}).get('number')
            if build_number:
                deployment_state["build_number"] = build_number
                break
        except Exception:
            pass
        time.sleep(3)

    if not build_number:
        return "❌ Could not find build number"

    print(f"   📌 Build #{build_number} in progress...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(
                f"{job_url}/{build_number}/api/json",
                auth=(JENKINS_USER, JENKINS_API_TOKEN), timeout=5)
            data = r.json()
            if not data.get('building', True):
                result = data.get('result')
                deployment_state["build_number"] = None
                if result == 'SUCCESS':
                    return (
                        f"\n✅ Build #{build_number} PASSED!\n"
                        f"   Frontend deployed to S3 + "
                        f"CloudFront cache invalidated.\n\n"
                        f"   🌐 Live URL : {CLOUDFRONT_DOMAIN}\n"
                        f"   🔧 Build    : {job_url}/{build_number}\n"
                    )
                else:
                    logs = fetch_build_logs(jenkins_url, build_number)
                    return (
                        f"\n❌ Build #{build_number} FAILED "
                        f"({result})\n\n"
                        f"--- Last 50 lines ---\n{logs}"
                    )
            print(f"   ... Build #{build_number} running — waiting 10s")
        except Exception as e:
            print(f"   ⚠️  Poll error: {e}")
        time.sleep(10)
    return f"⏰ Timed out after {timeout}s — check Jenkins manually"


# ============================================================
# Deploy Backend
# ============================================================

def deploy_backend():
    print("\n📋 Here's what I'll do for backend:\n")
    print("   1. Start RDS instance (awslearn-db)")
    print("   2. Wait for RDS to be available")
    print("   3. Start 3-tier-Backend EC2 (i-001974cf5de1f89f3)")
    print("   4. SSH in → restart Docker + Nginx")
    print("   5. Verify Docker containers running")
    print("   6. Return backend public IP\n")
    print("   ⚠️  Press Ctrl+C anytime to cancel and rollback.\n")

    if input("Proceed? (yes/no): ").strip().lower() != 'yes':
        print("❌ Deploy cancelled.")
        return None

    start_rds()

    print("\n⚙️  Starting Backend EC2...")
    ip = start_ec2(BACKEND_EC2_ID, "3-tier-Backend")
    if not ip:
        print("❌ Backend EC2 did not start.")
        return None
    deployment_state["backend_started"] = True
    deployment_state["backend_ip"] = ip

    ssh_restart_backend(ip)

    print(f"\n✅ Backend ready at: https://{ip}")
    return ip


# ============================================================
# Deploy Frontend
# ============================================================

def deploy_frontend(backend_ip=None, jenkins_url=None):
    backend_url = f"https://{backend_ip}" if backend_ip else None

    print("\n📋 Here's what I'll do for frontend:\n")
    print("   1. Start Jenkins EC2 (i-035fc3e44cf280710)")
    print("   2. Enable CloudFront distribution")
    print("   3. SSH into Jenkins → memory fix + restart")
    if backend_url:
        print(f"   4. Update REACT_APP_API_URL → {backend_url}")
    else:
        print("   4. Ask you for backend URL (or keep existing)")
    print("   5. Trigger Jenkins job: 3rd-Tier-Frontend")
    print("   6. Monitor build live")
    print(f"   7. Print live URL: {CLOUDFRONT_DOMAIN}\n")
    print("   ⚠️  Press Ctrl+C anytime to cancel and rollback.\n")

    if input("Proceed? (yes/no): ").strip().lower() != 'yes':
        print("❌ Deploy cancelled.")
        return

    branch = input(
        "Branch to deploy? (default: main): "
    ).strip() or "main"
    print(f"   ✅ Branch: {branch}")

    if not backend_url:
        manual = input(
            "Backend URL? (Enter to keep existing): "
        ).strip()
        backend_url = manual or None

    print()

    print("⚙️  Starting Jenkins EC2...")
    jenkins_ip = start_ec2(JENKINS_EC2_ID, "Jenkins")
    if not jenkins_ip:
        print("❌ Jenkins EC2 did not start.")
        return
    deployment_state["jenkins_started"] = True
    jenkins_url = f"http://{jenkins_ip}:8080"
    deployment_state["jenkins_url"] = jenkins_url

    print("\n🌐 Enabling CloudFront...")
    enable_cloudfront()

    print("\n🔧 Waiting for Jenkins...")
    wait_for_jenkins(jenkins_url, jenkins_ip)

    if backend_url:
        print(f"\n🔧 Updating REACT_APP_API_URL → {backend_url}")
        result = update_jenkins_backend_url(jenkins_url, backend_url)
        print(f"   {result}")

    print(f"\n🚀 Triggering: {JENKINS_JOB_NAME} [{branch}]")
    crumb = get_jenkins_crumb(jenkins_url)
    headers = {}
    if crumb:
        headers[crumb['crumbRequestField']] = crumb['crumb']
    try:
        r = requests.post(
            f"{jenkins_url}/job/{JENKINS_JOB_NAME}/build",
            auth=(JENKINS_USER, JENKINS_API_TOKEN),
            headers=headers, timeout=10)
        if r.status_code in [200, 201]:
            print("   ✅ Build triggered")
        else:
            print(f"   ❌ Trigger failed: {r.status_code}")
            return
    except Exception as e:
        print(f"   ❌ {e}")
        return

    time.sleep(3)
    print(monitor_jenkins_build(jenkins_url))


# ============================================================
# Stop Commands
# ============================================================

def stop_frontend():
    print("\n🛑 Stopping frontend...\n")
    disable_cloudfront()
    print(f"\n✅ CloudFront disabled.")
    print("   Jenkins EC2 still running — serves other projects.")


def stop_backend():
    print("\n🛑 Stopping backend...\n")
    stop_ec2(BACKEND_EC2_ID, "3-tier-Backend")
    stop_rds()
    print("\n✅ Backend EC2 + RDS stopped.")


def stop_all():
    print("\n🛑 Stopping everything...\n")
    disable_cloudfront()
    stop_ec2(JENKINS_EC2_ID, "Jenkins")
    stop_ec2(BACKEND_EC2_ID, "3-tier-Backend")
    stop_rds()
    print("\n✅ Everything stopped.")


# ============================================================
# READ Actions
# ============================================================

def run_aws_query(service, action, params=None):
    try:
        c = boto3.client(service, region_name=AWS_REGION)
        resp = getattr(c, action)(**(params or {}))
        resp.pop('ResponseMetadata', None)
        return json.dumps(resp, default=str, indent=2)
    except Exception as e:
        return f"Error: {e}"


def get_cloudwatch_metric(instance_id, metric_name, hours=1):
    cw = boto3.client('cloudwatch', region_name=AWS_REGION)
    resp = cw.get_metric_statistics(
        Namespace='AWS/EC2', MetricName=metric_name,
        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
        StartTime=datetime.utcnow() - timedelta(hours=hours),
        EndTime=datetime.utcnow(), Period=300, Statistics=['Average'])
    dps = sorted(resp['Datapoints'], key=lambda x: x['Timestamp'])
    if not dps:
        return (f"No data for {metric_name} on "
                f"{instance_id} in last {hours}h.")
    return "\n".join([
        f"{d['Timestamp'].strftime('%H:%M')} → "
        f"{round(d['Average'], 2)}%"
        for d in dps])


def get_cloudwatch_alarms():
    cw = boto3.client('cloudwatch', region_name=AWS_REGION)
    alarms = cw.describe_alarms().get('MetricAlarms', [])
    if not alarms:
        return "No CloudWatch alarms found."
    return "\n".join([
        f"{a['AlarmName']} | {a['StateValue']} | "
        f"{a['MetricName']} | threshold: {a['Threshold']}"
        for a in alarms])


def confirm_and_execute(action):
    intent = action.get('intent')
    params = action.get('params', {})
    msgs = {
        'start_ec2':
            f"⚠️  START EC2: {params.get('instance_id')}",
        'stop_ec2':
            f"⚠️  STOP EC2: {params.get('instance_id')}",
        'invalidate_cf':
            f"⚠️  INVALIDATE CloudFront: {CLOUDFRONT_DIST_ID}",
        'create_s3':
            f"⚠️  CREATE S3 bucket: '{params.get('bucket_name')}'",
    }
    print(f"\n{msgs.get(intent, 'Unknown')}")
    if input("Are you sure? (yes/no): ").strip().lower() != 'yes':
        return "❌ Cancelled."
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    if intent == 'start_ec2':
        ec2.start_instances(InstanceIds=[params['instance_id']])
        return f"✅ {params['instance_id']} STARTING."
    elif intent == 'stop_ec2':
        ec2.stop_instances(InstanceIds=[params['instance_id']])
        return f"✅ {params['instance_id']} STOPPING."
    elif intent == 'invalidate_cf':
        boto3.client('cloudfront').create_invalidation(
            DistributionId=CLOUDFRONT_DIST_ID,
            InvalidationBatch={
                'Paths': {'Quantity': 1, 'Items': ['/*']},
                'CallerReference': str(datetime.utcnow().timestamp())
            })
        return "✅ CloudFront cache invalidated."
    elif intent == 'create_s3':
        boto3.client('s3', region_name=AWS_REGION).create_bucket(
            Bucket=params['bucket_name'],
            CreateBucketConfiguration={'LocationConstraint': AWS_REGION})
        return f"✅ S3 bucket '{params['bucket_name']}' created."
    return "❌ Unknown intent."


# ============================================================
# AI Agent
# ============================================================

def ask_agent(user_command):
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """You are a smart DevOps assistant managing AWS infrastructure.

For AWS actions respond ONLY with JSON. No markdown. No explanation.

READ:
{"type":"read","service":"s3","action":"list_buckets","params":{}}
{"type":"ec2_names"}
{"type":"read","service":"ec2","action":"describe_instances","params":{}}
{"type":"read","service":"cloudfront","action":"list_distributions","params":{}}
{"type":"read","service":"lambda","action":"list_functions","params":{}}
{"type":"read","service":"rds","action":"describe_db_instances","params":{}}
{"type":"read","service":"iam","action":"list_users","params":{}}
{"type":"read","service":"sns","action":"list_topics","params":{}}
{"type":"read","service":"sqs","action":"list_queues","params":{}}
{"type":"read","service":"ecs","action":"list_clusters","params":{}}
{"type":"read","service":"glue","action":"get_jobs","params":{}}

CLOUDWATCH:
{"type":"cloudwatch","action":"get_alarms"}
{"type":"cloudwatch","action":"get_metric","metric":"CPUUtilization","instance_id":"<id>","hours":1}

WRITE:
{"type":"write","intent":"start_ec2","params":{"instance_id":"<id>"}}
{"type":"write","intent":"stop_ec2","params":{"instance_id":"<id>"}}
{"type":"write","intent":"invalidate_cf","params":{}}
{"type":"write","intent":"create_s3","params":{"bucket_name":"<name>"}}

DEPLOY:
{"type":"deploy","target":"frontend"}
{"type":"deploy","target":"backend"}
{"type":"deploy","target":"all"}

STOP:
{"type":"stop","target":"frontend"}
{"type":"stop","target":"backend"}
{"type":"stop","target":"all"}

MENU:
{"type":"menu"}

For ANY general question about DevOps, AWS, cloud, Linux, Docker,
Kubernetes, Terraform, CI/CD, networking, security or any technology
topic — answer naturally and helpfully like a senior DevOps engineer.
Use {"type":"general","answer":"your detailed answer here"}
Never refuse general questions. Always answer them."""
            },
            {"role": "user", "content": user_command}
        ]
    )
    return resp.choices[0].message.content


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    startup_check()

    jenkins_url = None

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() == 'exit':
            print("Goodbye! 👋")
            break

        if user_input.lower() in ['status', 'menu', 'refresh']:
            fetch_infra_status()
            show_menu()
            continue

        raw = ask_agent(user_input).strip()

        try:
            action = json.loads(raw)
            atype = action.get('type')

            if atype == 'menu':
                fetch_infra_status()
                show_menu()

            elif atype == 'read':
                print(f"\nQuerying {action['service'].upper()} "
                      f"→ {action['action']}...\n")
                print(run_aws_query(
                    action['service'],
                    action['action'],
                    action.get('params', {})))

            elif atype == 'ec2_names':
                print("\nFetching EC2 instances...\n")
                ec2 = boto3.client('ec2', region_name=AWS_REGION)
                for r in ec2.describe_instances()['Reservations']:
                    for i in r['Instances']:
                        name = next(
                            (t['Value'] for t in i.get('Tags', [])
                             if t['Key'] == 'Name'), 'Unnamed')
                        state = i['State']['Name']
                        icon = "🟢" if state == 'running' else "🔴"
                        print(f"   {icon} {name.strip()} | "
                              f"{i['InstanceId']} | {state}")

            elif atype == 'cloudwatch':
                if action.get('action') == 'get_alarms':
                    print("\nFetching alarms...\n")
                    print(get_cloudwatch_alarms())
                elif action.get('action') == 'get_metric':
                    iid = action.get('instance_id', '')
                    if not iid or '<' in iid:
                        iid = input(
                            "\nEnter EC2 Instance ID: ").strip()
                    print(f"\nFetching {action['metric']} "
                          f"for {iid}...\n")
                    print(get_cloudwatch_metric(
                        iid, action['metric'],
                        action.get('hours', 1)))

            elif atype == 'write':
                print(confirm_and_execute(action))

            elif atype == 'deploy':
                target = action.get('target')
                if target == 'backend':
                    deploy_backend()
                elif target == 'frontend':
                    deploy_frontend(jenkins_url=jenkins_url)
                elif target == 'all':
                    print(
                        "\n🚀 Deploying backend first, "
                        "then frontend...\n")
                    backend_ip = deploy_backend()
                    if backend_ip:
                        print(
                            "\n✅ Backend done. "
                            "Starting frontend...\n")
                        deploy_frontend(
                            backend_ip=backend_ip,
                            jenkins_url=jenkins_url)
                    else:
                        print("⚠️  Backend failed — skipping frontend")

            elif atype == 'stop':
                target = action.get('target')
                if target == 'frontend':
                    stop_frontend()
                elif target == 'backend':
                    stop_backend()
                elif target == 'all':
                    stop_all()

            elif atype == 'general':
                print(f"\n🤖 {action.get('answer')}\n")

            else:
                print(f"\n🤖 {raw}\n")

        except json.JSONDecodeError:
            print(f"\n🤖 {raw}\n")

        print()