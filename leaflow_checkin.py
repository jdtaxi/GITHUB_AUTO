#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Leaflow Playwright + API 自动签到（最终稳定版）

功能：
- Playwright 登录（勾选记住我）
- cookies 缓存 & 复用
- cookies → requests API 签到
- cookies 失效自动刷新
- 无 Selenium / 无前端点击签到
"""

import os
import json
import time
import re
import logging
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ================= 基础配置 =================

LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"
CHECKIN_URL = "https://checkin.leaflow.net"
COOKIE_CACHE = "/tmp/leaflow_cookies.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("leaflow")

# ================= Playwright =================

def launch_browser():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    context = browser.new_context()
    page = context.new_page()
    return pw, browser, context, page


def save_cookies(context):
    cookies = context.cookies()
    with open(COOKIE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cookies, f)
    logger.info("🍪 Cookies 已保存")


def load_cookies(context):
    if not os.path.exists(COOKIE_CACHE):
        return False

    with open(COOKIE_CACHE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    context.add_cookies(cookies)
    logger.info("🍪 已加载本地 Cookies")
    return True


def cookies_valid(page):
    page.goto(DASHBOARD_URL, timeout=30000)
    time.sleep(3)
    return "login" not in page.url


def login_leaflow(page, email, password):
    logger.info("🔐 使用账号密码登录")
    page.goto(LOGIN_URL, timeout=30000)
    page.wait_for_timeout(3000)

    page.fill("input[type='email'], input[name='email']", email)
    page.fill("input[type='password']", password)

    # 勾选 Remember Me
    try:
        checkbox = page.locator("input[type='checkbox']")
        if checkbox.count() > 0 and not checkbox.first.is_checked():
            checkbox.first.check()
            logger.info("☑ 已勾选记住我")
    except Exception:
        pass

    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle", timeout=30000)

    if "login" in page.url:
        raise RuntimeError("❌ 登录失败")

    logger.info("✅ 登录成功")


def get_api_cookie_data(context, account="leaflow"):
    cookies = context.cookies()
    return {
        "account": account,
        "cookies": {
            c["name"]: c["value"]
            for c in cookies
            if "leaflow" in c.get("domain", "")
        }
    }


def ensure_login_and_get_cookies(email, password):
    pw, browser, context, page = launch_browser()
    try:
        if load_cookies(context) and cookies_valid(page):
            logger.info("✅ Cookies 登录有效")
        else:
            logger.info("♻ Cookies 失效，重新登录")
            login_leaflow(page, email, password)
            save_cookies(context)

        return get_api_cookie_data(context)

    finally:
        browser.close()
        pw.stop()

# ================= API 签到 =================

class LeaflowAPICheckin:

    def __init__(self):
        self.session = requests.Session()

    def load_cookies(self, cookie_data):
        for k, v in cookie_data["cookies"].items():
            self.session.cookies.set(k, v)

    def already_checked_in(self, text):
        indicators = ["已签到", "already checked", "completed"]
        return any(i in text.lower() for i in indicators)

    def check_success(self, text):
        patterns = [
            r"获得[^\d]*(\d+\.?\d*)",
            r"earned[^\d]*(\d+\.?\d*)"
        ]
        for p in patterns:
            m = re.search(p, text, re.I)
            if m:
                return True, f"获得 {m.group(1)} 奖励"
        return "成功" in text or "success" in text.lower(), "签到成功"

    def run(self, cookie_data):
        self.load_cookies(cookie_data)

        r = self.session.get(CHECKIN_URL, timeout=30)
        if r.status_code != 200:
            return False, "无法访问签到页面"

        if self.already_checked_in(r.text):
            return True, "今日已签到"

        csrf = None
        m = re.search(r'name="_token".*?value="([^"]+)"', r.text)
        if m:
            csrf = m.group(1)

        payload = {"checkin": "1"}
        if csrf:
            payload["_token"] = csrf

        r = self.session.post(CHECKIN_URL, data=payload, timeout=30)
        return self.check_success(r.text)

# ================= 主入口 =================

def main():
    email = os.getenv("LEAFLOW_EMAIL")
    password = os.getenv("LEAFLOW_PASSWORD")

    if not email or not password:
        raise RuntimeError("未设置 LEAFLOW_EMAIL / LEAFLOW_PASSWORD")

    cookie_data = ensure_login_and_get_cookies(email, password)

    checkin = LeaflowAPICheckin()
    success, message = checkin.run(cookie_data)

    logger.info(f"🎁 签到结果：{message}")
    if not success:
        exit(1)


if __name__ == "__main__":
    main()

