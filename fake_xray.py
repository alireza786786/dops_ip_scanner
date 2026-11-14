#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""A stand-in for the xray binary, used only by tests. Behaviour is driven by environment variables:
  FAKE_GOOD_IPS=ip,ip   outbound addresses that "work" (others are refused)
  FAKE_SLOW_IPS=ip:ms   extra delay before answering
  FAKE_TARGET=host:port every CONNECT is forwarded here (the test's local HTTP server)
  FAKE_REJECT_TEST=1    make `-test` fail (simulates a schema mismatch)
"""
import json, os, socket, struct, sys, threading, time
args = sys.argv[1:]
if "-config" not in args:
    sys.exit(2)
cfg = json.load(open(args[args.index("-config") + 1]))
def structure_ok(c):
    try:
        o = c["outbounds"][0]; i = c["inbounds"][0]; ok = i["protocol"] == "socks" and isinstance(i["port"], int) and "streamSettings" in o and o["protocol"] in ("vless", "vmess", "trojan")
        addr = (o["settings"].get("vnext") or o["settings"].get("servers"))[0]["address"]; return ok and bool(addr)
    except Exception:
        return False
if "-test" in args:
    if os.environ.get("FAKE_REJECT_TEST"):
        sys.stderr.write("fake_xray: rejected for test (FAKE_REJECT_TEST)\n"); sys.exit(1)
    if not structure_ok(cfg):
        sys.stderr.write("fake_xray: invalid config structure\n"); sys.exit(1)
    sys.exit(0)
if not structure_ok(cfg):
    sys.stderr.write("config invalid\n"); sys.exit(1)
o = cfg["outbounds"][0]; addr = (o["settings"].get("vnext") or o["settings"].get("servers"))[0]["address"]
good = set(filter(None, os.environ.get("FAKE_GOOD_IPS", "").split(","))); slow = dict(x.split(":") for x in filter(None, os.environ.get("FAKE_SLOW_IPS", "").split(",")))
th, tp = os.environ["FAKE_TARGET"].rsplit(":", 1)
def pump(a, b):
    try:
        while True:
            d = a.recv(4096)
            if not d: break
            b.sendall(d)
    except OSError: pass
    finally:
        try: b.shutdown(socket.SHUT_WR)
        except OSError: pass
def handle(c):
    try:
        c.recv(3); c.sendall(b"\x05\x00"); h = c.recv(4); n = c.recv(1)[0]; c.recv(n + 2)
        if addr not in good:
            c.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00"); c.close(); return
        time.sleep(int(slow.get(addr, 0)) / 1000)
        up = socket.create_connection((th, int(tp))); c.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        threading.Thread(target=pump, args=(c, up), daemon=True).start(); pump(up, c)
    except Exception: pass
    finally: c.close()
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", cfg["inbounds"][0]["port"])); srv.listen(16)
while True:
    cl, _ = srv.accept(); threading.Thread(target=handle, args=(cl,), daemon=True).start()
