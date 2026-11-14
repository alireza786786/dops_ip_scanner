#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""Cloudflare clean-IP scanner. Engine lives in scanlib.py."""
import asyncio, ipaddress, os, re, sys
import scanlib as sl

CLOUDFLARE_IPV4_URL = "https://www.cloudflare.com/ips-v4"
# community list tested from CHINESE carriers (CM/CT/CU): used only as unverified candidates/seeds
CF2DNS_URL = "https://raw.githubusercontent.com/ircfspace/cf2dns/refs/heads/master/list/ipv4.json"
FALLBACK_RANGES = ["173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
                   "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
                   "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22"]


def fetch_ranges():
    try:
        got = sl.valid_cidrs(sl.http_get_text(CLOUDFLARE_IPV4_URL).splitlines())
        if len(got) >= 5:
            return got
    except Exception as e:
        print(f"⚠️ official range list unavailable ({e}); using the built-in list")
    return list(FALLBACK_RANGES)


def cf2dns_seeds(nets):
    """IPv4 addresses from the cf2dns list, kept only if they sit inside Cloudflare's published ranges."""
    out = set()
    for row in sl.http_get_json(CF2DNS_URL, timeout=20):
        ip = row.get("ip") if isinstance(row, dict) else None
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.version == 4 and any(a in n for n in nets):
            out.add(str(a))
    return sorted(out)


def verify(head):
    m = re.search(r"^colo=(\w+)", head, re.M)      # body of /cdn-cgi/trace
    return (bool(m), m.group(1) if m else "")


PROFILE = sl.Profile(
    key="cloudflare", out_name="alive_cloudflare",
    test_host=os.environ.get("TEST_HOST", "cloudflare.com"), port=int(os.environ.get("SCAN_PORT", "443")),
    fetch_ranges=fetch_ranges, verify=verify, http_path="/cdn-cgi/trace",
    extra_ports=[2053, 2083, 2087, 2096, 8443],
    samples_per_cidr=int(os.environ.get("SAMPLES_PER_CIDR", "50")), concurrency=int(os.environ.get("CONCURRENCY", "150")),
    seeds=cf2dns_seeds, flag="☁️", country="Cloudflare", city="Anycast CDN")

if __name__ == "__main__":
    sys.exit(asyncio.run(sl.run_profile(PROFILE)))
