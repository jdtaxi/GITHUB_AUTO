import os
import json
import requests

BASE_URL = "https://incudal.com"
TIMEOUT = 15

def build_session():
    data = json.loads(os.environ["USER_SESSION"])
    s = requests.Session()
    s.headers.update({
        "authorization": data["auth_token"],
        "user-agent": "Mozilla/5.0",
        "accept": "application/json"
    })
    for c in data["cookies"]:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain"))
    return s

def safe_json(r):
    try:
        return r.json()
    except:
        return {}

def decode(code_type, value):
    return {
        "cpu": "CPU",
        "memory": "内存",
        "disk": "硬盘",
        "traffic": "流量"
    }.get(code_type, code_type) + f" +{value}"

def get_instances(session):
    r = session.get(f"{BASE_URL}/api/instances", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("instances", [])

def redeem(session, code, instance_id):
    print(f"🚀 开始兑换实例 {instance_id}，兑换码 {code}")
    r = session.post(
        f"{BASE_URL}/api/checkin/redeem",
        json={"redeemCode": code, "instanceId": instance_id},
        timeout=TIMEOUT
    )
    data = safe_json(r)
    code_data = data.get("todayCode") if isinstance(data.get("todayCode"), dict) else data

    if r.status_code == 200 and code_data and "codeType" in code_data:
        result = f"✅ {instance_id}: {decode(code_data['codeType'], code_data['codeValue'])}"
        print(result)
        return result
    result = f"❌ {instance_id}: 失败"
    print(result)
    return result

def main():
    session = build_session()
    codes = [x.strip() for x in os.environ["REDEEM_TEXT"].splitlines() if x.strip()]
    instances = get_instances(session)

    lines = []
    for code in codes:
        print(f"🎟 兑换码 {code} 开始")
        lines.append(f"🎟 兑换码 {code}")
        for ins in instances:
            line = redeem(session, code, ins["id"])
            lines.append("  " + line)

    # 确保 result.txt 在当前工作目录
    result_file = os.path.join(os.getcwd(), "result.txt")
    with open(result_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("✅ 全部兑换完成")
