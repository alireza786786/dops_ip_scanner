#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""Browser regression tests for index.html (headless Chromium via Playwright). Run: python tests/test_web.py"""
import asyncio, os, sys
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "tests", "web_checks.js"), encoding="utf-8").read()
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + os.path.join(ROOT, "index.html")); await pg.wait_for_timeout(400)
        r = await pg.evaluate(JS); await b.close()
    check("no page errors", not errs)
    check("no exception in any section", not [k for k, v in r.items() if isinstance(v, str) and v.startswith("EXC")])
    rw = r["rewrite"]
    check("port extraction", rw["port"] == [2087, 8443, 0, 0])
    check("custom SNI overrides existing sni/host", "sni=my.dom.com" in rw["custom"] and "old.com" not in rw["custom"] and "host=my.dom.com" in rw["custom"])
    check("legacy ss + reality untouched, vmess add rewritten", rw["ssSame"] and rw["realSame"] and rw["vmAdd"] == "5.5.5.5")
    check("no SNI invented for IP-address config", "sni=" not in rw["ipHostCfg"])
    check("SNI kept only when 'keep' is on", "sni=sub.example.com" in r["sni_keep"]["keep"] and "sni=" not in r["sni_keep"]["noKeep"])
    check("custom/all-TLS ports + CIDR parsing", r["ports"] == [[2096, 8443], 6, ["162.159.20.0/24"]])
    check("every CDN source scans (50/50)", all(v == 50 for k, v in r["scan_each_source"].items() if k != "offline_db") and r["scan_each_source"]["offline_db"] > 0)
    check("smart sampling learns blocks for presets", r["smart_presets"]["blocks"] > 0 and r["smart_presets"]["hotNote"])
    check("quality text translates with language", r["lang_quality"]["qk"] == "qExcellent" and r["lang_quality"]["enRowHasEnglishQuality"])
    check("repo files read from data branch first", r["data_branch"]["dataFirst"] and r["data_branch"]["ips"] == ["104.16.1.1"])
    check("repo list age note", "1" in r["data_branch"]["note"] or "۱" in r["data_branch"]["note"])
    check("fallback to file next to page", r["fallback_relative"] == ["104.16.9.9"])
    check("fallback to offline bank", r["offline_bank_fallback"][0])
    check("cf2dns filtered to Cloudflare ranges + warning", r["cf2dns"]["ips"] == ["104.16.200.25", "198.41.208.160"] and r["cf2dns"]["warn"] == "block")
    check("CDN warnings (CF none, others shown)", r["warnings"] == {"cf_ranges": "none", "google": "block", "warp": "block", "cf2dns": "block", "offline_db": "none"})
    check("per-ISP history", r["history"] == [2, True])
    check("Clash YAML + unsupported skipped", r["clash"]["count"] == 2 and r["clash"]["skip"] == 1 and "proxies:" in r["clash"]["text"])
    check("copy modal + clear buttons", r["modal_clear"] == [True, 45, "", ""])
    check("remember saves/clears immediately", r["remember"] == [True, True])
    check("3 distinct subscription errors", r["sub_errors"] == 3)
    check("5 tutorial tabs", r["tabs"] == ["block"] * 5)
    check("theme + language persist", r["theme_lang"] == ["light", ["ltr", "en"], "rtl"])
    g = r["gh_clear"]
    check("GitHub button in header (safe external link)", g["href"] == "https://github.com/alireza786786/dops_ip_scanner" and g["target"] == "_blank" and "noopener" in g["rel"] and g["inNav"])
    check("manual IP clear button works", g["cleared"])
    check("i18n keys complete in both languages", all(not v for v in r["i18n_keys"].values()))
asyncio.run(main()); sys.exit(0 if ok else 1)
