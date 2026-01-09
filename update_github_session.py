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
        print(f"[初始化] Secret 更新器已初始化，仓库：{self.repo}", flush=True)

    def update(self, name, value):
        print(f"[Secret] 开始更新 Secret：{name}", flush=True)

        if not self.token or not self.repo:
            print("[Secret] 缺少 REPO_TOKEN 或 GITHUB_REPOSITORY，无法更新", flush=True)
            return False

        from nacl import encoding, public

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

        print("[Secret] 获取仓库公钥中…", flush=True)
        r = requests.get(
            f"https://api.github.com/repos/{self.repo}/actions/secrets/public-key",
            headers=headers,
            timeout=20
        )

        if r.status_code != 200:
            print("[Secret] 获取公钥失败", flush=True)
            return False

        key = r.json()
        pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
        encrypted = public.SealedBox(pk).encrypt(value.encode())

        print("[Secret] 正在提交加密后的 Secret…", flush=True)
        r = requests.put(
            f"https://api.github.com/repos/{self.repo}/actions/secrets/{name}",
            headers=headers,
            json={
                "encrypted_value": base64.b64encode(encrypted).decode(),
                "key_id": key["key_id"]
            },
            timeout=20
        )

        ok = r.status_code in (201, 204)
        print(f"[Secret] Secret 更新结果：{'成功' if ok else '失败'}", flush=True)
        return ok


# ================= GitHub Session 更新 =================

class GitHubSessionUpdater:

    def __init__(self):
        print("[初始化] 正在初始化 GitHub Session 更新器", flush=True)

        self.username = os.getenv("GH_USERNAME")
        self.password = os.getenv("GH_PASSWORD")
        self.session = os.getenv("GH_SESSION", "")
        self.totp_secret = os.getenv("GH_2FA_SECRET")
        self.proxy = os.getenv("PROXY")

        self.secret = SecretUpdater()

        print(f"[初始化] 用户名是否存在：{'是' if self.username else '否'}", flush=True)
        print(f"[初始化] 密码是否存在：{'是' if self.password else '否'}", flush=True)
        print(f"[初始化] 是否已有 Session：{'是' if self.session else '否'}", flush=True)
        print(f"[初始化] 是否配置 2FA：{'是' if self.totp_secret else '否'}", flush=True)
        print(f"[初始化] 代理配置：{self.proxy or '未使用'}", flush=True)

    def is_session_valid(self, page):
        print("[检查] 正在校验 GH_SESSION 是否有效…", flush=True)
        page.goto(PROFILE_URL, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        ok = "login" not in page.url.lower()
        print(f"[检查] Session 校验结果：{'有效' if ok else '无效'}，当前 URL：{page.url}", flush=True)
        return ok

    def extract_session(self, context):
        print("[Cookie] 正在提取 user_session Cookie…", flush=True)
        for c in context.cookies():
            if c["name"] == "user_session" and "github.com" in c["domain"]:
                print("[Cookie] 已成功获取 user_session", flush=True)
                return c["value"]
        print("[Cookie] 未找到 user_session", flush=True)
        return None

    def login(self, page):
        print("[登录] 打开 GitHub 登录页面", flush=True)
        page.goto("https://github.com/login", timeout=30000)

        print("[登录] 填写用户名", flush=True)
        page.fill("input[name=login]", self.username)

        print("[登录] 填写密码", flush=True)
        page.fill("input[name=password]", self.password)

        print("[登录] 提交登录表单", flush=True)
        page.click("input[type=submit]")
        page.wait_for_load_state("networkidle", timeout=30000)

        if "device-verification" in page.url:
            print("[登录] 检测到设备验证，等待 30 秒", flush=True)
            time.sleep(30)
            page.reload()

        if "two-factor" in page.url:
            print("[2FA] 检测到两步验证，正在生成验证码", flush=True)
            if not self.totp_secret:
                raise RuntimeError("未配置 GH_2FA_SECRET")

            code = pyotp.TOTP(self.totp_secret).now()
            print("[2FA] 已生成验证码，提交中…", flush=True)
            page.fill("input[inputmode=numeric]", code)
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle", timeout=30000)

        if "login" in page.url:
            raise RuntimeError(f"登录失败，当前页面：{page.url}")

        print("[登录] GitHub 登录成功", flush=True)

    def run(self):
        start = time.time()
        status = "UNKNOWN"
        error = ""
        screenshot = None

        try:
            print("[初始化] 启动 Playwright 浏览器", flush=True)

            with sync_playwright() as p:
                launch = {"headless": True, "args": ["--no-sandbox"]}

                if self.proxy:
                    launch["proxy"] = {"server": self.proxy}
                    print(f"[初始化] 使用代理：{self.proxy}", flush=True)

                browser = p.chromium.launch(**launch)
                context = browser.new_context()
                page = context.new_page()

                if self.session:
                    print("[Cookie] 注入已有 GH_SESSION", flush=True)
                    context.add_cookies([
                        {"name": "user_session", "value": self.session, "domain": "github.com", "path": "/"},
                        {"name": "logged_in", "value": "yes", "domain": "github.com", "path": "/"}
                    ])

                if self.session and self.is_session_valid(page):
                    status = "SESSION_OK"
                    print("[结果] Session 有效，跳过登录流程", flush=True)
                else:
                    print("[结果] Session 无效或不存在，开始登录", flush=True)
                    self.login(page)
                    status = "LOGIN_OK"

                new_session = self.extract_session(context)
                if not new_session:
                    raise RuntimeError("无法提取新的 GH_SESSION")

                if self.secret.update("GH_SESSION", new_session):
                    print("[Secret] GH_SESSION 已成功更新", flush=True)
                else:
                    print("[Secret] GH_SESSION 更新失败", flush=True)

                browser.close()

        except Exception as e:
            status = "FAIL"
            error = str(e)
            print(f"[错误] 执行过程中发生异常：{error}", flush=True)

            try:
                print("[截图] 正在保存失败截图", flush=True)
                page.screenshot(path=FAIL_SHOT)
                screenshot = FAIL_SHOT
            except Exception as se:
                print(f"[截图] 截图失败：{se}", flush=True)

        cost = f"{time.time() - start:.1f}s"
        user = self.username or "UNKNOWN"

        print(f"[结果] 最终状态={status}，耗时={cost}", flush=True)

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
                f"用户：{user}\n错误原因：{error}\n耗时：{cost}",
                image_path=screenshot
            )


# ================= main =================

if __name__ == "__main__":
    GitHubSessionUpdater().run()
