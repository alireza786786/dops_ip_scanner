#!/usr/bin/env python3
import asyncio
import csv
import ipaddress
import json
import os
import random
import re
import ssl
import sys
import time
from typing import List, Tuple, Optional
from urllib.request import urlopen, Request
import socket
from contextlib import contextmanager

from sender import send_telegram_file, format_config_remark

TEST_HOST = "cloudflare.com"
TEST_PATH = "/"
PORT = 443
OUTPUT_DIR = "outputs"

SAMPLES_PER_CIDR_V4 = 80
CONCURRENCY = 120
PING_ENABLED = True
PING_TIMEOUT_MS = 900
TCP_TIMEOUT = 2.0
TLS_TIMEOUT = 3.0
READ_TIMEOUT = 4.0
READ_BYTES = 150_000
SEED = 7
TRY_INSECURE_TLS = True

CLOUDFLARE_IPV4_URL = "https://www.cloudflare.com/ips-v4"

def fetch_cloudflare_ranges() -> List[str]:
    headers = {"User-Agent": "cloudflare-probe/1.0"}
    ipv4 = []
    try:
        req = Request(CLOUDFLARE_IPV4_URL, headers=headers)
        with urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8").strip()
            ipv4 = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    except Exception:
        pass
    if not ipv4:
        ipv4 = ["104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "162.158.0.0/15", "188.114.96.0/20"]
    return ipv4

def sample_ips_from_cidr(cidr: str, k: int, seed: int = 0) -> List[str]:
    net = ipaddress.ip_network(cidr, strict=False)
    rnd = random.Random(hash((cidr, seed)))
    if isinstance(net, ipaddress.IPv4Network) and net.num_addresses >= 4:
        first = int(net.network_address) + 1
        last = int(net.broadcast_address) - 1
        host_count = max(0, last - first + 1)
        picks = set()
        while len(picks) < min(k, host_count):
            picks.add(first + rnd.randrange(host_count))
        return [str(ipaddress.IPv4Address(x)) for x in picks]
    return []

async def ping_latency_ms(ip: str, timeout_ms: int = 900) -> Optional[float]:
    cmd = ["ping", "-c", "1", "-W", "1", ip] if not sys.platform.startswith("win") else ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        m = re.search(r"time[=<]\s*([\d\.]+)\s*ms", out.decode("utf-8", errors="ignore"), re.IGNORECASE)
        return float(m.group(1)) if m else None
    except Exception:
        return None

async def https_probe_and_speed(ip: str) -> dict:
    t0 = time.time()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, PORT), timeout=TCP_TIMEOUT)
        writer.close()
        await writer.wait_closed()
    except Exception as e:
        return {"ip": ip, "ok": False, "stage": "tcp", "connect_ms": None, "mbps": None, "err": str(e)}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    t0 = time.time()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host=ip, port=PORT, ssl=ctx, server_hostname=TEST_HOST), timeout=TLS_TIMEOUT)
        connect_ms = (time.time() - t0) * 1000
    except Exception as e:
        return {"ip": ip, "ok": False, "stage": "tls", "connect_ms": None, "mbps": None, "err": str(e)}

    try:
        writer.write(f"GET {TEST_PATH} HTTP/1.1\r\nHost: {TEST_HOST}\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        chunk = await asyncio.wait_for(reader.read(4096), timeout=READ_TIMEOUT)
        writer.close()
        await writer.wait_closed()
        return {"ip": ip, "ok": True, "stage": "ok", "connect_ms": round(connect_ms, 1), "mbps": 5.0, "err": ""}
    except Exception as e:
        return {"ip": ip, "ok": False, "stage": "read", "connect_ms": round(connect_ms, 1), "mbps": None, "err": str(e)}

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cidrs = fetch_cloudflare_ranges()
    targets = []
    for c in cidrs:
        targets.extend(sample_ips_from_cidr(c, SAMPLES_PER_CIDR_V4, seed=SEED))
    targets = sorted(set(targets))
    print(f"📡 Cloudflare IPs to scan: {len(targets)}")

    sem = asyncio.Semaphore(CONCURRENCY)
    async def worker(ip):
        async with sem:
            r = await https_probe_and_speed(ip)
            if r["ok"] and PING_ENABLED:
                r["ping_ms"] = await ping_latency_ms(ip, PING_TIMEOUT_MS)
            return r

    results = []
    tasks = [asyncio.create_task(worker(ip)) for ip in targets]
    for coro in asyncio.as_completed(tasks):
        r = await coro
        results.append(r)
        if r["ok"]:
            print(f" ✓ {r['ip']:15} tls={r['connect_ms']}ms ping={r.get('ping_ms')}ms")

    alive = [x for x in results if x["ok"]]
    out_file = os.path.join(OUTPUT_DIR, "alive_cloudflare.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        for x in alive:
            f.write(f"{x['ip']} ping={x.get('ping_ms')}ms connect={x['connect_ms']}ms\n")

    print(f"\n✅ اسکن تمام شد. {len(alive)} آی‌پی سالم پیدا شد.")

    if alive:
        best = min(alive, key=lambda x: (x.get("ping_ms") or 9999))
        best_ping = str(int(best.get("ping_ms") or 0))
        caption = format_config_remark(flag="☁️", country="Cloudflare", city="Anycast CDN", ping=best_ping, feature=f"تعداد: {len(alive)} آی‌پی سالم")
        send_telegram_file(out_file, caption=caption)

if __name__ == "__main__":
    asyncio.run(main())
