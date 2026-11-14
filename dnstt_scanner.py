#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""DNSTT resolver tester (stdlib only). Run it on the network you will tunnel from (e.g. phone/Termux inside Iran).

  python dnstt_scanner.py                       # basic reachability + validity test
  python dnstt_scanner.py --domain t.example.com  # also sends a TXT query for YOUR tunnel domain (what dnstt really needs)
  python dnstt_scanner.py --extra 1.2.3.4,5.6.7.8 # add your own resolvers

A resolver is reported "ok" only if it answers with a valid DNS response (matching transaction id, QR bit set,
NOERROR/NXDOMAIN). It also reports EDNS support (dnstt works best with large UDP payloads).
"""
import argparse, os, random, socket, struct, sys, time
from concurrent.futures import ThreadPoolExecutor

# (name, ip). Names describe the operator of the address itself; private 10.202.x.x resolvers only work inside Iran.
RESOLVERS = [
    ("رادار گیم ۱", "10.202.10.10"), ("رادار گیم ۲", "10.202.10.11"), ("سرویس ۴۰۳", "10.202.10.202"),
    ("بگذر ۱", "185.55.226.26"), ("بگذر ۲", "185.55.225.25"),
    ("شکن ۱", "178.22.122.100"), ("شکن ۲", "185.51.200.2"), ("الکترو", "78.157.42.100"),
    ("Google DNS ۱", "8.8.8.8"), ("Google DNS ۲", "8.8.4.4"), ("Cloudflare DNS", "1.1.1.1"),
    ("Quad9", "9.9.9.9"), ("OpenDNS", "208.67.222.222"), ("Level3", "4.2.2.4"),
]
QTYPE = {"A": 1, "NS": 2, "TXT": 16}


def build_query(domain, qtype="A", edns=True):
    """Return (txid, packet). EDNS0 OPT record advertises a 1232-byte UDP payload."""
    txid = random.randint(0, 0xFFFF)
    flags = 0x0100                                    # standard query, recursion desired
    arcount = 1 if edns else 0
    pkt = struct.pack(">HHHHHH", txid, flags, 1, 0, 0, arcount)
    for label in domain.strip(".").split("."):
        b = label.encode("idna") if not label.isascii() else label.encode()
        if not 0 < len(b) < 64:
            raise ValueError(f"bad label in {domain!r}")
        pkt += bytes([len(b)]) + b
    pkt += b"\x00" + struct.pack(">HH", QTYPE[qtype], 1)
    if edns:
        pkt += b"\x00" + struct.pack(">HHIH", 41, 1232, 0, 0)   # root name, TYPE OPT, class=payload size, ttl=0, rdlen=0
    return txid, pkt


def parse_response(data, txid):
    """-> (valid, rcode, truncated). Rejects short packets, wrong txid and non-responses."""
    if len(data) < 12:
        return False, -1, False
    rid, flags = struct.unpack(">HH", data[:4])
    if rid != txid or not flags & 0x8000:
        return False, -1, False
    return True, flags & 0x000F, bool(flags & 0x0200)


def query(ip, domain, qtype="A", edns=True, timeout=1.5, port=53):
    txid, pkt = build_query(domain, qtype, edns)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    t0 = time.perf_counter()
    try:
        s.sendto(pkt, (ip, port))
        data, _ = s.recvfrom(4096)
    except Exception:
        return None
    finally:
        s.close()
    ok, rcode, tc = parse_response(data, txid)
    return {"ok": ok, "rcode": rcode, "tc": tc, "ms": round((time.perf_counter() - t0) * 1000, 1), "size": len(data)} if ok else None


def test_resolver(name, ip, tunnel_domain=None, port=53):
    base = query(ip, "www.google.com", "A", edns=False, port=port)
    if not base or base["rcode"] not in (0, 3):
        return {"name": name, "ip": ip, "ok": False}
    ed = query(ip, "www.google.com", "A", edns=True, port=port)
    r = {"name": name, "ip": ip, "ok": True, "ms": base["ms"], "edns": bool(ed and ed["rcode"] not in (1, 4)), "tunnel": None}
    if tunnel_domain:
        tq = query(ip, tunnel_domain, "TXT", edns=True, timeout=2.5, port=port)
        r["tunnel"] = bool(tq and tq["rcode"] in (0, 3) and not tq["tc"])
    return r


def scan(resolvers, tunnel_domain=None, port=53, workers=12):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(lambda x: test_resolver(x[0], x[1], tunnel_domain, port), resolvers))
    return sorted(res, key=lambda r: (not r["ok"], not (r.get("tunnel") or False), r.get("ms", 9e9)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="DNSTT resolver tester")
    ap.add_argument("--domain", default=os.environ.get("DNSTT_DOMAIN", ""), help="your dnstt tunnel domain (TXT query test)")
    ap.add_argument("--extra", default="", help="comma-separated extra resolver IPs")
    a = ap.parse_args(argv)
    resolvers = list(RESOLVERS) + [(f"custom {ip}", ip) for ip in a.extra.split(",") if ip.strip()]
    print("\n🔍 تست ریزالورها برای تونل DNSTT (روی همین اینترنت)...\n" + "=" * 56)
    res = scan(resolvers, a.domain or None)
    alive = [r for r in res if r["ok"]]
    for r in res:
        if r["ok"]:
            extra = "" if r["tunnel"] is None else (" | دامنهٔ تونل ✅" if r["tunnel"] else " | دامنهٔ تونل ❌")
            print(f" ✅ {r['name']:<16} {r['ip']:<16} ⚡ {r['ms']}ms | EDNS {'✅' if r['edns'] else '❌'}{extra}")
        else:
            print(f" ❌ {r['name']:<16} {r['ip']:<16} بدون پاسخ معتبر")
    print("=" * 56)
    if not alive:
        print("⚠️ هیچ ریزالور معتبری پیدا نشد.")
        return 1
    best = alive[0]
    print(f"\n🏆 بهترین: {best['name']} ({best['ip']})")
    print("نکته: پاسخ معتبر یعنی ریزالور DNS می‌دهد؛ برای تونل، گزینهٔ --domain با دامنهٔ خودتان را هم اجرا کنید.")
    print(f"\nدستور نمونه:\ndnstt-client -udp {best['ip']}:53 -pubkey-file server.pub <دامنه-شما> 127.0.0.1:7000\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
