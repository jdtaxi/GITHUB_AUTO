#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ICMP9 / Incudal / GV.UY 签到
GitHub Actions 专用版本
"""

import asyncio
import os
import base64
from telethon import TelegramClient
from urllib.parse import urlparse

# ===================== 环境变量 =====================

TG_APIS = os.getenv("TG_APIS")  # api_id:api_hash,...
TG_SESSIONS = os.getenv("TG_SESSIONS")  # api_id=base64session;api_id=base64session
PROXIES = os.getenv("PROXIES", "")

if not TG_APIS or not TG_SESSIONS:
    raise SystemExit("❌ 缺少 TG_APIS 或 TG_SESSIONS")

# ===================== 代理解析 =====================

def parse_proxy(proxy_url):
    u = urlparse(proxy_url)
    return {
        "proxy_type": "socks5",
        "addr": u.hostname,
        "port": u.port,
        "username": u.username,
        "password": u.password,
    }

proxy_list = [p for p in PROXIES.splitlines() if p.strip()]

# ===================== Session 写入 =====================

def load_sessions():
    sessions = {}
    for item in TG_SESSIONS.split(";"):
        api_id, data = item.split("=", 1)
        sessions[int(api_id)] = base64.b64decode(data)
    return sessions

# ===================== 单账号执行 =====================

async def run_one(api_id, api_hash, session_bytes):
    session_file = f"TG{api_id}.session"
    with open(session_file, "wb") as f:
        f.write(session_bytes)

    last_error = None

    for proxy_url in proxy_list or [None]:
        proxy = parse_proxy(proxy_url) if proxy_url else None

        try:
            client = TelegramClient(
                f"TG{api_id}",
                api_id,
                api_hash,
                proxy=proxy
            )

            await client.start()
            print(f"✅ API {api_id} 登录成功")

            # ===== GV.UY =====
            await client.send_message(-1003604386217, "incudal.com")
            await asyncio.sleep(2)

            # ===== Incudal =====
            await client.send_message(-1003489851755, "incudal.com")
            await asyncio.sleep(2)

            # ===== ICMP9 =====
            checkin = await client.send_message("@ICMP9_Bot", "/checkin")
            await asyncio.sleep(2)
            await client.delete_messages("@ICMP9_Bot", [checkin.id])

            msgs = await client.get_messages("@ICMP9_Bot", limit=5)
            reply = next(
                (m.text for m in msgs if not m.out and m.date > checkin.date),
                "⚠️ 未匹配到签到回复"
            )

            print(f"[API {api_id}] {reply}")
            await client.disconnect()
            return

        except Exception as e:
            last_error = e
            print(f"❌ API {api_id} 代理失败: {e}")

    raise RuntimeError(f"[API {api_id}] 全部代理失败: {last_error}")

# ===================== 主流程 =====================

async def main():
    sessions = load_sessions()

    for item in TG_APIS.split(","):
        api_id, api_hash = item.split(":")
        api_id = int(api_id)

        if api_id not in sessions:
            print(f"⚠️ API {api_id} 无 session，跳过")
            continue

        await run_one(api_id, api_hash, sessions[api_id])
        await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
