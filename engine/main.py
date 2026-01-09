
# -*- coding: utf-8 -*-

import re
import requests

# session_factory
def session_from_cookies(cookies: dict, headers=None):
    session = requests.Session()
    for k, v in cookies.items():
        session.cookies.set(k, v)

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
    })

    if headers:
        session.headers.update(headers)

    print("🧩 Session 已从 Cookie 构建完成")
    return session

# leaflow_checkin_engine
def perform_checkin(session, account_name, checkin_url, main_site, printer=print):
    """执行签到（依赖函数入口）"""
    printer(f"\n🎯 [{account_name}] 开始签到流程")

    try:
        # 1️⃣ 直接访问签到页
        printer(f"➡️ GET {checkin_url}")
        resp = session.get(checkin_url, timeout=30)
        printer(f"⬅️ HTTP {resp.status_code}")

        if resp.status_code == 200:
            ok, msg = analyze_and_checkin(
                session, resp.text, checkin_url, account_name, printer
            )
            if ok:
                return True, msg

        # 2️⃣ API fallback
        api_endpoints = [
            f"{checkin_url}/api/checkin",
            f"{checkin_url}/checkin",
            f"{main_site}/api/checkin",
            f"{main_site}/checkin",
        ]

        for ep in api_endpoints:
            printer(f"➡️ 尝试接口 {ep}")

            try:
                r = session.get(ep, timeout=30)
                printer(f"GET {r.status_code}")
                if r.status_code == 200:
                    ok, msg = check_checkin_response(r.text)
                    if ok:
                        return True, msg
            except Exception as e:
                printer(f"⚠ GET 失败: {e}")

            try:
                r = session.post(ep, data={"checkin": "1"}, timeout=30)
                printer(f"POST {r.status_code}")
                if r.status_code == 200:
                    ok, msg = check_checkin_response(r.text)
                    if ok:
                        return True, msg
            except Exception as e:
                printer(f"⚠ POST 失败: {e}")

        return False, "所有签到方式均失败"

    except Exception as e:
        return False, f"签到异常: {e}"


def analyze_and_checkin(session, html, page_url, account_name, printer):
    """分析页面并执行签到"""
    printer(f"🔍 [{account_name}] 分析签到页面")

    if already_checked_in(html):
        printer("✅ 已签到")
        return True, "今日已签到"

    if not is_checkin_page(html):
        printer("❌ 不是签到页面")
        return False, "非签到页面"

    data = {
        "checkin": "1",
        "action": "checkin",
        "daily": "1",
    }

    token = extract_csrf_token(html)
    if token:
        printer(f"🔐 提取 CSRF Token: {token[:8]}***")
        data["_token"] = token
        data["csrf_token"] = token
    else:
        printer("⚠ 未检测到 CSRF Token")

    printer(f"📤 POST {page_url}")
    r = session.post(page_url, data=data, timeout=30)
    printer(f"⬅️ HTTP {r.status_code}")

    if r.status_code == 200:
        return check_checkin_response(r.text)

    return False, "POST 签到失败"


def already_checked_in(html):
    content = html.lower()
    keys = [
        "already checked in", "今日已签到",
        "checked in today", "已完成签到",
        "attendance recorded"
    ]
    return any(k in content for k in keys)


def is_checkin_page(html):
    content = html.lower()
    keys = ["check-in", "checkin", "签到", "attendance", "daily"]
    return any(k in content for k in keys)


def extract_csrf_token(html):
    patterns = [
        r'name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']',
        r'<meta[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def check_checkin_response(html):
    content = html.lower()
    success_words = [
        "check-in successful", "签到成功",
        "attendance recorded", "earned reward",
        "success", "成功", "completed"
    ]

    if any(w in content for w in success_words):
        patterns = [
            r"获得奖励[^\d]*(\d+\.?\d*)",
            r"earned.*?(\d+\.?\d*)",
            r"(\d+\.?\d*)\s*(credits?|points?|元)",
        ]
        for p in patterns:
            m = re.search(p, html, re.IGNORECASE)
            if m:
                return True, f"签到成功，获得 {m.group(1)}"
        return True, "签到成功"

    return False, "签到返回失败"
