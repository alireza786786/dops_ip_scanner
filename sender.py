#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
import os, sys, json, urllib.request, urllib.parse

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")   # optional private chat for health alerts

INLINE_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "✨ کانال:", "url": "https://t.me/Goodbaye_filtering"}],
        [{"text": "💬 گروه:", "url": "https://t.me/CONFIG_V2RAY_VIP"}],
        [{"text": "🌐 اسکنر آنلاین (تست روی اینترنت شما)", "url": "https://alireza786786.github.io/dops_ip_scanner/"}],
        [{"text": "بفرست واسه رفقا", "url": "https://t.me/share/url?url=https://t.me/Goodbaye_filtering"}]
    ]
}

def format_config_remark(flag="🌐", country="Clean CDN", city="Anycast Edge", ping="0", feature="High Speed"):
    return f"👉🆔@Goodbaye_filtering\n📡{flag} {country}\n®️{city}\n🅿️ping:{ping}ms\n⚡{feature}"

def send_telegram_file(file_path: str, caption: str = ""):
    if not BOT_TOKEN or not CHAT_ID or not os.path.exists(file_path):
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    filename = os.path.basename(file_path)
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"parse_mode\"\r\n\r\nHTML\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"reply_markup\"\r\n\r\n{json.dumps(INLINE_KEYBOARD)}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\nContent-Type: text/plain\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            print(f"✅ فایل {filename} با موفقیت به تلگرام ارسال شد.")
        return True
    except Exception as e:
        print(f"❌ خطا در ارسال تلگرام: {e}")
        return False


def send_telegram_message(text: str, chat_id: str = "") -> bool:
    """Plain HTML message (used for admin health alerts). Needs BOT_TOKEN and ADMIN_CHAT_ID (or chat_id)."""
    cid = chat_id or ADMIN_CHAT_ID
    if not BOT_TOKEN or not cid:
        return False
    data = json.dumps({"chat_id": cid, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception as e:
        print(f"❌ خطا در ارسال هشدار تلگرام: {e}")
        return False

if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT_TOKEN و CHAT_ID تنظیم نشده‌اند.  مثال:  export BOT_TOKEN=... ; export CHAT_ID=@your_channel")
    else:
        import tempfile
        test_file = os.path.join(tempfile.gettempdir(), "dops_test.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("DOPS Scanner - test message\n")
        send_telegram_file(test_file, caption="✅ تست ارسال از DOPS Scanner")
