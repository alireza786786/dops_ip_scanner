#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared CDN clean-IP scan engine (stdlib only; GitHub Actions / Termux / PC).

Used by start.py (Cloudflare) and fastly.py. Per profile it writes, inside OUTPUT_DIR:
  alive_<name>.txt    <ip> ping=..ms connect=..ms jitter=..ms colo=XXX ports=443,2053   (first token = IP)
  alive_<name>.json   same data + metadata (time, vantage, counts, failure tally, seed info)
  scan_state_<key>.json  learned /24 blocks, last winners, last Telegram send time

Exit code 0 = lists updated, 1 = scan looked broken (previous lists are kept untouched).
Telegram is sent at most every TG_INTERVAL_MIN minutes (default 170) unless TG_FORCE=1.
"""
import asyncio, ipaddress, json, math, os, random, re, ssl, time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Callable, List, Optional
from urllib.request import urlopen, Request
from sender import send_telegram_file, format_config_remark

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "outputs")
ROUNDS = 3              # TLS handshakes per IP (jitter / loss)
TIMEOUT = 2.5
STATE_DAYS = 30
HOT_SAMPLES = 150       # draws from /24 blocks that were healthy before
SEED_BLOCK_SAMPLES = 5  # draws per seed /24 block
PORT_CHECK_TOP = 40
MIN_ALIVE = 5           # below this the scan is considered broken -> keep old files
TG_INTERVAL_MIN = int(os.environ.get("TG_INTERVAL_MIN", "170"))
TG_FORCE = os.environ.get("TG_FORCE", "").lower() in ("1", "true", "yes")
SHOW_VANTAGE_NOTE = True
MIN_GAP_MIN = int(os.environ.get("SCAN_MIN_GAP_MIN", "0") or 0)   # scheduled runs skip a scan if the last one is younger than this

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


@dataclass
class Profile:
    key: str                                   # cloudflare / fastly (state file name)
    out_name: str                              # alive_cloudflare / alive_fastly
    test_host: str                             # SNI + Host header
    port: int
    fetch_ranges: Callable[[], List[str]]
    verify: Callable[[str], tuple]             # raw HTTP response -> (verified, pop/colo)
    http_path: str = "/"
    extra_ports: List[int] = field(default_factory=list)
    samples_per_cidr: int = 50
    concurrency: int = 150
    seeds: Optional[Callable[[list], List[str]]] = None   # candidate IPs from third-party lists
    flag: str = "🌐"
    country: str = "CDN"
    city: str = "Anycast Edge"


# ---------------------------------------------------------------- helpers
def http_get_text(url, timeout=30):
    req = Request(url, headers={"User-Agent": "dops-scanner/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def http_get_json(url, timeout=30):
    return json.loads(http_get_text(url, timeout))


def valid_cidrs(lines):
    out = []
    for line in lines:
        line = str(line).strip()
        if not line or line.startswith("#"):
            continue
        try:
            n = ipaddress.ip_network(line, strict=False)
        except ValueError:
            continue
        if n.version == 4 and n.prefixlen >= 8:
            out.append(str(n))
    return out


def sample_ips(cidr, k):
    net = ipaddress.ip_network(cidr, strict=False)
    if net.num_addresses < 4:
        return []
    first, last = int(net.network_address) + 1, int(net.broadcast_address) - 1
    if last - first + 1 <= k:
        return [str(ipaddress.IPv4Address(x)) for x in range(first, last + 1)]
    return [str(ipaddress.IPv4Address(x)) for x in random.sample(range(first, last + 1), k)]


def _atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------- state / sampling
def state_path(p):
    return os.path.join(OUTPUT_DIR, f"scan_state_{p.key}.json")


def load_state(p):
    path = state_path(p)
    legacy = os.path.join(OUTPUT_DIR, "scan_state.json")      # written by the older standalone start.py
    if not os.path.exists(path) and p.key == "cloudflare" and os.path.exists(legacy):
        path = legacy
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = {}
    cut = time.time() - STATE_DAYS * 86400
    blocks = s.get("blocks") if isinstance(s.get("blocks"), dict) else {}
    s["blocks"] = {b: v for b, v in blocks.items() if isinstance(v, dict) and v.get("t", 0) >= cut}
    s["last_alive"] = s.get("last_alive") if isinstance(s.get("last_alive"), list) else []
    s["tg_at"] = s.get("tg_at", 0) if isinstance(s.get("tg_at", 0), (int, float)) else 0
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


def build_targets(p, cidrs, state, seeds):
    nets = [ipaddress.ip_network(c, strict=False) for c in cidrs]
    inside = lambda ip: any(ipaddress.ip_address(ip) in n for n in nets)
    targets = set()
    for c in cidrs:
        targets.update(sample_ips(c, p.samples_per_cidr))
    hot = [(b, v) for b, v in state["blocks"].items() if v.get("h", 0) > 0 and inside(b + ".1")]
    if hot:  # exploit blocks that were healthy before (smoothed weight)
        w = [(v["h"] + 1) / (v["p"] + 3) for _, v in hot]
        for b in random.choices([b for b, _ in hot], weights=w, k=HOT_SAMPLES):
            targets.add(f"{b}.{random.randint(1, 254)}")
    targets.update(ip for ip in state["last_alive"] if inside(ip))      # re-verify previous winners
    for ip in seeds:                                                     # third-party candidates (+ their /24 neighbours)
        if inside(ip):
            targets.add(ip)
            b = ip.rsplit(".", 1)[0]
            targets.update(f"{b}.{random.randint(1, 254)}" for _ in range(SEED_BLOCK_SAMPLES))
    return sorted(targets)


# ---------------------------------------------------------------- probing
def _kind(e):
    if isinstance(e, ConnectionResetError):
        return "rst"        # reset mid-handshake (DPI-injection signature when scanned from inside a filtered network)
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


async def tls_probe(ip, port, p, http=False):
    t0 = time.perf_counter()
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port, ssl=_CTX, server_hostname=p.test_host), TIMEOUT)
    except Exception as e:
        return {"ok": False, "err": _kind(e)}
    res = {"ok": True, "ms": (time.perf_counter() - t0) * 1000, "status": 0, "verified": False, "pop": ""}
    if http:
        try:
            w.write(f"GET {p.http_path} HTTP/1.1\r\nHost: {p.test_host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n".encode())
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
            res["verified"], res["pop"] = p.verify(head)
        except Exception:
            pass
    await _close(w)
    return res


async def scan_ip(ip, p):
    first = await tls_probe(ip, p.port, p, http=True)
    if not first["ok"]:
        return {"ip": ip, "ok": False, "err": first["err"]}
    tls, fails = [first["ms"]], 0
    for _ in range(ROUNDS - 1):
        r = await tls_probe(ip, p.port, p)
        if r["ok"]:
            tls.append(r["ms"])
        else:
            fails += 1
    if len(tls) < math.ceil(ROUNDS / 2):
        return {"ip": ip, "ok": False, "err": "unstable"}
    rtt = await tcp_rtt(ip, p.port)
    conn, jitter, loss = median(tls), max(tls) - min(tls), round(fails / ROUNDS * 100)
    return {"ip": ip, "ok": True, "ping_ms": round(rtt if rtt is not None else conn, 1), "connect_ms": round(conn, 1),
            "jitter_ms": round(jitter, 1), "loss": loss, "colo": first["pop"], "status": first["status"],
            "verified": first["verified"], "ports": [p.port], "score": conn + jitter * 0.5 + loss * 4}


async def add_ports(top, p, sem):
    async def one(r, port):
        async with sem:
            if (await tls_probe(r["ip"], port, p))["ok"]:
                r["ports"].append(port)
    await asyncio.gather(*[one(r, port) for r in top for port in p.extra_ports])
    for r in top:
        r["ports"].sort()


def last_scan_age_min(p):
    """Minutes since the last published scan of this profile (None if unknown)."""
    try:
        with open(os.path.join(OUTPUT_DIR, p.out_name + ".json"), encoding="utf-8") as f:
            t = datetime.fromisoformat(json.load(f)["scanned_at"])
        return (datetime.now(timezone.utc) - t).total_seconds() / 60
    except Exception:
        return None


# ---------------------------------------------------------------- output / telegram
def write_outputs(p, pool, meta):
    lines = "".join(f"{r['ip']} ping={r['ping_ms']}ms connect={r['connect_ms']}ms jitter={r['jitter_ms']}ms "
                    f"colo={r['colo'] or '-'} ports={','.join(map(str, r['ports']))}\n" for r in pool)
    txt = os.path.join(OUTPUT_DIR, p.out_name + ".txt")
    _atomic(txt, lines)
    keys = ("ip", "ping_ms", "connect_ms", "jitter_ms", "loss", "colo", "ports", "verified")
    _atomic(os.path.join(OUTPUT_DIR, p.out_name + ".json"),
            json.dumps({**meta, "ips": [{k: r[k] for k in keys} for r in pool]}, ensure_ascii=False, indent=1))
    return txt


def telegram_due(state):
    return TG_FORCE or time.time() - state.get("tg_at", 0) >= TG_INTERVAL_MIN * 60


def send_telegram(p, pool, txt):
    best = pool[0]
    cap = format_config_remark(flag=p.flag, country=p.country, city=p.city, ping=str(int(best["ping_ms"])),
                               feature=f"تعداد: {len(pool)} آی‌پی سالم")
    top = "\n".join(f"🔹 <code>{x['ip']}</code> (⚡ {int(x['ping_ms'])}ms · پورت‌ها: {','.join(map(str, x['ports']))})" for x in pool[:5])
    note = "\n\nℹ️ این تست از سرور گیت‌هاب (خارج ایران) انجام شده؛ برای نتیجهٔ دقیق روی اینترنت خودتان از اسکنر وب استفاده کنید." \
        if SHOW_VANTAGE_NOTE and os.environ.get("GITHUB_ACTIONS") else ""
    ok = send_telegram_file(txt, caption=f"{cap}\n\n👑 <b>۵ آی‌پی برتر (کلیک روی آی‌پی = کپی):</b>\n{top}\n\n"
                                         f"📁 لیست کامل {len(pool)} آی‌پی در فایل بالا قرار دارد.{note}")
    return ok is not False      # older sender.py returned None -> treat as sent


async def run_profile(p):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if MIN_GAP_MIN > 0:
        age = last_scan_age_min(p)
        if age is not None and age < MIN_GAP_MIN:
            print(f"⏭️ {p.key}: last scan was {age:.0f} min ago (< {MIN_GAP_MIN}); skipping this scheduled slot")
            return 0
    state, cidrs = load_state(p), p.fetch_ranges()
    seeds = []
    if p.seeds:
        try:
            seeds = p.seeds([ipaddress.ip_network(c, strict=False) for c in cidrs])
        except Exception as e:
            print(f"⚠️ seed list unavailable ({e})")
    targets = build_targets(p, cidrs, state, seeds)
    print(f"📡 {p.key}: {len(targets)} IPs to scan (port {p.port}, {ROUNDS} rounds, {len(seeds)} seeds)")
    sem = asyncio.Semaphore(p.concurrency)

    async def worker(ip):
        async with sem:
            return await scan_ip(ip, p)

    results = await asyncio.gather(*[worker(ip) for ip in targets])
    alive = [r for r in results if r["ok"]]
    fails = Counter(r["err"] for r in results if not r["ok"])
    verified = [r for r in alive if r["verified"]]
    pool = verified or alive
    if not verified and alive:
        print("⚠️ HTTP verification matched no IP; falling back to TLS-only results")
    if len(pool) < MIN_ALIVE:
        print(f"❌ only {len(pool)} usable IPs (< {MIN_ALIVE}); keeping previous lists. Failures: {dict(fails)}")
        return 1
    pool.sort(key=lambda r: r["score"])
    await add_ports(pool[:PORT_CHECK_TOP], p, sem)
    learn(state, targets, [r["ip"] for r in pool])
    meta = {"scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "vantage": "github-actions" if os.environ.get("GITHUB_ACTIONS") else "local",
            "port": p.port, "tested": len(targets), "alive": len(alive), "verified": len(verified),
            "seeds": len(seeds), "failures": dict(fails)}
    txt = write_outputs(p, pool, meta)
    print(f"\n✅ {p.key} scan done: {len(pool)} usable ({len(verified)} verified). Failures: {dict(fails)}")
    if telegram_due(state):
        if send_telegram(p, pool, txt):
            state["tg_at"] = time.time()
    else:
        print(f"⏭️ Telegram skipped (next send in ≈{int(TG_INTERVAL_MIN - (time.time() - state['tg_at']) / 60)} min)")
    _atomic(state_path(p), json.dumps(state, ensure_ascii=False))
    return 0
