#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""UI details: header icon buttons (GitHub / theme / language), splash screen timeline, reduced motion, quick repeat-visit mode."""
import asyncio, os, sys
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); URL = "file://" + os.path.join(ROOT, "index.html")
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
SPL = "(() => { const e = document.getElementById('splash'); if (!e) return 'gone'; const c = getComputedStyle(e); return c.visibility === 'hidden' || +c.opacity === 0 ? 'hidden' : 'visible'; })()"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); errs = []
        ctx = await b.new_context(viewport={"width": 390, "height": 800}); pg = await ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL); await pg.wait_for_timeout(350)
        check("splash visible on open", await pg.evaluate(SPL) == "visible")
        anim = await pg.evaluate("[getComputedStyle(document.querySelector('.sp-orbit')).animationName, getComputedStyle(document.querySelector('.sp-m')).animationName]")
        check("globe is animated (orbit spins, meridians turn)", anim == ["sp-spin", "sp-m"])
        await pg.wait_for_timeout(2300)
        check("splash fades out within ~2.5 s", await pg.evaluate(SPL) in ("hidden", "gone"))
        await pg.wait_for_timeout(600); check("splash removed from DOM", await pg.evaluate("!document.getElementById('splash')"))
        check("page usable after splash", await pg.evaluate("typeof run === 'function' && !!document.getElementById('start')"))
        # header
        order = await pg.evaluate("[...document.querySelectorAll('.nav-actions > *')].map(e => e.id)")
        check("header order GitHub, theme, language", order == ["ghBtn", "themeToggle", "langToggle"])
        check("all three are SVG icon buttons", await pg.evaluate("[...document.querySelectorAll('.nav-actions .icon-btn')].every(e => !!e.querySelector('svg'))"))
        gh = await pg.evaluate("(() => { const a = document.getElementById('ghBtn'); return [a.href, a.target, a.rel, a.getAttribute('aria-label')]; })()")
        check("GitHub button opens the repo safely", gh[0] == "https://github.com/alireza786786/dops_ip_scanner" and gh[1] == "_blank" and "noopener" in gh[2] and gh[3] == "GitHub")
        ic0 = await pg.evaluate("document.getElementById('themeIcon').innerHTML"); await pg.evaluate("toggleTheme()"); ic1 = await pg.evaluate("document.getElementById('themeIcon').innerHTML")
        check("theme icon switches moon/sun", ic0 != ic1 and "circle" in ic1)
        b0 = await pg.evaluate("document.getElementById('langLabel').textContent"); await pg.evaluate("toggleLang()"); b1 = await pg.evaluate("document.getElementById('langLabel').textContent")
        check("language badge shows target language", (b0, b1) == ("EN", "FA"))
        boxes = await pg.evaluate("[...document.querySelectorAll('.nav-actions .icon-btn')].map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.width), Math.round(r.height)]; })")
        check("buttons are 40px squares in one row, left-to-right", all(w == 40 and h == 40 for _, w, h in boxes) and boxes[0][0] < boxes[1][0] < boxes[2][0])
        check("manual IP clear button label", await pg.evaluate("document.getElementById('clearManual').textContent.includes('پاک کردن اینها') || document.getElementById('clearManual').textContent.includes('Clear These')"))
        # repeat visit in the same session -> quick splash
        import time
        await pg.reload(wait_until="domcontentloaded"); t0 = time.time()
        q = await pg.evaluate("[document.documentElement.className, sessionStorage.getItem('dops-seen')]")
        check("quick mode on repeat visit", "quick" in q[0]); print("   debug:", q)
        while time.time() - t0 < 4 and await pg.evaluate(SPL) == "visible": await pg.wait_for_timeout(50)
        check("quick splash is gone in under ~1.8 s", time.time() - t0 < 1.8)
        check("local/file copy shows no unofficial warning", await pg.evaluate("document.getElementById('fakeWarn').hidden"))
        check("no page errors", not errs); await ctx.close()
        rm = await b.new_context(reduced_motion="reduce", viewport={"width": 390, "height": 800}); q = await rm.new_page(); await q.goto(URL); await q.wait_for_timeout(200)
        check("reduced motion: no spinning animation", await q.evaluate("getComputedStyle(document.querySelector('.sp-orbit')).animationName") == "none")
        html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        async def at(url):
            c = await b.new_context(viewport={"width": 390, "height": 800}); pp = await c.new_page()
            async def h(route):
                u = route.request.url
                await (route.fulfill(body=html, content_type="text/html") if u.endswith("/index.html") or u.endswith("/") else route.abort())
            await c.route("**/*", h); await pp.goto(url); await pp.wait_for_timeout(250)
            r = await pp.evaluate("({warn: !document.getElementById('fakeWarn').hidden, tok: document.getElementById('tgToken').disabled, rem: document.getElementById('remember').disabled, link: document.getElementById('fakeLink').href, txt: document.getElementById('fakeWarn').textContent.length > 30})")
            await c.close(); return r
        off = await at("https://alireza786786.github.io/dops_ip_scanner/")
        check("official address: no warning, token field enabled", not off["warn"] and not off["tok"] and not off["rem"])
        for bad in ("https://evil.example/index.html", "https://alireza786786.github.io.evil.com/dops_ip_scanner/", "https://someone-else.github.io/dops_ip_scanner/", "https://alireza786786.github.io/other/"):
            r2 = await at(bad)
            check("unofficial copy warns + disables token/remember: " + bad.split("/")[2], r2["warn"] and r2["tok"] and r2["rem"] and r2["txt"] and r2["link"] == "https://alireza786786.github.io/dops_ip_scanner/")
        await b.close()
asyncio.run(main()); sys.exit(0 if ok else 1)
