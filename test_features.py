#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""Quick mode, QR modal, freshness badge, operator opt-out, wipe-all, CSP (Chromium)."""
import asyncio, os, sys
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); URL = "file://" + os.path.join(ROOT, "index.html")
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
MOCK = """() => {
  window.__urls = []; window.__fake = (ageH) => async (u) => { window.__urls.push(u);
    if (u.includes('alive_cloudflare.json')) return ageH === null ? { ok: false } : { ok: true, json: async () => ({ scanned_at: new Date(Date.now() - ageH * 36e5).toISOString(), vantage: 'github-actions' }) };
    if (u.includes('alive_cloudflare.txt')) return { ok: true, text: async () => '104.16.1.1 ping=3ms\\n104.16.1.2 ping=4ms\\n172.64.9.9 ping=5ms\\n104.17.5.5 ping=5ms\\n' };
    throw new TypeError('offline'); };
  window.fetch = window.__fake(0.5);
  probeOnce = async (ip) => ({ ok: true, ms: ip.endsWith('.1') ? 30 : 80 });
}"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={"width": 390, "height": 800}); pg = await ctx.new_page()
        msgs, errs = [], []
        pg.on("console", lambda m: msgs.append(m.text) if m.type in ("error", "warning") else None); pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL); await pg.wait_for_timeout(300); await pg.evaluate(MOCK)
        # --- quick mode without configs
        before = await pg.evaluate("['src', 'limit', 'proto', 'samples', 'targetPort'].map(i => document.getElementById(i).value).join('|')")
        await pg.evaluate("document.getElementById('quickBtn').click()"); await pg.wait_for_timeout(2500)
        r = await pg.evaluate("({vis: !document.getElementById('quickOut').hidden, ip: document.getElementById('qIp').textContent, noCfg: !document.getElementById('qNoCfg').hidden, qr: document.getElementById('qQr').hidden, after: ['src', 'limit', 'proto', 'samples', 'targetPort'].map(i => document.getElementById(i).value).join('|'), busy: document.getElementById('quickBtn').disabled})")
        import re
        check("quick mode shows the best IP:port", r["vis"] and re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", r["ip"]) and r["ip"].startswith("104.16.1.1"))
        check("quick mode restores the user's settings", r["after"] == before and not r["busy"])
        check("no configs: hint shown, config buttons hidden", r["noCfg"] and r["qr"])
        used = await pg.evaluate("window.__urls.some(u => u.includes('/data/outputs/alive_cloudflare.txt'))")
        check("quick mode reads the repo list (data branch)", used)
        # --- quick mode with configs + QR modal
        await pg.evaluate("document.getElementById('cfgIn').value = 'vless://u@sub.example.com:443?type=ws&security=tls&path=%2Fws#a\\nvmess://' + b64e(JSON.stringify({v:2,ps:'b',add:'x.com',port:'443',id:'1',net:'ws',tls:'tls'}))")
        await pg.evaluate("document.getElementById('quickBtn').click()"); await pg.wait_for_timeout(2500)
        r = await pg.evaluate("({cfgBtn: !document.getElementById('qCopyCfg').hidden, qr: !document.getElementById('qQr').hidden, hint: document.getElementById('qNoCfg').hidden})")
        check("with configs: copy-configs + QR buttons shown", r["cfgBtn"] and r["qr"] and r["hint"])
        await pg.evaluate("document.getElementById('qQr').click()")
        m = await pg.evaluate("({open: !document.getElementById('qrModal').hidden, svg: !!document.querySelector('#qrBox svg path'), count: document.getElementById('qrCount').textContent})")
        check("QR modal opens with an SVG and counter 1 / 2", m["open"] and m["svg"] and m["count"] == "1 / 2")
        await pg.evaluate("document.getElementById('qrNext').click()"); c2 = await pg.evaluate("document.getElementById('qrCount').textContent")
        await pg.evaluate("document.getElementById('qrNext').click()"); c3 = await pg.evaluate("document.getElementById('qrCount').textContent")
        check("QR next/prev cycles", c2 == "2 / 2" and c3 == "1 / 2")
        await pg.evaluate("document.getElementById('qrClose').click()")
        check("QR modal closes", await pg.evaluate("document.getElementById('qrModal').hidden"))
        # --- freshness badge
        for age, cls in ((0.5, "ok"), (2, "warn"), (5, "bad"), (None, "bad")):
            await pg.evaluate("a => { window.fetch = window.__fake(a); }", age); await pg.evaluate("loadRepoAge()"); await pg.wait_for_timeout(100)
            got = await pg.evaluate("({c: document.getElementById('repoAge').className, t: document.getElementById('repoAge').textContent, h: document.getElementById('repoAge').hidden})")
            check(f"repo age badge: {age} h -> {cls}", cls in got["c"] and not got["h"] and (cls != "bad" or len(got["t"]) > 10))
        # --- operator opt-out
        await pg.evaluate("window.__urls = []; window.fetch = async (u) => { window.__urls.push(u); throw new TypeError('x'); }; document.getElementById('noIsp').checked = true")
        await pg.evaluate("loadISP()"); n_off = await pg.evaluate("window.__urls.filter(u => u.includes('ipwho.is')).length")
        await pg.evaluate("document.getElementById('noIsp').checked = false; window.__urls = []"); await pg.evaluate("loadISP()")
        n_on = await pg.evaluate("window.__urls.filter(u => u.includes('ipwho.is')).length")
        check("operator detection opt-out stops the ipwho.is request", n_off == 0 and n_on == 1)
        # --- what is stored with / without "remember"
        await pg.evaluate("localStorage.removeItem('dops-v14'); ['cfgIn', 'tgToken', 'tgChat', 'customSni', 'srcUrl', 'customSrc'].forEach((id, i) => { document.getElementById(id).value = 'private-' + id; }); document.getElementById('remember').checked = false; save();")
        off = await pg.evaluate("JSON.parse(localStorage.getItem('dops-v14'))")
        check("without 'remember': no config/token/chat/SNI/URL/list is stored", not any(k in off for k in ("cfgIn", "tgToken", "tgChat", "customSni", "srcUrl", "customSrc")) and "src" in off)
        await pg.evaluate("document.getElementById('remember').checked = true; save();")
        on = await pg.evaluate("JSON.parse(localStorage.getItem('dops-v14'))")
        check("with 'remember': they are stored (on this device only)", all(on.get(k) == "private-" + k for k in ("cfgIn", "tgToken", "tgChat", "customSni", "srcUrl", "customSrc")))
        await pg.evaluate("document.getElementById('remember').checked = false; document.getElementById('remember').dispatchEvent(new Event('change'))")
        gone = await pg.evaluate("JSON.parse(localStorage.getItem('dops-v14'))")
        check("unticking 'remember' removes them immediately", not any(k in gone for k in ("cfgIn", "tgToken", "tgChat", "customSni", "srcUrl", "customSrc")))
        # --- wipe everything
        await pg.evaluate("localStorage.setItem('dops-v14', JSON.stringify({tgToken: 'SECRET', cfgIn: 'vless://x'})); localStorage.setItem('dops-lang', 'en')")
        pg.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await pg.evaluate("document.getElementById('wipeAll').click()"); await pg.wait_for_timeout(1200)
        left = await pg.evaluate("({cfg: localStorage.getItem('dops-v14'), lang: localStorage.getItem('dops-lang'), hist: Object.keys(JSON.parse(localStorage.getItem('dops-hist2') || '{}')).length})")
        check("wipe-all clears the stored token/configs/settings/history", left == {"cfg": None, "lang": None, "hist": 0})
        # --- privacy panel text in both languages
        txt_fa = await pg.evaluate("document.getElementById('privStore') ? '' : document.querySelector('#privacy li').textContent.length")
        check("privacy panel present with text", txt_fa > 40)
        # --- CSP: never violated during all of the above
        csp = [m for m in msgs if ("Content Security Policy" in m or "Refused to" in m) and "file:///" not in m]   # relative file: fallback only exists on a local file:// copy
        check("no CSP violations", not csp); print("   csp msgs:", csp[:2])
        check("CSP meta present, no unsafe-eval", await pg.evaluate("(() => { const m = document.querySelector('meta[http-equiv=Content-Security-Policy]'); return !!m && !m.content.includes('unsafe-eval') && m.content.includes(\"object-src 'none'\"); })()"))
        check("no page errors", not errs); await b.close()
asyncio.run(main()); sys.exit(0 if ok else 1)
