#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import base64
import requests
import pyotp
from playwright.sync_api import sync_playwright

from engine.notify import send_notify

# ================== 基础配置 ==================

GITHUB_LOGIN_URL = "https://github.com/login"
GITHUB_TEST_URL = "https://github.com/settings/profile"

GH_USERNAME = os.getenv("GH_USERNAME")
GH_PASSWORD = os.getenv("GH_PASSWORD")
GH_SESSION = (os.getenv("GH_SESSION") or "").strip()
GH_2FA_SECRET = os.getenv("GH_2FA_SECRET")

REPO = os.getenv("GITHUB_REPOSITORY")
REPO_TOKEN = os.getenv("REPO_TOKEN")

# ================== 工具函数 ==================

def sep():
    print("=" * 60, flush=True)

def mask_email(email: str) -> str:
    if "@" not in email:
        return email
    name, domain = email.split("@", 1)
    return f"{name[:3]}***{name[-2:]}@{domain}"

def update_github_secret(name, value):
    from nacl import encoding, public

    print("📤 更新 GitHub Actions Secret", flush=True)

    headers = {
        "Authorization": f"token {REPO_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    r = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers=headers,
        timeout=20
    )
    if r.status_code != 200:
        print("❌ 获取 Secret 公钥失败", flush=True)
        return False

    key = r.json()
    pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    encrypted = public.SealedBox(pk).encrypt(value.encode())

    r = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/{name}",
        headers=headers,
        json={
            "encrypted_value": base64.b64encode(encrypted).decode(),
            "key_id": key["key_id"]
        },
        timeout=20
    )
    return r.status_code in (201, 204)

def save_screenshot(page, name):
    path = f"{name}.png"
    page.screenshot(path=path)
    return path

# ================== 主流程 ==================

def main():
    masked = mask_email(GH_USERNAME)

    print(f"🔐 读取账号数: 1", flush=True)
    print(f"🍪 已加载 cookies 账号数: {1 if GH_SESSION else 0}", flush=True)
    sep()

    with sync_playwright() as p:
        print("🌐 启动浏览器", flush=True)

        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        context = browser.new_context()
        page = context.new_page()

        # ================== 🧠 阶段一：cookies 校验 ==================

        sep()
        print("🧠 阶段一：cookies 校验", flush=True)
        sep()

        cookies_ok = False

        if GH_SESSION:
            print("🍪 检测到 GH_SESSION", flush=True)
            print("🍪 注入 GitHub cookies", flush=True)

            context.add_cookies([
                {
                    "name": "user_session",
                    "value": GH_SESSION,
                    "domain": "github.com",
                    "path": "/"
                },
                {
                    "name": "logged_in",
                    "value": "yes",
                    "domain": "github.com",
                    "path": "/"
                }
            ])

            print("🔍 校验 cookies 是否有效", flush=True)
            page.goto(GITHUB_TEST_URL, timeout=30000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)

            if "login" not in page.url:
                print("✅ cookies 有效，跳过登录", flush=True)
                cookies_ok = True
            else:
                print("⚠️ cookies 已失效，需要重新登录", flush=True)
        else:
            print("🍪 未检测到 GH_SESSION", flush=True)
            print("⚠️ cookies 不存在或已失效", flush=True)

        # ================== 🔐 阶段二：登录 ==================

        if not cookies_ok:
            sep()
            print("🔐 阶段二：GitHub 登录", flush=True)
            sep()

            print(f"👤 登录账号: {masked}", flush=True)
            print("🌐 打开 GitHub 登录页", flush=True)

            page.goto(GITHUB_LOGIN_URL, timeout=30000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)

            print("⌨️ 输入用户名和密码", flush=True)
            page.fill('input[name="login"]', GH_USERNAME)
            page.fill('input[name="password"]', GH_PASSWORD)
            page.click('input[type="submit"]')

            time.sleep(3)
            page.wait_for_load_state("networkidle", timeout=30000)

            # 2FA
            if "two-factor" in page.url:
                print("🔑 检测到两步验证", flush=True)

                if GH_2FA_SECRET:
                    print("🔢 使用 TOTP 自动生成验证码", flush=True)
                    code = pyotp.TOTP(GH_2FA_SECRET).now()
                    page.fill('input[autocomplete="one-time-code"]', code)
                    page.keyboard.press("Enter")
                else:
                    print("❌ 未配置 GH_2FA_SECRET，无法继续", flush=True)
                    shot = save_screenshot(page, "2fa_failed")
                    send_notify("❌ GitHub 登录失败", "缺少 2FA 密钥", shot)
                    return

                time.sleep(3)
                page.wait_for_load_state("networkidle", timeout=30000)

            if "login" in page.url:
                print("❌ GitHub 登录失败", flush=True)
                shot = save_screenshot(page, "login_failed")
                send_notify("❌ GitHub 登录失败", "登录流程失败", shot)
                return

            print("✅ GitHub 登录成功", flush=True)

        # ================== 🔄 阶段三：更新 GH_SESSION ==================

        sep()
        print("🔄 阶段三：更新 GH_SESSION", flush=True)
        sep()

        new_session = None
        for c in context.cookies():
            if c["name"] == "user_session" and "github.com" in c["domain"]:
                new_session = c["value"]
                break

        if not new_session:
            print("❌ 未获取到新的 GH_SESSION", flush=True)
            shot = save_screenshot(page, "session_failed")
            send_notify("❌ GH_SESSION 更新失败", "未获取到 session", shot)
            return

        print("🍪 获取新的 user_session", flush=True)
        print(f"🔐 新 GH_SESSION: {new_session[:6]}****{new_session[-4:]}", flush=True)

        if update_github_secret("GH_SESSION", new_session):
            print("✅ GH_SESSION 更新成功", flush=True)
            send_notify("✅ GH_SESSION 更新成功", f"账号 {masked} 已更新")
        else:
            print("❌ GH_SESSION 更新失败", flush=True)
            send_notify("❌ GH_SESSION 更新失败", "Secret 写入失败")

        browser.close()

# ================== 入口 ==================

if __name__ == "__main__":
    main()
