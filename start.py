#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cloudflare clean-IP scanner (stdlib only; GitHub Actions / Termux / PC).

Outputs (the .txt stays backward compatible: the first token of each line is the IP):
  outputs/alive_cloudflare.txt   <ip> ping=..ms connect=..ms jitter=..ms colo=XXX ports=443,2053
  outputs/alive_cloudflare.json  same data + scan metadata (time, vantage, failure tally)
  outputs/scan_state.json        learned /24 blocks for adaptive sampling (pruned after 30 days)

Exit code: 0 = lists updated, 1 = scan looked broken (previous lists are kept untouched).
"""
import asyncio, ipaddress, json, math, os, random, re, ssl, sys, time
from collections import Counter
from datetime import datetime, timezone
from statistics import median
from urllib.request import urlopen, Request
from sender import send_telegram_file, format_config_remark

TEST_HOST = os.environ.get("TEST_HOST", "cloudflare.com")
PORT = int(os.environ.get("SCAN_PORT", "443"))
EXTRA_PORTS = [2053, 2083, 2087, 2096, 8443]   # Cloudflare TLS ports, checked for the best IPs only
OUTPUT_DIR = "outputs"
SAMPLES_PER_CIDR = int(os.environ.get("SAMPLES_PER_CIDR", "50"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "150"))
ROUNDS = 3              # TLS handshakes per IP (jitter / loss)
HOT_SAMPLES = 150       # extra samples drawn from /24 blocks that were healthy before
PORT_CHECK_TOP = 40
MIN_ALIVE = 5           # below this the scan is considered broken -> keep old files
TIMEOUT = 2.5
STATE_DAYS = 30
SHOW_VANTAGE_NOTE = True
CLOUDFLARE_IPV4_URL = "https://www.cloudflare.com/ips-v4"
FALLBACK_RANGES = ["173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
                   "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
                   "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22"]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def state_file():
    return os.path.join(OUTPUT_DIR, "scan_state.json")


# ---------------------------------------------------------------- ranges / sampling
def _valid(lines):
    out = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            n = ipaddress.ip_network(line, strict=False)
        except ValueError:
            continue
        if n.version == 4 and n.prefixlen >= 8:
            out.append(str(n))
    return out


def fetch_ranges():
    try:
        req = Request(CLOUDFLARE_IPV4_URL, headers={"User-Agent": "cloudflare-probe/1.0"})
        with urlopen(req, timeout=30) as r:
            got = _valid(r.read().decode("utf-8").splitlines())
        if len(got) >= 5:
            return got
    except Exception as e:
        print(f"⚠️ official range list unavailable ({e}); using the built-in list")
    return list(FALLBACK_RANGES)


def sample_ips(cidr, k):
    net = ipaddress.ip_network(cidr, strict=False)
    if net.num_addresses < 4:
        return []
    first, last = int(net.network_address) + 1, int(net.broadcast_address) - 1
    if last - first + 1 <= k:
        return [str(ipaddress.IPv4Address(x)) for x in range(first, last + 1)]
    return [str(ipaddress.IPv4Address(x)) for x in random.sample(range(first, last + 1), k)]


def load_state():
    try:
        with open(state_file(), encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = {}
    cut = time.time() - STATE_DAYS * 86400
    blocks = s.get("blocks") if isinstance(s.get("blocks"), dict) else {}
    s["blocks"] = {b: v for b, v in blocks.items() if isinstance(v, dict) and v.get("t", 0) >= cut}
    s["last_alive"] = s.get("last_alive") if isinstance(s.get("last_alive"), list) else []
    return s


def learn(state, tested, healthy):
    now, hs = time.time(), set(healthy)
    for ip in tested:
        e = state["blocks"].setdefault(ip.rsplit(".", 1)[0], {"p": 0, "h": 0, "t": 0})
        e["p"] += 1
        e["h"] += 1 if ip in hs else 0
        e["t"] = now
    if len(state["blocks"]) > 4000:
        keep = sorted(state["blocks"].items(), key=lambda kv: kv[1]["t"], reverse=True)[:4000]
        state["blocks"] = dict(keep)
    state["last_alive"] = list(healthy)[:150]


def build_targets(cidrs, state):
    nets = [ipaddress.ip_network(c, strict=False) for c in cidrs]
    inside = lambda ip: any(ipaddress.ip_address(ip) in n for n in nets)
    targets = set()
    for c in cidrs:
        targets.update(sample_ips(c, SAMPLES_PER_CIDR))
    hot = [(b, v) for b, v in state["blocks"].items() if v.get("h", 0) > 0 and inside(b + ".1")]
    if hot:  # exploit blocks that were healthy before (Bayesian-smoothed weight)
        w = [(v["h"] + 1) / (v["p"] + 3) for _, v in hot]
        for b in random.choices([b for b, _ in hot], weights=w, k=HOT_SAMPLES):
            targets.add(f"{b}.{random.randint(1, 254)}")
    targets.update(ip for ip in state["last_alive"] if inside(ip))  # re-verify yesterday's winners
    return sorted(targets)


# ---------------------------------------------------------------- probing
def _kind(e):
    if isinstance(e, ConnectionResetError):
        return "rst"        # reset mid-handshake (DPI-injection signature when run from inside a filtered network)
    if isinstance(e, ConnectionRefusedError):
        return "refused"
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"    # silent drop
    if isinstance(e, ssl.SSLError):
        return "tls"
    return "other"


async def _close(w):
    try:
        w.close()
        await w.wait_closed()
    except Exception:
        pass


async def tcp_rtt(ip, port):
    t0 = time.perf_counter()
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(ip, port), TIMEOUT)
    except Exception:
        return None
    ms = (time.perf_counter() - t0) * 1000
    await _close(w)
    return ms


async def tls_probe(ip, port, http=False):
    t0 = time.perf_counter()
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port, ssl=_CTX, server_hostname=TEST_HOST), TIMEOUT)
    except Exception as e:
        return {"ok": False, "err": _kind(e)}
    res = {"ok": True, "ms": (time.perf_counter() - t0) * 1000, "status": 0, "colo": ""}
    if http:
        try:
            w.write(f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {TEST_HOST}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n".encode())
            await w.drain()
            buf, end = b"", time.perf_counter() + TIMEOUT
            while len(buf) < 16384 and time.perf_counter() < end:
                chunk = await asyncio.wait_for(r.read(4096), max(0.05, end - time.perf_counter()))
                if not chunk:
                    break
                buf += chunk
            head = buf.decode("latin1")
            m = re.match(r"HTTP/1\.[01] (\d{3})", head)
            res["status"] = int(m.group(1)) if m else 0
            c = re.search(r"^colo=(\w+)", head, re.M)
            res["colo"] = c.group(1) if c else ""
        except Exception:
            pass
    await _close(w)
    return res


async def scan_ip(ip, port):
    first = await tls_probe(ip, port, http=True)
    if not first["ok"]:
        return {"ip": ip, "ok": False, "err": first["err"]}
    tls, fails = [first["ms"]], 0
    for _ in range(ROUNDS - 1):
        r = await tls_probe(ip, port)
        if r["ok"]:
            tls.append(r["ms"])
        else:
            fails += 1
    if len(tls) < math.ceil(ROUNDS / 2):
        return {"ip": ip, "ok": False, "err": "unstable"}
    rtt = await tcp_rtt(ip, port)
    conn, jitter, loss = median(tls), max(tls) - min(tls), round(fails / ROUNDS * 100)
    return {"ip": ip, "ok": True, "ping_ms": round(rtt if rtt is not None else conn, 1), "connect_ms": round(conn, 1),
            "jitter_ms": round(jitter, 1), "loss": loss, "colo": first["colo"], "status": first["status"],
            "verified": bool(first["colo"]), "ports": [port], "score": conn + jitter * 0.5 + loss * 4}


async def add_ports(top, sem):
    async def one(r, p):
        async with sem:
            if (await tls_probe(r["ip"], p))["ok"]:
                r["ports"].append(p)
    await asyncio.gather(*[one(r, p) for r in top for p in EXTRA_PORTS])
    for r in top:
        r["ports"].sort()


# ---------------------------------------------------------------- output
def _atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def write_outputs(pool, meta):
    lines = "".join(f"{r['ip']} ping={r['ping_ms']}ms connect={r['connect_ms']}ms jitter={r['jitter_ms']}ms "
                    f"colo={r['colo'] or '-'} ports={','.join(map(str, r['ports']))}\n" for r in pool)
    txt = os.path.join(OUTPUT_DIR, "alive_cloudflare.txt")
    _atomic(txt, lines)
    keys = ("ip", "ping_ms", "connect_ms", "jitter_ms", "loss", "colo", "ports", "verified")
    _atomic(os.path.join(OUTPUT_DIR, "alive_cloudflare.json"),
            json.dumps({**meta, "ips": [{k: r[k] for k in keys} for r in pool]}, ensure_ascii=False, indent=1))
    return txt


def telegram(pool, txt):
    best = pool[0]
    cap = format_config_remark(flag="☁️", country="Cloudflare", city="Anycast CDN", ping=str(int(best["ping_ms"])),
                               feature=f"تعداد: {len(pool)} آی‌پی سالم")
    top = "\n".join(f"🔹 <code>{x['ip']}</code> (⚡ {int(x['ping_ms'])}ms · پورت‌ها: {','.join(map(str, x['ports']))})" for x in pool[:5])
    note = "\n\nℹ️ این تست از سرور گیت‌هاب (خارج ایران) انجام شده؛ برای نتیجهٔ دقیق روی اینترنت خودتان از اسکنر وب استفاده کنید." \
        if SHOW_VANTAGE_NOTE and os.environ.get("GITHUB_ACTIONS") else ""
    send_telegram_file(txt, caption=f"{cap}\n\n👑 <b>۵ آی‌پی برتر (کلیک روی آی‌پی = کپی):</b>\n{top}\n\n"
                                    f"📁 لیست کامل {len(pool)} آی‌پی در فایل بالا قرار دارد.{note}")


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    state, cidrs = load_state(), fetch_ranges()
    targets = build_targets(cidrs, state)
    print(f"📡 Cloudflare IPs to scan: {len(targets)} (port {PORT}, {ROUNDS} rounds each)")
    sem = asyncio.Semaphore(CONCURRENCY)

    async def worker(ip):
        async with sem:
            return await scan_ip(ip, PORT)

    results = await asyncio.gather(*[worker(ip) for ip in targets])
    alive = [r for r in results if r["ok"]]
    fails = Counter(r["err"] for r in results if not r["ok"])
    verified = [r for r in alive if r["verified"]]
    pool = verified or alive
    if verified == [] and alive:
        print("⚠️ /cdn-cgi/trace gave no colo for any IP; falling back to TLS-only results")
    if len(pool) < MIN_ALIVE:
        print(f"❌ only {len(pool)} usable IPs (< {MIN_ALIVE}); keeping previous lists. Failures: {dict(fails)}")
        return 1
    pool.sort(key=lambda r: r["score"])
    await add_ports(pool[:PORT_CHECK_TOP], sem)
    learn(state, targets, [r["ip"] for r in pool])
    _atomic(state_file(), json.dumps(state, ensure_ascii=False))
    meta = {"scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "vantage": "github-actions" if os.environ.get("GITHUB_ACTIONS") else "local",
            "port": PORT, "tested": len(targets), "alive": len(alive), "verified": len(verified), "failures": dict(fails)}
    txt = write_outputs(pool, meta)
    print(f"\n✅ Cloudflare Scan Done. {len(pool)} IPs usable ({len(verified)} verified). Failures: {dict(fails)}")
    telegram(pool, txt)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
