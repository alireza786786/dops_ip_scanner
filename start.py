#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio, os, random, re, ssl, sys, time, json
from typing import List, Optional
from urllib.request import urlopen, Request
from sender import send_telegram_file, format_config_remark

TEST_HOST = "cloudflare.com"
PORT = 443
OUTPUT_DIR = "outputs"
SAMPLES_PER_CIDR = 50
CONCURRENCY = 150
CLOUDFLARE_IPV4_URL = "https://www.cloudflare.com/ips-v4"

def fetch_cloudflare_ranges():
    try:
        req = Request(CLOUDFLARE_IPV4_URL, headers={"User-Agent": "cloudflare-probe/1.0"})
        with urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8").strip()
            return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    except Exception:
        return ["104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "162.158.0.0/15", "188.114.96.0/20"]

def sample_ips(cidr, k):
    import ipaddress
    net = ipaddress.ip_network(cidr, strict=False)
    rnd = random.Random(hash(cidr))
    if net.num_addresses >= 4:
        first, last = int(net.network_address) + 1, int(net.broadcast_address) - 1
        return [str(ipaddress.IPv4Address(first + rnd.randrange(last - first + 1))) for _ in range(min(k, last - first + 1))]
    return []

async def ping_ip(ip):
    cmd = ["ping", "-c", "1", "-W", "1", ip]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        m = re.search(r"time[=<]\s*([\d\.]+)\s*ms", out.decode("utf-8", errors="ignore"))
        return float(m.group(1)) if m else None
    except Exception:
        return None

async def probe(ip):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    t0 = time.time()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host=ip, port=PORT, ssl=ctx, server_hostname=TEST_HOST), timeout=2.5)
        ms = (time.time() - t0) * 1000
        writer.close()
        return {"ip": ip, "ok": True, "connect_ms": round(ms, 1)}
    except Exception as e:
        return {"ip": ip, "ok": False, "err": str(e)}

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cidrs = fetch_cloudflare_ranges()
    targets = []
    for c in cidrs: targets.extend(sample_ips(c, SAMPLES_PER_CIDR))
    targets = sorted(set(targets))
    print(f"📡 Cloudflare IPs to scan: {len(targets)}")

    sem = asyncio.Semaphore(CONCURRENCY)
    async def worker(ip):
        async with sem:
            r = await probe(ip)
            if r["ok"]: r["ping_ms"] = await ping_ip(ip)
            return r

    results = await asyncio.gather(*[worker(ip) for ip in targets])
    alive = [x for x in results if x["ok"]]
    alive.sort(key=lambda x: (x.get("ping_ms") or 9999, x.get("connect_ms") or 9999))
    
    out_file = os.path.join(OUTPUT_DIR, "alive_cloudflare.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        for x in alive:
            f.write(f"{x['ip']} ping={x.get('ping_ms')}ms connect={x['connect_ms']}ms\n")
            
    print(f"\n✅ Cloudflare Scan Done. {len(alive)} IPs alive.")
    if alive:
        best = alive[0]
        best_ping = str(int(best.get("ping_ms") or best.get("connect_ms") or 0))
        base_caption = format_config_remark(flag="☁️", country="Cloudflare", city="Anycast CDN", ping=best_ping, feature=f"تعداد: {len(alive)} آی‌پی سالم")
        
        top5 = alive[:5]
        top_lines = "\n".join([f"🔹 <code>{x['ip']}</code> (⚡ {int(x.get('ping_ms') or x.get('connect_ms') or 0)}ms)" for x in top5])
        
        full_caption = (
            f"{base_caption}\n\n"
            f"👑 <b>۵ آی‌پی برتر (کلیک روی آی‌پی = کپی):</b>\n"
            f"{top_lines}\n\n"
            f"📁 لیست کامل {len(alive)} آی‌پی در فایل بالا قرار دارد."
        )
        send_telegram_file(out_file, caption=full_caption)
    
    os._exit(0)

if __name__ == "__main__":
    asyncio.run(main())
