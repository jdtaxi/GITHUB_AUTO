#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import base64
import requests
import pyotp
from playwright.sync_api import sync_playwright

from engine.notify import send_notify

PROFILE_URL = "https://github.com/settings/profile"
FAIL_SHOT = "github_login_fail.png"

# ================= Secret 更新 =================

class SecretUpdater:
    def __init__(self):
        self.token = os.getenv("REPO_TOKEN")
        self.repo = os.getenv("GITHUB_REPOSITORY")

    def update(self, name, value):
        if not self.token or not self.repo:
            return False

        from nacl import encoding, public

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

        r = requests.get(
            f"https://api.github.com/repos/{self.repo}/actions/secrets/public-key",
            headers=headers,
            timeout=20
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
            timeout=20
        )
        return r.status_code in (201, 204)

# ================= GitHub Session 更新 =================

class GitHubSessionUpdater:

    def __init__(self):
        self.username = os.getenv("GH_USERNAME")
        self.password = os.getenv("GH_PASSWORD")
        self.session = os.getenv("GH_SESSION", "")
        self.totp_secret = os.getenv("GH_2FA_SECRET")
        self.proxy = os.getenv("PROXY")
        self.secret = SecretUpdater()

    def is_session_valid(self, page):
        page.goto(PROFILE_URL, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        return "login" not in page.url.lower()

    def extract_session(self, context):
        for c in context.cookies():
            if c["name"] == "user_session" and "github.com" in c["domain"]:
                return c["value"]
        return None

    def login(self, page):
        page.goto("https://github.com/login", timeout=30000)
        page.fill("input[name=login]", self.username)
        page.fill("input[name=password]", self.password)
        page.click("input[type=submit]")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Device Verify
        if "device-verification" in page.url:
            time.sleep(30)
            page.reload()

        # 2FA
        if "two-factor" in page.url:
            if not self.totp_secret:
                raise RuntimeError("缺少 GH_2FA_SECRET")

            code = pyotp.TOTP(self.totp_secret).now()
            page.fill("input[inputmode=numeric]", code)
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle", timeout=30000)

        if "login" in page.url:
            raise RuntimeError("GitHub 登录失败")

    def run(self):
        start = time.time()
        status = "UNKNOWN"
        err = ""
        shot = None

        try:
            with sync_playwright() as p:
                launch = {"headless": True, "args": ["--no-sandbox"]}
                if self.proxy:
                    launch["proxy"] = {"server": self.proxy}

                browser = p.chromium.launch(**launch)
                context = browser.new_context()
                page = context.new_page()

                # 预加载 Session
                if self.session:
                    context.add_cookies([
                        {"name": "user_session", "value": self.session, "domain": "github.com", "path": "/"},
                        {"name": "logged_in", "value": "yes", "domain": "github.com", "path": "/"}
                    ])

                # Session 校验
                if self.session and self.is_session_valid(page):
                    status = "SESSION_OK"
                else:
                    self.login(page)
                    status = "LOGIN_OK"

                new_session = self.extract_session(context)
                if not new_session:
                    raise RuntimeError("未获取到 GH_SESSION")

                self.secret.update("GH_SESSION", new_session)
                browser.close()

        except Exception as e:
            status = "FAIL"
            err = str(e)

            try:
                if 'page' in locals():
                    page.screenshot(path=FAIL_SHOT)
                    shot = FAIL_SHOT
            except:
                pass

        # ================= 通知 =================

        cost = f"{time.time() - start:.1f}s"
        user = self.username or "UNKNOWN"

        if status == "SESSION_OK":
            send_notify(
                "🔐 GitHub Session 有效",
                f"用户：{user}\n状态：免登录\n耗时：{cost}"
            )

        elif status == "LOGIN_OK":
            send_notify(
                "✅ GitHub 登录成功",
                f"用户：{user}\n方式：账号 + 2FA\nGH_SESSION 已更新\n耗时：{cost}"
            )

        else:
            send_notify(
                "❌ GitHub 登录失败",
                f"用户：{user}\n错误：{err}\n耗时：{cost}",
                image_path=shot
            )

# ================= main =================

if __name__ == "__main__":
    GitHubSessionUpdater().run()
