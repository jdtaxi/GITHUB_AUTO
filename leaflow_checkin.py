#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Leaflow Playwright 登录 + API 签到
- cookies 存储到 GitHub Actions Secrets
- cookies 失效自动刷新
"""

import os
import json
import time
import base64
import re
import requests
from playwright.sync_api import sync_playwright

# ================= 基础配置 =================

LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"
CHECKIN_URL = "https://checkin.leaflow.net"

EMAIL = os.getenv("LEAFLOW_EMAIL")
PASSWORD = os.getenv("LEAFLOW_PASSWORD")
SECRET_COOKIES = os.getenv("LEAFLOW_COOKIES", "").strip()

# ================= GitHub Secret 更新器 =================

class SecretUpdater:
    def __init__(self):
        self.token = os.environ.get("REPO_TOKEN")
        self.repo = os.environ.get("GITHUB_REPOSITORY")
        self.ok = bool(self.token and self.repo)

    def update(self, name, value):
        if not self.ok:
            print("⚠️ 未配置 REPO_TOKEN，无法自动更新 Secret")
            return False

        try:
            from nacl import encoding, public

            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }

            r = requests.get(
                f"https://api.github.com/repos/{self.repo}/actions/secrets/public-key",
                headers=headers, timeout=30
            )
            if r.status_code != 200:
                return False

            key = r.json()
            pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
            encrypted = public.SealedBox(pk).encrypt(value.encode())

            r = requests.put(
                f"https://api.github.com/repos/{self.repo}/actions/secrets/{name}",
                headers=headers,
                json={
                    "encrypted_value": base64.b64encode(encrypted).decode(),
                    "key_id": key["key_id"]
                },
                timeout=30
            )
            return r.status_code in (201, 204)

        except Exception as e:
            print("❌ 更新 Secret 失败:", e)
            return False

# ================= Playwright 登录 =================

def launch_browser():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context()
    page = context.new_page()
    return pw, browser, context, page


def load_cookies_from_secret(context):
    if not SECRET_COOKIES:
        return False

    try:
        cookies = json.loads(SECRET_COOKIES)
        context.add_cookies(cookies)
        print("🍪 已从 Secret 加载 cookies")
        return True
    except Exception:
        return False


def cookies_valid(page):
    page.goto(DASHBOARD_URL, timeout=30000)
    time.sleep(3)
    return "login" not in page.url.lower()


def login_leaflow(page):
    print("🔐 使用账号密码登录")
    page.goto(LOGIN_URL, timeout=30000)
    page.wait_for_timeout(3000)

    page.fill("input[type=email]", EMAIL)
    page.fill("input[type=password]", PASSWORD)

    # 记住我
    try:
        cb = page.locator("input[type=checkbox]").first
        if cb.is_visible() and not cb.is_checked():
            cb.check()
    except:
        pass

    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle", timeout=30000)

    if "login" in page.url.lower():
        raise RuntimeError("登录失败")

    print("✅ 登录成功")


def save_cookies_to_secret(context):
    cookies = context.cookies()
    value = json.dumps(cookies)

    updater = SecretUpdater()
    if updater.update("LEAFLOW_COOKIES", value):
        print("✅ cookies 已更新到 GitHub Secrets")
    else:
        print("⚠️ cookies 更新失败")


def ensure_login_and_get_cookies():
    pw, browser, context, page = launch_browser()
    try:
        if load_cookies_from_secret(context) and cookies_valid(page):
            print("✅ cookies 登录有效")
        else:
            print("♻ cookies 无效，重新登录")
            login_leaflow(page)
            save_cookies_to_secret(context)

        return {
            "cookies": {
                c["name"]: c["value"]
                for c in context.cookies()
                if "leaflow" in c.get("domain", "")
            }
        }
    finally:
        browser.close()
        pw.stop()

# ================= API 签到 =================

class LeaflowCheckinAPI:

    def __init__(self):
        self.session = requests.Session()

    def load_cookies(self, cookies):
        for k, v in cookies.items():
            self.session.cookies.set(k, v)

    def run(self, cookies):
        self.load_cookies(cookies)

        r = self.session.get(CHECKIN_URL, timeout=30)
        if r.status_code != 200:
            return False, "签到页访问失败"

        if "已签到" in r.text or "already" in r.text.lower():
            return True, "今日已签到"

        token = None
        m = re.search(r'name="_token".*?value="([^"]+)"', r.text)
        if m:
            token = m.group(1)

        data = {"checkin": "1"}
        if token:
            data["_token"] = token

        r = self.session.post(CHECKIN_URL, data=data, timeout=30)
        if "成功" in r.text or "success" in r.text.lower():
            return True, "签到成功"

        return False, "签到失败"

# ================= 主入口 =================

def main():
    if not EMAIL or not PASSWORD:
        raise RuntimeError("缺少 LEAFLOW_EMAIL / LEAFLOW_PASSWORD")

    cookie_data = ensure_login_and_get_cookies()
    api = LeaflowCheckinAPI()
    ok, msg = api.run(cookie_data["cookies"])

    print("🎯 签到结果:", msg)
    if not ok:
        exit(1)


if __name__ == "__main__":
    main()
