#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Leaflow Playwright + API 自动签到
依赖 engine 目录中的模块
"""
import asyncio
import os
import sys
import json
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engine.safe_print import enable_safe_print
enable_safe_print()

from engine.notify import send_notify
from engine.playwright_login import (
    open_browser,
    cookies_ok,
    login_and_get_cookies,
)
from engine.main import (
    perform_token_checkin,
    SecretUpdater,
    getconfig,
    check_socks5_proxy
)

# ================= 基础配置 =================

LOGIN_URL = "https://leaflow.net/login"
DASHBOARD_URL = "https://leaflow.net/dashboard"
checkin_url = "https://checkin.leaflow.net"
main_site = "https://leaflow.net"
headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

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
    raw = os.getenv("LEAFLOW_COOKIES")
    if not raw:
        print("ℹ️ 未检测到 cookies，首次运行")
        return {}

    try:
        cookies = json.loads(raw)
        print(f"🍪 已加载 cookies 账号数: {len(cookies)}")
        return cookies
    except Exception as e:
        print(f"❌ cookies JSON 解析失败: {e}")
        return {}


# ================= 单账号流程 =================

async def process_account(email, password, cookies_map, proxy=None):
    print("=" * 60)
    print(f"👤 开始处理账号: {email}")

    pw, browser, ctx, page = await open_browser(proxy)
    note = ""

    try:
        # ---------- 浏览器出口 IP ----------
        await page.goto("https://api.ipify.org")
        ip = await page.text_content("body")
        print(f"🌍 浏览器出口 IP: {ip}")

        # ---------- cookies 尝试 ----------
        if email in cookies_map:
            print("🍪 尝试复用 cookies")
            await ctx.add_cookies(cookies_map[email])       # ✅ await
            if await cookies_ok(page):                       # ✅ await
                print("✅ cookies 有效")
                note = "cookies复用"
            else:
                print("♻ cookies 已失效")
                raise RuntimeError("cookies expired")
        else:
            print("⚠ 未找到 cookies，执行登录")
            raise RuntimeError("no cookies")

    except Exception as e:
        print(f"🔐 执行 Playwright 登录: {e}")
        cookies = await login_and_get_cookies(page, email, password)   # ✅ await
        cookies_map[email] = cookies
        note = "重新登录"

    finally:
        # 同步 cookies
        cookies_map[email] = await ctx.cookies()     # ✅ await
        await browser.close()                         # ✅ await
        await pw.stop()                               # ✅ await
        print("💾 cookies 已同步，浏览器已关闭")

    # ---------- API 签到 ----------
    print("📡 执行 API 签到")
    try:
        # 如果 perform_token_checkin 本身是 async，记得 await
        ok, msg = await perform_token_checkin(cookies_map[email], email, checkin_url, main_site, headers, proxy=None)
        print(f"ℹ️ API 签到结果: {ok}, {msg}")
    except Exception as e:
        ok, msg = False, f"签到失败: {e}"
        print(f"❌ API 签到异常: {e}")

    return ok, f"{note} | {msg}"

# ================= Main =================

async def main():
    useproxy = True
    password = os.getenv("CONFIG_PASSWORD","").strip()
    if not password:
        raise RuntimeError("❌ 未设置 CONFIG_PASSWORD")
    config = getconfig(password)

    LF_INFO = config.get("LF_INFO","")
    if not LF_INFO:
        raise RuntimeError("❌ 配置文件中不存在 LF_INFO")
    print(f'ℹ️ 已读取: {LF_INFO.get("description","")}')

    accounts = LF_INFO.get("value","")
    cookies_map = load_cookies()
    results = []

    for idx, acc in enumerate(accounts):
        username = acc.get("usename")
        password = acc.get("password")
    
        if not username or not password:
            print(f"⚠ 跳过非法账号 {idx+1}: {acc}")
            continue
        print(f'----------【{idx+1}】{username}----------')

        # ---------- 代理测试 ----------
        proxyurl = None
        if useproxy::
            ok, msg, proxyurl = check_socks5_proxy()
            print(f"{'✅' if ok else '❌'} {username} 测试代理: {msg}")
            results.append(f"{'✅' if ok else '❌'} {username} 测试代理— {msg}")
        else:
            print(f"❌ {username} 代理测试异常: {e}")
            results.append(f"❌ {username} — {e}")

        # ---------- 执行账号签到 ----------
        try:
            ok, msg = await process_account(username, password, cookies_map, proxyurl)
            results.append(f"{'✅' if ok else '❌'} {username} — {msg}")
        except Exception as e:
            print(f"❌ {username} 签到异常: {e}")
            results.append(f"❌ {username} — {e}")

    # ---------- 回写 cookies ----------
    print("💾 回写 cookies")
    SecretUpdater("LEAFLOW_COOKIES").update(json.dumps(cookies_map, ensure_ascii=False))

    # ---------- 通知 ----------
    print("📨 发送签到汇总通知")
    send_notify(title="Leaflow 自动签到汇总", content="\n".join(results))
    print("✅ 全部完成")


if __name__ == "__main__":
    asyncio.run(main())
