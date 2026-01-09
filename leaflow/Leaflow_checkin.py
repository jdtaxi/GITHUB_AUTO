#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import base64
import requests
from playwright.sync_api import sync_playwright

# ==================== 基础配置 ====================

LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"
CHECKIN_API = "https://leaflow.net/api/checkin"

REPO = os.getenv("GITHUB_REPOSITORY")
REPO_TOKEN = os.getenv("REPO_TOKEN")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# ==================== Telegram ====================

def tg_send(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }, timeout=20)

# ==================== 账号 / Cookie 解析 ====================

def load_accounts():
    raw = os.getenv("LEAFLOW_ACCOUNTS", "").strip()
    if not raw:
        raise RuntimeError("❌ 未设置 LEAFLOW_ACCOUNTS")

    data = {}
    for item in raw.split(","):
        email, pwd = item.split(":", 1)
        data[email.strip()] = pwd.strip()
    return data


def load_cookies():
    raw = os.getenv("LEAFLOW_COOKIES", "").strip()
    cookies = {}

    if not raw:
        return cookies

    for item in raw.split(","):
        if ":" not in item:
            continue
        email, cookie_json = item.split(":", 1)
        try:
            cookies[email.strip()] = json.loads(cookie_json)
        except Exception:
            pass
    return cookies


def dump_cookies(cookies_map):
    parts = []
    for email, cookies in cookies_map.items():
        parts.append(f"{email}:{json.dumps(cookies, separators=(',', ':'))}")
    return ",".join(parts)

# ==================== GitHub Secret 更新 ====================

class SecretUpdater:
    def __init__(self, name):
        self.name = name

    def update(self, value):
        if not (REPO_TOKEN and REPO):
            return False

        headers = {
            "Authorization": f"token {REPO_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        r = requests.get(
            f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
            headers=headers, timeout=30
        )
        if r.status_code != 200:
            return False

        from nacl import public, encoding
        key = r.json()
        pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
        encrypted = public.SealedBox(pk).encrypt(value.encode())

        r = requests.put(
            f"https://api.github.com/repos/{REPO}/actions/secrets/{self.name}",
            headers=headers,
            json={
                "encrypted_value": base64.b64encode(encrypted).decode(),
                "key_id": key["key_id"]
            },
            timeout=30
        )
        return r.status_code in (201, 204)

# ==================== Playwright ====================

def open_browser():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    return pw, browser, ctx, page


def cookies_ok(page):
    page.goto(DASHBOARD_URL, timeout=30000)
    time.sleep(2)
    return "login" not in page.url.lower()


def login(page, email, password):
    page.goto(LOGIN_URL, timeout=30000)
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)

    if "login" in page.url.lower():
        raise RuntimeError("登录失败")

# ==================== API 签到 ====================

def api_checkin(cookies):
    s = requests.Session()
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain"))

    r = s.post(CHECKIN_API, timeout=20)
    if r.status_code != 200:
        return False, "接口异常"

    j = r.json()
    if j.get("success"):
        return True, j.get("message", "签到成功")
    return False, j.get("message", "签到失败")

# ==================== 主流程 ====================

def process_account(email, password, cookies_map):
    pw, browser, ctx, page = open_browser()
    note = ""

    try:
        if email in cookies_map:
            try:
                ctx.add_cookies(cookies_map[email])
                if cookies_ok(page):
                    note = "🍪 cookies复用"
                else:
                    raise Exception
            except:
                login(page, email, password)
                note = "♻ cookies失效重登"
        else:
            login(page, email, password)
            note = "🔐 首次登录"

        new_cookies = ctx.cookies()
        cookies_map[email] = new_cookies

        ok, msg = api_checkin(new_cookies)
        return ok, f"{note} | {msg}"

    finally:
        browser.close()
        pw.stop()


def main():
    accounts = load_accounts()
    cookies_map = load_cookies()

    results = []
    for email, pwd in accounts.items():
        try:
            ok, msg = process_account(email, pwd, cookies_map)
            status = "✅" if ok else "❌"
            results.append(f"{status} {email} — {msg}")
        except Exception as e:
            results.append(f"❌ {email} — {e}")

    SecretUpdater("LEAFLOW_COOKIES").update(
        dump_cookies(cookies_map)
    )

    tg_send("📋 <b>Leaflow 签到汇总</b>\n\n" + "\n".join(results))


if __name__ == "__main__":
    main()
