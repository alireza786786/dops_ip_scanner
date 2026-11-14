#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""PWA: manifest/icons valid, service worker registers over http://localhost, app loads offline, cross-origin is untouched."""
import asyncio, functools, http.server, json, os, struct, sys, threading
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
m = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
check("manifest fields", m["display"] == "standalone" and m["start_url"] == "./" and {i["src"] for i in m["icons"]} == {"icon-192.png", "icon-512.png", "icon-512-maskable.png"})
for i in m["icons"]:
    b = open(os.path.join(ROOT, i["src"]), "rb").read(); w, h = struct.unpack(">II", b[16:24]); n = int(i["sizes"].split("x")[0])
    check(f"{i['src']} is a {n}px PNG", b[:8] == b"\x89PNG\r\n\x1a\n" and (w, h) == (n, n))
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
check("index links exactly one manifest + icon", html.count('rel="manifest"') == 1 and 'href="manifest.json"' in html and html.count("theme-color") == 1 and "apple-touch-icon" in html and "serviceWorker.register('sw.js')" in html)
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
handler.log_message = lambda *a, **k: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(); pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(f"http://127.0.0.1:{port}/index.html"); await pg.wait_for_timeout(500)
        state = await pg.evaluate("navigator.serviceWorker.ready.then(r => r.active.state)")
        check("service worker active", state == "activated")
        cached = await pg.evaluate("caches.open('dops-v15-0').then(c => c.keys()).then(k => k.map(x => new URL(x.url).pathname))")
        check("app shell cached", {"/", "/index.html", "/manifest.json", "/icon-192.png", "/icon-512.png", "/icon-512-maskable.png"} <= set(cached))
        await pg.reload(); await pg.wait_for_timeout(300)
        await ctx.set_offline(True); await pg.reload(); await pg.wait_for_timeout(500)
        check("offline page is the scanner UI", await pg.evaluate("typeof run === 'function' && !!document.getElementById('start')"))
        await ctx.set_offline(False)
        keys = await pg.evaluate("caches.keys().then(ks => Promise.all(ks.map(k => caches.open(k).then(c => c.keys()).then(r => r.map(x => new URL(x.url).origin)))))")
        check("only same-origin entries cached", all(o == f"http://127.0.0.1:{port}" for ks in keys for o in ks))
        check("no page errors", not errs); await b.close()
asyncio.run(main()); sys.exit(0 if ok else 1)
