#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import base64
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ================= 基础配置 =================

LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"
CHECKIN_API = "https://leaflow.net/api/checkin"

REPO = os.getenv("GITHUB_REPOSITORY")
REPO_TOKEN = os.getenv("REPO_TOKEN")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# ================= Telegram =================

def tg_send(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        },
        timeout=20
    )


def tg_send_photo(path, caption=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
            data={
                "chat_id": TG_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML"
            },
            files={"photo": f},
            timeout=30
        )

# ================= 账号 / Cookies =================

def load_accounts():
    raw = os.getenv("LEAFLOW_ACCOUNTS", "").strip()
    if not raw:
        raise RuntimeError("❌ 未设置 LEAFLOW_ACCOUNTS")

    accounts = {}
    for item in raw.split(","):
        email, pwd = item.split(":", 1)
        accounts[email.strip()] = pwd.strip()

    print(f"🔐 读取账号数: {len(accounts)}")
    return accounts


def load_cookies():
    raw = os.getenv("LEAFLOW_COOKIES", "").strip()
    cookies = {}

    if not raw:
        print("🍪 未设置 LEAFLOW_COOKIES")
        return cookies

    for item in raw.split(","):
        if ":" not in item:
            continue
        email, cookie_json = item.split(":", 1)
        try:
            cookies[email.strip()] = json.loads(cookie_json)
        except Exception:
            print(f"⚠ cookies 解析失败: {email}")

    print(f"🍪 已加载 cookies 数: {len(cookies)}")
    return cookies


def dump_cookies(cookies_map):
    return ",".join(
        f"{email}:{json.dumps(cookies, separators=(',', ':'))}"
        for email, cookies in cookies_map.items()
    )

# ================= GitHub Secret 回写 =================

class SecretUpdater:
    def __init__(self, name):
        self.name = name

    def update(self, value):
        if not (REPO and REPO_TOKEN):
            print("⚠ 未设置 REPO_TOKEN，跳过 cookies 回写")
            return

        headers = {
            "Authorization": f"token {REPO_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        r = requests.get(
            f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
            headers=headers,
            timeout=30
        )
        if r.status_code != 200:
            print("❌ 获取 GitHub 公钥失败")
            return

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

        print(f"💾 cookies 回写状态: {r.status_code}")

# ================= Playwright =================

def open_browser():
    print("🌐 启动浏览器")
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    ctx = browser.new_context()
    page = ctx.new_page()
    return pw, browser, ctx, page


def cookies_ok(page):
    print("🔍 校验 cookies 是否有效")
    page.goto(DASHBOARD_URL, timeout=30000)
    time.sleep(2)
    print(f"📍 当前 URL: {page.url}")
    return "login" not in page.url.lower()

# ================= 登录 =================

def login(page, email, password):
    print(f"\n🔐 执行登录: {email}")

    try:
        page.goto(LOGIN_URL, timeout=30000)
        page.wait_for_load_state("domcontentloaded")

        page.wait_for_selector("#account", timeout=30000)
        page.fill("#account", email)
        print("✅ 已输入账号")

        page.wait_for_timeout(1500)
        page.wait_for_selector("#password", timeout=30000)
        page.fill("#password", password)
        print("✅ 已输入密码")

        # 保持登录状态
        try:
            remember = page.locator('button[data-slot="checkbox"]')
            remember.wait_for(state="visible", timeout=5000)
            if remember.get_attribute("aria-checked") != "true":
                remember.click()
                print("☑ 已勾选保持登录状态")
        except Exception:
            print("⚠ 未找到保持登录状态按钮")

        # 登录按钮
        login_btn = page.locator(
            'button[data-slot="button"][type="submit"]',
            has_text="登录"
        )
        login_btn.wait_for(state="visible", timeout=10000)
        login_btn.click()
        print("➡ 已点击登录按钮")

        page.wait_for_load_state("networkidle", timeout=30000)

        if "login" in page.url.lower():
            raise RuntimeError("登录提交后仍在登录页")

        page.goto(DASHBOARD_URL, timeout=30000)
        if "login" in page.url.lower():
            raise RuntimeError("Dashboard 校验失败")

        print("🎉 登录成功")

    except Exception as e:
        print(f"❌ 登录异常: {e}")
        img = f"leaflow_login_fail_{email.replace('@','_')}.png"
        page.screenshot(path=img, full_page=True)

        tg_send_photo(
            img,
            f"❌ <b>Leaflow 登录失败</b>\n"
            f"👤 {email}\n"
            f"🕒 {datetime.now():%F %T}\n"
            f"📍 {page.url}\n"
            f"{e}"
        )
        raise

# ================= API 签到 =================

def api_checkin(cookies):
    print("📡 发送签到请求")
    s = requests.Session()
    for c in cookies:
        s.cookies.set(
            c["name"],
            c["value"],
            domain=c.get("domain"),
            path="/"
        )

    r = s.post(CHECKIN_API, timeout=20)
    print(f"📥 接口返回码: {r.status_code}")

    if r.status_code != 200:
        return False, "接口异常"

    j = r.json()
    return j.get("success", False), j.get("message", "未知返回")

# ================= 单账号流程（最终修正版） =================

def process_account(email, password, cookies_map):
    print("=" * 60)
    print(f"👤 开始处理账号: {email}")

    pw, browser, ctx, page = open_browser()
    note = ""

    try:
        try:
            if email in cookies_map:
                print("🍪 尝试复用 cookies")
                ctx.add_cookies(cookies_map[email])

                if cookies_ok(page):
                    print("✅ cookies 有效")
                    note = "cookies复用"
                else:
                    print("♻ cookies 失效")
                    raise Exception
            else:
                print("🆕 未发现 cookies")
                raise Exception

            print("🔄 同步浏览器 cookies")
            cookies_map[email] = ctx.cookies()

        except Exception:
            print("🔐 进入登录流程")
            login(page, email, password)

            print("🔄 登录后同步 cookies")
            cookies_map[email] = ctx.cookies()
            note = "重新登录"

        print("📡 开始执行签到")
        ok, msg = api_checkin(cookies_map[email])
        print(f"📊 签到结果: {ok} | {msg}")

        return ok, f"{note} | {msg}"

    finally:
        print("🧹 关闭浏览器")
        browser.close()
        pw.stop()

# ================= Main =================

def main():
    accounts = load_accounts()
    cookies_map = load_cookies()
    results = []

    for email, pwd in accounts.items():
        try:
            ok, msg = process_account(email, pwd, cookies_map)
            results.append(f"{'✅' if ok else '❌'} {email} — {msg}")
        except Exception as e:
            print(f"🔥 账号异常: {e}")
            results.append(f"❌ {email} — {e}")

    SecretUpdater("LEAFLOW_COOKIES").update(
        dump_cookies(cookies_map)
    )

    tg_send("📋 <b>Leaflow 签到汇总</b>\n\n" + "\n".join(results))


if __name__ == "__main__":
    main()
