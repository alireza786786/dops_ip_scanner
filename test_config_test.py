#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""config_test.py checked against a fake Xray + a local HTTP server (no network, no real Xray needed)."""
import http.server, json, os, sys, tempfile, threading, functools
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import config_test as c
ok = True
def check(name, cond, detail=None):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
    if not cond and detail is not None: print("   ", detail)

VLESS_WS = "vless://11111111-1111-1111-1111-111111111111@sub.example.com:443?type=ws&security=tls&sni=sub.example.com&path=%2Fws&fp=chrome#node"
VMESS_WS = "vmess://" + __import__("base64").b64encode(json.dumps({"v": "2", "ps": "n", "add": "x.example.com", "port": "443", "id": "2222", "net": "ws", "tls": "tls"}).encode()).decode()
TROJAN = "trojan://pw@t.example.com:443?security=tls&sni=t.example.com#tj"
REALITY = "vless://u@r.example.com:443?security=reality&type=tcp&pbk=x&sid=y#r"
PLAIN_TCP = "vless://11111111-1111-1111-1111-111111111111@t.example.com:443?type=tcp&encryption=none#tj"

check("parse vless/ws", c.parse_link(VLESS_WS)["sni"] == "sub.example.com" and c.parse_link(VLESS_WS)["net"] == "ws")
check("parse vmess (base64 JSON)", c.parse_link(VMESS_WS)["host"] == "x.example.com" and c.parse_link(VMESS_WS)["proto"] == "vmess")
check("parse trojan", c.parse_link(TROJAN)["proto"] == "trojan")
try: c.build_xray_config(c.parse_link(REALITY), "1.2.3.4", 1); check("Reality is refused (no CDN)", False)
except c.Unsupported: check("Reality is refused (no CDN)", True)
cfg = c.build_xray_config(c.parse_link(VLESS_WS), "104.16.1.1", 19080)
check("outbound address is the clean IP, SNI/Host stay the original domain", cfg["outbounds"][0]["settings"]["vnext"][0]["address"] == "104.16.1.1" and cfg["outbounds"][0]["streamSettings"]["tlsSettings"]["serverName"] == "sub.example.com" and cfg["outbounds"][0]["streamSettings"]["wsSettings"]["headers"]["Host"] == "sub.example.com")
cfg2 = c.build_xray_config(c.parse_link(PLAIN_TCP), "104.16.1.1", 19080)
check("plain tcp/no-tls config has no tlsSettings", cfg2["outbounds"][0]["streamSettings"]["security"] == "none" and "tlsSettings" not in cfg2["outbounds"][0]["streamSettings"])
try: c.parse_link("ss://abc@1.2.3.4:443#x"); check("unsupported scheme rejected", False)
except c.Unsupported: check("unsupported scheme rejected", True)

body = b"OK"
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(204); self.send_header("Content-Length", "0"); self.end_headers()
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
target_port = srv.server_address[1]

os.environ["FAKE_TARGET"] = f"127.0.0.1:{target_port}"
os.environ["FAKE_GOOD_IPS"] = "104.16.1.1,104.16.1.2"
fake_xray = [sys.executable, os.path.join(ROOT, "tests", "fake_xray.py")]
c._xray_cmds = lambda xray, cfg, test=False: (fake_xray + (["-test"] if test else []) + ["-config", cfg], fake_xray + (["-test"] if test else []) + ["-config", cfg])

info = c.parse_link(VLESS_WS)
r_ok = c.test_pair(fake_xray, info, "104.16.1.1", 19091, c.DEFAULT_URL, 5)
check("a reachable IP is reported ok with a real timing", r_ok["ok"] and isinstance(r_ok["ms"], float) and r_ok["ms"] > 0, r_ok)
r_bad = c.test_pair(fake_xray, info, "104.16.1.9", 19092, c.DEFAULT_URL, 5)
check("an unreachable IP is reported as failed, not a crash", not r_bad["ok"] and r_bad["error"], r_bad)
os.environ["FAKE_REJECT_TEST"] = "1"
good, msg = c.validate_with_xray(fake_xray, cfg)
check("xray -test rejection is surfaced, not silently ignored", not good and msg)
del os.environ["FAKE_REJECT_TEST"]
good2, _ = c.validate_with_xray(fake_xray, cfg)
check("a valid config passes xray -test", good2)

res = c.run_batch(fake_xray, [VLESS_WS, REALITY], ["104.16.1.1", "104.16.1.2", "104.16.1.9"], jobs=2, base_port=19100)
check("batch runs config x IP, unsupported links fail cleanly, results sorted best-first", len(res) == 6 and sum(r["ok"] for r in res) == 2 and res[0]["ok"] and res[1]["ok"] and not res[-1]["ok"] and sum("unsupported" in r["error"] for r in res) == 3)
with tempfile.TemporaryDirectory() as d:
    ipf = os.path.join(d, "ips.txt"); open(ipf, "w").write("104.16.1.1 ping=1ms\n104.16.1.2 ping=2ms\nnot-an-ip\n104.16.1.1 ping=1ms\n")
    class A: ips, ips_file, top = "", ipf, 0
    a = A(); a.ips = ""
    check("--ips-file: parses, dedupes, drops non-IP lines", c.load_ips(a) == ["104.16.1.1", "104.16.1.2"])
    a.top = 1; check("--top limits the count", c.load_ips(a) == ["104.16.1.1"])
outf = None
with tempfile.TemporaryDirectory() as d:
    outf = os.path.join(d, "out.json")
    rc = c.main(["--config", VLESS_WS, "--ips", "104.16.1.1,104.16.1.9", "--xray", fake_xray[1], "--base-port", "19110", "--out", outf, "--jobs", "1"])
    check("CLI exits 0 when at least one IP works, writes JSON", rc == 0 and os.path.exists(outf) and len(json.load(open(outf))["results"]) == 2)
    rc2 = c.main(["--config", VLESS_WS, "--ips", "104.16.1.9", "--xray", fake_xray[1], "--base-port", "19120", "--jobs", "1"])
    check("CLI exits 1 when nothing works", rc2 == 1)
rc3 = c.main(["--config", VLESS_WS, "--ips", "1.2.3.4", "--xray", "/no/such/xray-binary"])
check("missing xray binary -> clear exit 2, no crash", rc3 == 2)
sys.exit(0 if ok else 1)
