#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import base64
import requests
from playwright.sync_api import sync_playwright, TimeoutError

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
        json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=20
    )

# ================= 账号 / Cookie =================

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
    parts = []
    for email, cookies in cookies_map.items():
        parts.append(f"{email}:{json.dumps(cookies, separators=(',', ':'))}")
    return ",".join(parts)

# ================= GitHub Secret 更新 =================

class SecretUpdater:
    def __init__(self, name):
        self.name = name

    def update(self, value):
        if not (REPO_TOKEN and REPO):
            print("⚠ 未设置 REPO_TOKEN，跳过 cookies 回写")
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
            print("❌ 获取 GitHub 公钥失败")
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

        print(f"💾 cookies 回写状态: {r.status_code}")
        return r.status_code in (201, 204)

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
    print("🔍 检查 cookies 是否有效")
    page.goto(DASHBOARD_URL, timeout=30000)
    time.sleep(2)
    print(f"📍 当前 URL: {page.url}")
    return "login" not in page.url.lower()



def login(page, email, password, screenshot_cb=None):
    """
    Leaflow 登录函数（稳定版）
    - 支持动态密码框
    - 支持 button checkbox 记住登录
    - 失败截图
    """

    print(f"\n🔐 开始登录: {email}")

    # 打开登录页
    page.goto(LOGIN_URL, timeout=30000)
    print("➡ 已打开登录页")

    try:
        # ===== 账号输入框 =====
        page.wait_for_selector("#account", timeout=30000)
        page.fill("#account", email)
        print("✅ 已输入账号")

        # ===== 等待 JS 渲染密码框 =====
        page.wait_for_timeout(2000)
        page.wait_for_selector("#password", timeout=30000)
        page.fill("#password", password)
        print("✅ 已输入密码")

        # ===== 勾选“保持登录状态” =====
        try:
            remember = page.locator("#remember")
            remember.wait_for(state="visible", timeout=5000)

            if remember.get_attribute("aria-checked") != "true":
                remember.click()
                print("☑️ 已勾选保持登录状态")
            else:
                print("ℹ️ 已是保持登录状态")

        except Exception:
            print("⚠️ 未找到保持登录状态按钮，跳过")

        # ===== 提交登录 =====
        page.click('button[type="submit"]')
        print("➡ 已提交登录")

        page.wait_for_load_state("networkidle", timeout=30000)

        # ===== 判断是否成功 =====
        if "login" in page.url.lower():
            raise RuntimeError("登录失败，仍停留在登录页")

        # 额外校验 Dashboard
        page.goto(DASHBOARD_URL, timeout=30000)
        page.wait_for_timeout(2000)

        if "login" in page.url.lower():
            raise RuntimeError("登录失败，Dashboard 校验未通过")

        print("🎉 登录成功")

    except Exception as e:
        print(f"❌ 登录异常: {e}")

        # 截图（给 TG 用）
        try:
            img = f"leaflow_login_fail.png"
            page.screenshot(path=img, full_page=True)
            print(f"📸 已截图: {img}")

            if screenshot_cb:
                screenshot_cb(
                    img,
                    f"❌ Leaflow 登录失败\n👤 {email}\n🕒 {datetime.now():%F %T}"
                )
        except Exception:
            print("⚠️ 截图失败")

        raise

# ================= API 签到 =================

def api_checkin(cookies):
    print("📡 API 签到请求")
    s = requests.Session()
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain"))

    r = s.post(CHECKIN_API, timeout=20)
    print(f"📥 API 返回码: {r.status_code}")

    if r.status_code != 200:
        return False, "接口异常"

    j = r.json()
    return j.get("success", False), j.get("message", "未知返回")

# ================= 主流程 =================

def process_account(email, password, cookies_map):
    pw, browser, ctx, page = open_browser()
    note = ""

    try:
        if email in cookies_map:
            print(f"🍪 尝试复用 cookies: {email}")
            try:
                ctx.add_cookies(cookies_map[email])
                if cookies_ok(page):
                    note = "cookies复用"
                else:
                    raise Exception
            except Exception:
                print("♻ cookies 失效，重新登录")
                login(page, email, password)
                note = "cookies失效重登"
        else:
            print("🆕 无 cookies，首次登录")
            login(page, email, password)
            note = "首次登录"

        cookies_map[email] = ctx.cookies()
        ok, msg = api_checkin(cookies_map[email])
        print(f"📊 签到结果: {ok} | {msg}")
        return ok, f"{note} | {msg}"

    finally:
        browser.close()
        pw.stop()
        print("🧹 浏览器关闭")

# ================= Main =================

def main():
    accounts = load_accounts()
    cookies_map = load_cookies()
    results = []

    for email, pwd in accounts.items():
        print("=" * 60)
        print(f"👤 开始处理账号: {email}")
        try:
            ok, msg = process_account(email, pwd, cookies_map)
            results.append(f"{'✅' if ok else '❌'} {email} — {msg}")
        except Exception as e:
            print(f"🔥 异常: {e}")
            results.append(f"❌ {email} — {e}")

    SecretUpdater("LEAFLOW_COOKIES").update(
        dump_cookies(cookies_map)
    )

    tg_send("📋 <b>Leaflow 签到汇总</b>\n\n" + "\n".join(results))


if __name__ == "__main__":
    main()
