#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio, os, time, ssl, sys

CONCURRENCY = 60
TIMEOUT = 2.0

def load_ips(filename):
    filepath = os.path.join("outputs", filename)
    if not os.path.exists(filepath):
        print(f"❌ فایل {filepath} یافت نشد. ابتدا یک‌بار اسکن را اجرا کنید.")
        return []
    ips = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if parts:
                ips.append(parts[0])
    return ips

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
