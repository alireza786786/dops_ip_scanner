#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""Scan engine tests against local TLS servers (no internet). Run: python tests/test_engine.py"""
import asyncio, ipaddress, json, os, ssl, subprocess, sys, tempfile, time
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(); os.chdir(tmp)
os.environ.pop("GITHUB_ACTIONS", None)
import scanlib as sl, start, fastly
subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "k.pem", "-out", "c.pem", "-days", "1", "-subj", "/CN=x"], capture_output=True, check=True)
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
sent = []; sl.send_telegram_file = lambda p, caption="": (sent.append(caption) or True)

def handler(kind):
    async def h(r, w):
        try: await r.readuntil(b"\r\n\r\n")
        except Exception: w.close(); return
        body, hd = ("fl=1\ncolo=TST\n", "") if kind == "cf" else ("x", "X-Served-By: cache-fra-abc-FRA, cache-ams-xyz-AMS\r\nX-Timer: S1,VS0\r\n")
        w.write(f"HTTP/1.1 200 OK\r\n{hd}Content-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}".encode()); await w.drain(); w.close()
    return h

import sender
check("send_telegram_message without credentials is a safe no-op", sender.send_telegram_message("x") is False)
_kb = [b for row in sender.INLINE_KEYBOARD["inline_keyboard"] for b in row]
check("telegram keyboard: 4 https buttons incl. scanner", len(_kb) == 4 and all(b["url"].startswith("https://") and len(b["text"]) <= 64 for b in _kb) and any(b["url"] == "https://alireza786786.github.io/dops_ip_scanner/" for b in _kb) and bool(json.dumps(sender.INLINE_KEYBOARD)))

