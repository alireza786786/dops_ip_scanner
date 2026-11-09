#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""Fastly clean-IP scanner. Engine lives in scanlib.py."""
import asyncio, os, re, sys
import scanlib as sl

FASTLY_IP_LIST_URL = "https://api.fastly.com/public-ip-list"
FALLBACK_RANGES = ["151.101.0.0/16", "199.232.0.0/16", "146.75.0.0/17", "140.248.64.0/18"]


def fetch_ranges():
    try:
        got = sl.valid_cidrs(sl.http_get_json(FASTLY_IP_LIST_URL).get("addresses", []))
        if len(got) >= 3:
            return got
    except Exception as e:
        print(f"⚠️ Fastly range list unavailable ({e}); using the built-in list")
    return list(FALLBACK_RANGES)


def verify(head):
    """Fastly edges add x-served-by (cache-<pop>-...) / x-timer headers. Header names are from memory:
    if none matches, the engine falls back to TLS-only results instead of publishing nothing."""
    h = head.lower()
    m = re.search(r"^x-served-by:\s*([^\r\n]+)", h, re.M)
    pop = m.group(1).split(",")[-1].strip().split("-")[-1].upper() if m else ""
    return (bool(m) or "x-timer:" in h or "fastly" in h, pop)


PROFILE = sl.Profile(
    key="fastly", out_name="alive_fastly",
    test_host=os.environ.get("FASTLY_TEST_HOST", "www.github.com"), port=443,
    fetch_ranges=fetch_ranges, verify=verify, http_path="/",
    samples_per_cidr=int(os.environ.get("SAMPLES_PER_CIDR", "60")), concurrency=int(os.environ.get("CONCURRENCY", "150")),
    flag="⚡", country="Fastly CDN", city="Global Edge")

if __name__ == "__main__":
    sys.exit(asyncio.run(sl.run_profile(PROFILE)))
