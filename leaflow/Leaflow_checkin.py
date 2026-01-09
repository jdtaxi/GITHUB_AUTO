#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import base64
import re
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"
CHECKIN_URL = "https://checkin.leaflow.net"

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
REPO_TOKEN = os.getenv("REPO_TOKEN")
REPO = os.getenv("GITHUB_REPOSITORY")
ACCOUNTS=os.environ.get("LEAFLOW_ACCOUNTS")
# ================= GitHub SecretUpdater =================

class SecretUpdater:
    def update(self, value):
        if not (REPO_TOKEN and REPO):
            return False
        try:
            from nacl import encoding, public

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

            key = r.json()
            pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
            encrypted = public.SealedBox(pk).encrypt(value.encode())

            r = requests.put(
                f"https://api.github.com/repos/{REPO}/actions/secrets/LEAFLOW_ACCOUNTS",
                headers=headers,
                json={
                    "encrypted_value": base64.b64encode(encrypted).decode(),
                    "key_id": key["key_id"]
                },
                timeout=30
            )
            return r.status_code in (201, 204)
        except:
            return False

# ================= Telegram =================

def tg_msg(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=20
    )

def tg_photo(path, caption):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
            data={"chat_id": TG_CHAT_ID, "caption": caption[:1024]},
            files={"photo": f},
            timeout=30
        )

# ================= Playwright =================

def open_browser():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = browser.new_context()
    page = ctx.new_page()
    return pw, browser, ctx, page

def cookies_ok(page):
    page.goto(DASHBOARD_URL, timeout=30000)
    page.wait_for_timeout(2000)
    return "login" not in page.url.lower()

def login(page, email, password, idx):
    page.goto(LOGIN_URL, timeout=30000)
    page.fill("input[type=email]", email)
    page.fill("input[type=password]", password)

    try:
        cb = page.locator("input[type=checkbox]").first
        if cb.is_visible() and not cb.is_checked():
            cb.check()
    except:
        pass

    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle", timeout=30000)

    if "login" in page.url.lower():
        img = f"login_fail_{idx}.png"
        page.screenshot(path=img, full_page=True)
        tg_photo(
            img,
            f"❌ <b>Leaflow 登录失败</b>\n👤 {email}\n🕒 {datetime.now():%F %T}"
        )
        raise RuntimeError("login failed")

# ================= API Checkin =================

def api_checkin(cookies):
    s = requests.Session()
    for c in cookies:
        if "leaflow" in c["domain"]:
            s.cookies.set(c["name"], c["value"])

    r = s.get(CHECKIN_URL, timeout=30)
    if "已签到" in r.text:
        return True, "今日已签到"

    token = None
    m = re.search(r'name="_token".*?value="([^"]+)"', r.text)
    if m:
        token = m.group(1)

    data = {"checkin": "1"}
    if token:
        data["_token"] = token

    r = s.post(CHECKIN_URL, data=data, timeout=30)
    if any(x in r.text for x in ["成功", "签到", "完成"]):
        return True, "签到成功"

    return False, "签到失败"
    

# ================= 单账号流程 =================

def process(idx, email, password, cookie_str, updater):
    pw, browser, ctx, page = open_browser()

    try:
        note = ""
        if cookie_str:
            try:
                ctx.add_cookies(json.loads(cookie_str))
                if cookies_ok(page):
                    note = "🍪 cookies复用"
                else:
                    raise Exception
            except:
                login(page, email, password, idx)
                note = "♻ cookies失效重登"
        else:
            login(page, email, password, idx)
            note = "🔐 首次登录"

        cookies = ctx.cookies()
        ACCOUNTS[email][1] = json.dumps(cookies)

        ok, msg = api_checkin(cookies)
        return ok, f"{note} | {msg}"

    finally:
        browser.close()
        pw.stop()

# ================= Main =================

def main():
    updater = SecretUpdater()
    results = []


    for idx, (email, data) in enumerate(ACCOUNTS.items(), 1):
        password, cookie = data
        try:
            ok, msg = process(idx, email, password, cookie, updater)
            results.append((email, ok, msg))
        except Exception as e:
            results.append((email, False, str(e)))

    updater.update(json.dumps(ACCOUNTS))

    text = "🍃 <b>Leaflow 多账号签到汇总</b>\n\n"
    for email, ok, msg in results:
        text += f"{'✅' if ok else '❌'} {email[:3]}***{email[email.find('@'):]}：{msg}\n"
    text += f"\n🕒 {datetime.now():%F %T}"

    tg_msg(text)

    if not all(x[1] for x in results):
        exit(1)

if __name__ == "__main__":
    main()
