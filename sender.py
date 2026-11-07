#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, urllib.request, urllib.parse

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

INLINE_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "✨ کانال:", "url": "https://t.me/Goodbaye_filtering"}],
        [{"text": "💬 گروه:", "url": "https://t.me/CONFIG_V2RAY_VIP"}],
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


if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT_TOKEN و CHAT_ID تنظیم نشده‌اند.  مثال:  export BOT_TOKEN=... ; export CHAT_ID=@your_channel")
    else:
        import tempfile
        test_file = os.path.join(tempfile.gettempdir(), "dops_test.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("DOPS Scanner - test message\n")
        send_telegram_file(test_file, caption="✅ تست ارسال از DOPS Scanner")
