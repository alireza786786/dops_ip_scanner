#!/usr/bin/env python3
import asyncio, os, random, re, ssl, sys, time, json
from typing import List, Optional
from urllib.request import urlopen, Request
from sender import send_telegram_file, format_config_remark

TEST_HOST = "www.github.com"
PORT = 443
OUTPUT_DIR = "outputs"
SAMPLES_PER_CIDR = 100
CONCURRENCY = 150

def fetch_fastly_ranges():
    try:
        req = Request("https://api.fastly.com/public-ip-list", headers={"User-Agent": "fastly-probe/2.1"})
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")).get("addresses", [])
    except Exception:
        return ["151.101.0.0/16", "199.232.0.0/16", "146.75.0.0/17", "140.248.64.0/18"]

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
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host=ip, port=PORT, ssl=ctx, server_hostname=TEST_HOST), timeout=3.0)
        ms = (time.time() - t0) * 1000
        writer.close()
        await writer.wait_closed()
        return {"ip": ip, "ok": True, "connect_ms": round(ms, 1)}
    except Exception as e:
        return {"ip": ip, "ok": False, "err": str(e)}

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cidrs = fetch_fastly_ranges()
    targets = []
    for c in cidrs: targets.extend(sample_ips(c, SAMPLES_PER_CIDR))
    targets = sorted(set(targets))
    print(f"📡 Fastly IPs to scan: {len(targets)}")

    sem = asyncio.Semaphore(CONCURRENCY)
    async def worker(ip):
        async with sem:
            r = await probe(ip)
            if r["ok"]: r["ping_ms"] = await ping_ip(ip)
            return r

    results = await asyncio.gather(*[worker(ip) for ip in targets])
    alive = [x for x in results if x["ok"]]
    out_file = os.path.join(OUTPUT_DIR, "alive_fastly.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        for x in alive: f.write(f"{x["ip"]} ping={x.get("ping_ms")}ms connect={x["connect_ms"]}ms\n")
    print(f"\n✅ Fastly Scan Done. {len(alive)} IPs alive.")
    if alive:
        best = min(alive, key=lambda x: (x.get("ping_ms") or 9999))
        send_telegram_file(out_file, caption=format_config_remark(flag="⚡", country="Fastly CDN", city="Global Edge", ping=str(int(best.get("ping_ms") or 0)), feature="Optimized Anycast"))

if __name__ == "__main__":
    asyncio.run(main())
