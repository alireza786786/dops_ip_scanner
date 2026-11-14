#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
import asyncio, ipaddress, os, time, ssl, sys
from urllib.request import urlopen, Request

CONCURRENCY = 60
TIMEOUT = 2.0
DATA_URL = "https://raw.githubusercontent.com/alireza786786/dops_ip_scanner/data/outputs/"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".dops_cache")


def _parse(text):
    ips = []
    for line in text.splitlines():
        parts = line.strip().split()
        if parts:
            try:
                ipaddress.IPv4Address(parts[0])
                ips.append(parts[0])
            except ValueError:
                pass
    return ips


def load_ips(filename):
    """1) تازه‌ترین لیست از شاخهٔ data (اگر دسترسی هست؛ ذخیره در کش)  2) کش قبلی  3) پوشهٔ outputs کنار برنامه"""
    cache = os.path.join(CACHE_DIR, filename)
    try:
        req = Request(DATA_URL + filename, headers={"User-Agent": "dops-scanner/1.0"})
        with urlopen(req, timeout=8) as r:
            text = r.read().decode("utf-8")
        if _parse(text):
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache, "w", encoding="utf-8") as f:
                f.write(text)
            print("🌐 لیست تازه از مخزن دریافت شد.")
            return _parse(text)
    except Exception:
        pass
    for path, label in ((cache, "کش قبلی"), (os.path.join("outputs", filename), "پوشهٔ outputs")):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                ips = _parse(f.read())
            if ips:
                age = (time.time() - os.path.getmtime(path)) / 3600
                print(f"📁 دریافت از مخزن ممکن نشد؛ از {label} استفاده شد (حدود {age:.0f} ساعت پیش).")
                return ips
    print(f"❌ لیست {filename} پیدا نشد. یک‌بار با دسترسی به گیت‌هاب (مثلاً با VPN) اجرا کنید تا در کش ذخیره شود.")
    return []


async def test_ip(ip, host):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    t0 = time.time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host=ip, port=443, ssl=ctx, server_hostname=host),
            timeout=TIMEOUT
        )
        latency = (time.time() - t0) * 1000
        writer.close()
        return (ip, round(latency, 1))
    except Exception:
        return (ip, None)

async def run_test(filename, host, label):
    ips = load_ips(filename)
    if not ips:
        return
    print(f"\n🔍 در حال تست زنده {len(ips)} آی‌پی {label} با اینترنت خط شما...")
    sem = asyncio.Semaphore(CONCURRENCY)
    
    async def worker(ip):
        async with sem:
            return await test_ip(ip, host)

    results = await asyncio.gather(*[worker(ip) for ip in ips])
    alive = [x for x in results if x[1] is not None]
    alive.sort(key=lambda x: x[1])

    print(f"\n📊 نتایج تست زنده ({label}):")
    print(f"✅ سالم روی خط شما: {len(alive)} از {len(ips)}")
    
    if alive:
        print("\n👑 ۵ آی‌پی برتر مخصوص اپراتور شما (کمترین تاخیر):")
        print("="*45)
        for idx, (ip, lat) in enumerate(alive[:5], 1):
            print(f" {idx}. {ip:<18} ⚡ {lat}ms")
        print("="*45)
        print("💡 می‌توانید آی‌پی شماره ۱ را کپی کرده و در کانفیگ قرار دهید.\n")
    else:
        print("⚠️ متاسفانه هیچ‌کدام از این آی‌پی‌ها روی این خط باز نشدند.\n")

def main():
    print("\n" + "="*45)
    print("📱 تست زنده آی‌پی‌ها با اینترنت داخلی گوشی")
    print("="*45)
    print("1️⃣  تست آی‌پی‌های Cloudflare")
    print("2️⃣  تست آی‌پی‌های Fastly CDN")
    print("0️⃣  بازگشت")
    
    c = input("\nانتخاب کنید (0-2): ").strip()
    if c == "1":
        asyncio.run(run_test("alive_cloudflare.txt", "cloudflare.com", "Cloudflare"))
    elif c == "2":
        asyncio.run(run_test("alive_fastly.txt", "www.github.com", "Fastly"))

if __name__ == "__main__":
    main()
