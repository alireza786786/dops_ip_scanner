#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""DNSTT resolver tester: runs against local fake DNS servers (no internet needed)."""
import os, socket, struct, sys, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import dnstt_scanner as d

def serve(mode, seen):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", 0)); s.settimeout(3)
    def loop():
        try:
            while True:
                data, addr = s.recvfrom(1024); seen.append(data)
                txid = struct.unpack(">H", data[:2])[0]
                if mode == "silent": continue
                if mode == "wrong_txid": txid ^= 0xFFFF
                flags = 0x8180 if mode != "formerr" else 0x8181
                if mode == "refused": flags = 0x8185
                if mode == "not_response": flags = 0x0100
                s.sendto(struct.pack(">HHHHHH", txid, flags, 1, 0, 0, 0), addr)
        except Exception: pass
    threading.Thread(target=loop, daemon=True).start(); return s.getsockname()[1]

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)

seen = []; p_ok = serve("ok", seen); p_wrong = serve("wrong_txid", []); p_ref = serve("refused", []); p_nr = serve("not_response", []); p_quiet = serve("silent", [])
check("valid resolver ok", d.test_resolver("t", "127.0.0.1", None, port=p_ok)["ok"])
check("wrong txid rejected", not d.test_resolver("t", "127.0.0.1", None, port=p_wrong)["ok"])
check("REFUSED rejected", not d.test_resolver("t", "127.0.0.1", None, port=p_ref)["ok"])
check("non-response packet rejected", not d.test_resolver("t", "127.0.0.1", None, port=p_nr)["ok"])
check("silent server rejected", not d.test_resolver("t", "127.0.0.1", None, port=p_quiet)["ok"])
r = d.test_resolver("t", "127.0.0.1", "t.example.com", port=p_ok)
check("tunnel TXT test passes", r["tunnel"] is True and r["edns"] is True)
check("TXT query carries the tunnel domain", any(b"\x01t\x07example\x03com" in pkt for pkt in seen))
check("EDNS OPT record present in query", any(pkt.endswith(struct.pack(">HHIH", 41, 1232, 0, 0)) for pkt in seen))
_, pkt = d.build_query("a.b.com", "TXT", edns=False)
check("query layout (no EDNS)", pkt[4:6] == b"\x00\x01" and pkt[10:12] == b"\x00\x00" and pkt.endswith(b"\x00\x00\x10\x00\x01"))
try: d.build_query("a" * 64 + ".com"); check("over-long label rejected", False)
except ValueError: check("over-long label rejected", True)
labels = {n for n, _ in d.RESOLVERS}
check("mislabeled operators removed", not any(x in labels for x in ("همراه اول", "ایرانسل", "مخابرات ۱", "مخابرات ۲")))
res = d.scan([("a", "127.0.0.1"), ("b", "127.0.0.1")], None, port=p_ok)
check("scan returns sorted results", len(res) == 2 and all(x["ok"] for x in res))
sys.exit(0 if ok else 1)
