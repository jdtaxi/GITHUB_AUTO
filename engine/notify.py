# notify.py
# -*- coding: utf-8 -*-

"""
通知依赖模块
支持：
- Telegram 文字
- Telegram 图片（本地文件）
"""

import os
import requests


# =========================
# Telegram 通知
# =========================

def send_telegram_text(bot_token, chat_id, text):
    """
    发送 Telegram 文字消息
    """
    print("📨 [TG] 发送文字通知")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, data=payload, timeout=30)
        print(f"⬅️ [TG] HTTP {r.status_code}")
        if not r.ok:
            print(f"❌ [TG] 发送失败: {r.text}")
        return r.ok
    except Exception as e:
        print(f"💥 [TG] 异常: {e}")
        return False


def send_telegram_image(bot_token, chat_id, image_path, caption=None):
    """
    发送 Telegram 图片（本地文件）
    """
    print(f"🖼️ [TG] 发送图片: {image_path}")

    if not os.path.exists(image_path):
        print("❌ 图片文件不存在")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    data = {
        "chat_id": chat_id,
    }
    if caption:
        data["caption"] = caption

    try:
        with open(image_path, "rb") as f:
            files = {"photo": f}
            r = requests.post(url, data=data, files=files, timeout=60)

        print(f"⬅️ [TG] HTTP {r.status_code}")
        if not r.ok:
            print(f"❌ [TG] 发送失败: {r.text}")
        return r.ok
    except Exception as e:
        print(f"💥 [TG] 异常: {e}")
        return False


# =========================
# 统一调用入口（推荐）
# =========================

def send_notify(
    title,
    content,
    tg_bot_token=None,
    tg_chat_id=None,
    image_path=None,
):
    """
    统一通知入口
    """
    print("🔔 开始发送通知")

    message = f"<b>{title}</b>\n\n{content}"

    if not tg_bot_token or not tg_chat_id:
        print("⚠️ 未配置 Telegram，跳过通知")
        return False

    ok_text = send_telegram_text(
        tg_bot_token,
        tg_chat_id,
        message
    )

    ok_img = True
    if image_path:
        ok_img = send_telegram_image(
            tg_bot_token,
            tg_chat_id,
            image_path,
            caption=title
        )

    return ok_text and ok_img