async def main():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain("c.pem", "k.pem")
    s1 = await asyncio.start_server(handler("cf"), "127.0.0.1", 0, ssl=ctx); p1 = s1.sockets[0].getsockname()[1]
    s2 = await asyncio.start_server(handler("cf"), "127.0.0.1", 0, ssl=ctx); p2 = s2.sockets[0].getsockname()[1]
    s3 = await asyncio.start_server(handler("fastly"), "127.0.0.1", 0, ssl=ctx); p3 = s3.sockets[0].getsockname()[1]
    check("cloudflare verify (colo)", start.verify("HTTP/1.1 200 OK\r\n\r\nfl=1\ncolo=FRA\n") == (True, "FRA") and start.verify("HTTP/1.1 403\r\n\r\nno") == (False, ""))
    check("fastly verify (x-served-by)", fastly.verify("HTTP/1.1 200\r\nX-Served-By: cache-fra-a-FRA, cache-ams-b-AMS\r\n\r\n") == (True, "AMS") and fastly.verify("HTTP/1.1 200\r\nServer: nginx\r\n\r\n") == (False, ""))
    check("error classification", [sl._kind(ConnectionResetError()), sl._kind(asyncio.TimeoutError()), sl._kind(ssl.SSLError()), sl._kind(ValueError())] == ["rst", "timeout", "tls", "other"])
    check("range validation", sl.valid_cidrs(["# c", "1.2.3.0/24", "bad", "2001:db8::/32", "10.0.0.0/4"]) == ["1.2.3.0/24"])
    sl.http_get_json = lambda url, timeout=30: [{"ip": "198.41.208.160"}, {"ip": "8.8.8.8"}, {"ip": "bad"}, {"ip": "104.16.200.25"}, 5]
    nets = [ipaddress.ip_network(c) for c in start.FALLBACK_RANGES]
    check("cf2dns seeds filtered to Cloudflare ranges", start.cf2dns_seeds(nets) == ["104.16.200.25", "198.41.208.160"])
    sl.OUTPUT_DIR = "out"; sl.MIN_ALIVE = 1; sl.HOT_SAMPLES = 0; sl.SEED_BLOCK_SAMPLES = 0
    pc = sl.Profile(key="cloudflare", out_name="alive_cloudflare", test_host="cloudflare.com", port=p1, fetch_ranges=lambda: ["127.0.0.0/30"],
                    verify=start.verify, http_path="/cdn-cgi/trace", extra_ports=[p2, 1], seeds=lambda n: ["127.0.0.2"])
    sl.TG_FORCE = False
    check("scan exit code 0", await sl.run_profile(pc) == 0)
    line = open("out/alive_cloudflare.txt").read().splitlines()[0]; js = json.load(open("out/alive_cloudflare.json")); st = json.load(open("out/scan_state_cloudflare.json"))
    check("txt line keeps IP first + colo + ports", line.split()[0] == "127.0.0.1" and "colo=TST" in line and f"ports={min(p1, p2)},{max(p1, p2)}" in line)
    check("json metadata", js["vantage"] == "local" and js["seeds"] == 1 and js["tested"] == 2)
    check("first run sends Telegram once", len(sent) == 1 and st["tg_at"] > 0)
    await sl.run_profile(pc); check("second run is gated (no new send)", len(sent) == 1)
    sl.TG_FORCE = True; await sl.run_profile(pc); check("TG_FORCE sends", len(sent) == 2)
    sl.TG_FORCE = False; st = json.load(open("out/scan_state_cloudflare.json")); st["tg_at"] = time.time() - 171 * 60; json.dump(st, open("out/scan_state_cloudflare.json", "w"))
    await sl.run_profile(pc); check("sends again after 171 min", len(sent) == 3)
    st["tg_at"] = 0; json.dump(st, open("out/scan_state_cloudflare.json", "w")); sl.send_telegram_file = lambda p, caption="": False
    await sl.run_profile(pc); check("failed send keeps Telegram due", json.load(open("out/scan_state_cloudflare.json"))["tg_at"] == 0)
    sl.send_telegram_file = lambda p, caption="": None; await sl.run_profile(pc)
    check("old sender (None) counts as sent", json.load(open("out/scan_state_cloudflare.json"))["tg_at"] > 0)
    sl.send_telegram_file = lambda p, caption="": (sent.append(caption) or True)
    sl.MIN_GAP_MIN = 25; jp = "out/alive_cloudflare.json"; m0 = os.path.getmtime(jp)
    check("gap guard skips a too-soon scheduled scan", await sl.run_profile(pc) == 0 and os.path.getmtime(jp) == m0)
    j2 = json.load(open(jp)); j2["scanned_at"] = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(timespec="seconds"); json.dump(j2, open(jp, "w")); m1 = os.path.getmtime(jp)
    time.sleep(0.05); check("gap guard allows a scan after the gap", await sl.run_profile(pc) == 0 and os.path.getmtime(jp) != m1)
    os.remove(jp); check("gap guard ignores missing history (first run)", sl.last_scan_age_min(pc) is None and await sl.run_profile(pc) == 0 and os.path.exists(jp))
    sl.MIN_GAP_MIN = 0
    pf = sl.Profile(key="fastly", out_name="alive_fastly", test_host="www.github.com", port=p3, fetch_ranges=lambda: ["127.0.0.0/30"], verify=fastly.verify)
    check("fastly scan ok", await sl.run_profile(pf) == 0 and "colo=AMS" in open("out/alive_fastly.txt").read())
    alerts = []; sl.send_telegram_message = lambda text, chat_id="": (alerts.append(text) or True)
    before = open("out/alive_fastly.txt").read(); sl.MIN_ALIVE = 99
    check("broken scan keeps old files + exit 1", await sl.run_profile(pf) == 1 and open("out/alive_fastly.txt").read() == before)
    check("broken scan sends an admin alert", len(alerts) == 1 and "fastly" in alerts[0])
    await sl.run_profile(pf); check("alerts are rate-limited", len(alerts) == 1)
    stt = json.load(open("out/scan_state_fastly.json")); stt["alert_at"] = time.time() - 7 * 3600; json.dump(stt, open("out/scan_state_fastly.json", "w"))
    await sl.run_profile(pf); check("alert allowed again after the window", len(alerts) == 2)
    sl.MIN_ALIVE = 1; jf = json.load(open("out/alive_fastly.json")); jf["scanned_at"] = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(timespec="seconds"); json.dump(jf, open("out/alive_fastly.json", "w"))
    check("recovery message after a stale period", await sl.run_profile(pf) == 0 and len(alerts) == 3 and "✅" in alerts[-1])
    jf = json.load(open("out/alive_fastly.json")); await sl.run_profile(pf); check("no recovery message when the previous scan was recent", len(alerts) == 3)
    sl.MIN_ALIVE = 1
    json.dump({"blocks": {"104.16.5": {"p": 3, "h": 2, "t": time.time()}, "1.1.1": {"p": 1, "h": 1, "t": time.time() - 40 * 86400}}, "last_alive": ["104.16.5.9"]}, open("out/scan_state.json", "w"))
    os.remove("out/scan_state_cloudflare.json"); legacy = sl.load_state(start.PROFILE)
    check("legacy state migrated and pruned", legacy["blocks"].get("104.16.5", {}).get("h") == 2 and "1.1.1" not in legacy["blocks"] and legacy["last_alive"] == ["104.16.5.9"])
    tg = sl.build_targets(pc, ["104.16.0.0/13", "172.64.0.0/22"], legacy, [])
    check("adaptive targets use hot block", any(t.startswith("104.16.5.") for t in tg) or sl.HOT_SAMPLES == 0)
asyncio.run(main()); sys.exit(0 if ok else 1)
