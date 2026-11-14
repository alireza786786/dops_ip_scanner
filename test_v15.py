#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""V15 features: feedback + success rate, hourly trend, community opt-in client, experimental IPv6, preset labels."""
import asyncio, json, os, re, sys
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); URL = "file://" + os.path.join(ROOT, "index.html")
HTML = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
MOCK = """() => { window.__reqs = []; window.fetch = async (u, o) => { window.__reqs.push([u, o && o.method, o && o.body]);
    if (u.includes('/report')) return { ok: true, json: async () => ({ ok: true }) };
    if (u.includes('/best')) return { ok: true, json: async () => ({ ips: [{ ip: '104.16.9.9', n: 4 }, { ip: '8.8.8.8', n: 9 }, { ip: 'x', n: 5 }, { ip: '172.64.2.2', n: 3 }] }) };
    if (u.includes('ips-v4')) return { ok: true, text: async () => '104.16.0.0/13\\n172.64.0.0/13\\n173.245.48.0/20\\n' };
    if (u.includes('alive_cloudflare.txt')) return { ok: true, text: async () => '104.16.1.1\\n104.16.1.2\\n104.16.1.3\\n104.17.5.5\\n' };
    throw new TypeError('offline'); };
  probeOnce = async (ip) => ({ ok: true, ms: ip.endsWith('.1') ? 30 : ip.endsWith('.2') ? 45 : 90 }); ispName = 'Mobile Communication Co. of Iran (PLC)'; }"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={"width": 390, "height": 800}); pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL); await pg.wait_for_timeout(300); await pg.evaluate(MOCK)
        await pg.evaluate("document.getElementById('src').value = 'outputs/alive_cloudflare.txt'; document.getElementById('limit').value = '50'; document.getElementById('smart').checked = false")
        await pg.evaluate("run()"); await pg.wait_for_timeout(200)
        # ---------------- feedback
        top0 = await pg.evaluate("bestList()[0].ip")
        btns = await pg.evaluate("document.querySelectorAll('#rows tr:first-child .fb button').length")
        check("every row has two feedback buttons (👍 👎)", btns == 2 and top0 == "104.16.1.1")
        await pg.evaluate("document.querySelector('#rows tr:first-child .badb').click()")
        top1 = await pg.evaluate("bestList()[0].ip"); first_row = await pg.evaluate("document.querySelector('#rows tr:first-child td').textContent")
        check("👎 sinks the IP in the ranking and in the table", top1 != top0 and top0 not in first_row)
        await pg.evaluate("document.querySelector('#rows tr:first-child .okb').click()")
        st = await pg.evaluate("({txt: document.getElementById('fbStats').textContent, hidden: document.getElementById('fbStats').hidden, pressed: document.querySelector('#rows tr:first-child .okb').getAttribute('aria-pressed')})")
        check("success-rate line shows real feedback counts", not st["hidden"] and "۵۰" in st["txt"] and st["pressed"] == "true")
        await pg.evaluate("document.querySelector('#rows tr:first-child .okb').click()")   # toggle off
        await pg.evaluate("(() => { const ip = bestList()[0].ip; fbSet(ip, 'bad'); fbSet(ip, 'bad'); })()")
        st2 = await pg.evaluate("Object.keys(fbMap()).length")
        check("feedback toggles off on a second click", st2 == 1)
        raw = await pg.evaluate("localStorage.getItem('dops-fb')")
        check("feedback stored locally per operator (no config/token)", "mobile communication" in raw.lower() or "Mobile" in raw)
        await pg.evaluate("ispName = 'Other ISP'; fbCache = null")
        check("feedback is per operator", await pg.evaluate("Object.keys(fbMap()).length") == 0)
        await pg.evaluate("ispName = 'Mobile Communication Co. of Iran (PLC)'; fbCache = null")
        # ---------------- trend
        await pg.evaluate("localStorage.removeItem('dops-trend'); ispName = 'T1'; recordTrend(50, [{ping: 40}]); recordTrend(50, [{ping: 41}]); renderTrend()")
        check("trend: too little data -> hint", "داده" in await pg.evaluate("document.getElementById('trendBody').textContent"))
        await pg.evaluate("""(() => { const all = {}; const now = Date.now(); all['T1'] = [[9, 40, 50, 30], [9, 45, 50, 35], [14, 60, 50, 10], [14, 70, 50, 12], [22, 90, 50, 5]].map(([h, m, n, k], i) => ({ t: now - i * 3600e3, h, n, k, m })); localStorage.setItem('dops-trend', JSON.stringify(all)); renderTrend(); })()""")
        tr = await pg.evaluate("({svgs: document.querySelectorAll('#trendBody svg').length, bars: document.querySelectorAll('#trendBody svg:first-of-type rect').length, txt: document.getElementById('trendBody').textContent})")
        check("trend: hourly bars (24) + ping line + best hours (9:00 first)", tr["svgs"] == 2 and tr["bars"] == 24 and "9:00" in tr["txt"])
        # ---------------- IPv6
        v6 = await pg.evaluate("""(() => { const s = fromCf6(40); const back = s.map(x => { const m = /^2606:4700::([0-9a-f]{1,4}):([0-9a-f]{1,4})$/.exec(x); if (!m) return null; const a = parseInt(m[1], 16), c = parseInt(m[2], 16); return `${a >> 8}.${a & 255}.${c >> 8}.${c & 255}`; });
          return { n: s.length, ok: back.every(x => x && (inCidr(x, '104.16.0.0/13') || inCidr(x, '104.24.0.0/14'))), valid: s.every(isIPv6),
            cases: ['2606:4700::6810:84e5', '::1', '2606:4700::', 'fe80::1', '1:2:3:4:5:6:7:8'].map(isIPv6), bad: ['2606:4700::6810::1', '1.2.3.4', 'g::1', '1:2:3:4:5:6:7', '', 'abc', '1:2:3:4:5:6:7:8:9'].map(isIPv6),
            custom: parseCustom('1.1.1.1 2606:4700::6810:84E5 not-an-ip 162.159.20.0/24').ips, sort: ['104.16.1.1', '2606:4700::6810:1', '1.1.1.1'].map(ipSort).every(Number.isFinite) }; })()""")
        check("IPv6 sampler maps Cloudflare IPv4 space into 2606:4700::a.b:c.d", v6["n"] == 40 and v6["ok"] and v6["valid"])
        check("IPv6 validator: valid/invalid cases", v6["cases"] == [True] * 5 and v6["bad"] == [False] * 7)
        check("manual list accepts IPv6 (lowercased) next to IPv4", v6["custom"] == ["1.1.1.1", "2606:4700::6810:84e5"] and v6["sort"])
        probe_src = re.search(r"async function probeOnce\(ip, port.*?\n\}", HTML, re.S).group(0)
        check("probe URL uses brackets for IPv6", "urlHost(ip)" in probe_src)
        rw = await pg.evaluate("({v: rewrite('vless://u@sub.example.com:443?type=ws&security=tls#x', '2606:4700::6810:84e5', true, false, false, 'x'), m: JSON.parse(b64d(rewrite('vmess://' + b64e(JSON.stringify({v:2,ps:'a',add:'h.com',port:'443',id:'1',net:'ws',tls:'tls'})), '2606:4700::6810:84e5', true, false, false, 'x').slice(8))).add })")
        check("rewrite: [IPv6] in URI links, raw IPv6 in VMess JSON", rw["v"].startswith("vless://u@[2606:4700::6810:84e5]:443?") and rw["m"] == "2606:4700::6810:84e5")
        c6 = await pg.evaluate("buildClash(['vless://u@[2606:4700::6810:84e5]:443?type=ws&security=tls&sni=s.com#x']).text")
        check("Clash export keeps the IPv6 server unbracketed", 'server: "2606:4700::6810:84e5"' in c6)
        await pg.evaluate(MOCK); await pg.evaluate("document.getElementById('src').value = 'cf_ranges_v6'; document.getElementById('limit').value = '50'; document.getElementById('smart').checked = false; document.getElementById('targetPort').value = '443'; srcUi()")
        await pg.evaluate("run()"); await pg.wait_for_timeout(300)
        r6 = await pg.evaluate("({n: results.length, v6: results.every(r => r.ip.startsWith('2606:4700::')), warn: document.getElementById('cdnWarn').style.display})")
        print("   r6:", r6); check("IPv6 source scans end to end with a visible warning", r6["n"] == 50 and r6["v6"] and r6["warn"] == "block")
        # ---------------- preset labels
        labels = await pg.evaluate("['google','cloudfront','azure','gcore','arvancloud','warp'].map(v => document.querySelector('#src option[value=' + v + ']').textContent.includes('آزمایشی'))")
        check("non-Cloudflare presets are labelled experimental", all(labels))
        # ---------------- community (disabled by default)
        dis = await pg.evaluate("({share: document.getElementById('shareOpt').disabled, opt: document.querySelector('#src option[value=community]').disabled})")
        check("community is off until a Worker URL is configured", dis["share"] and dis["opt"])
        check("no page errors (main page)", not errs); await ctx.close()
        # ---------------- community enabled: serve the page with a Worker URL at the official origin
        html2 = HTML.replace("const COMMUNITY_URL = '';", "const COMMUNITY_URL = 'https://w.example';")
        c2 = await b.new_context(viewport={"width": 390, "height": 800}); p2 = await c2.new_page(); e2 = []
        p2.on("pageerror", lambda e: e2.append(str(e)))
        async def h(route):
            u = route.request.url; await (route.fulfill(body=html2, content_type="text/html") if u.endswith("/index.html") or u.endswith("/") else route.abort())
        await c2.route("**/*", h); await p2.goto("https://alireza786786.github.io/dops_ip_scanner/"); await p2.wait_for_timeout(400); await p2.evaluate(MOCK)
        en = await p2.evaluate("({share: !document.getElementById('shareOpt').disabled, opt: !document.querySelector('#src option[value=community]').disabled})")
        check("community controls are enabled when the URL is set", en["share"] and en["opt"])
        await p2.evaluate("document.getElementById('src').value = 'outputs/alive_cloudflare.txt'; document.getElementById('limit').value = '50'; document.getElementById('smart').checked = false; document.getElementById('shareOpt').checked = false")
        await p2.evaluate("run()"); await p2.wait_for_timeout(300)
        check("opt-out: nothing is sent", await p2.evaluate("!window.__reqs.some(r => r[0].includes('/report'))"))
        await p2.evaluate("window.__reqs = []; document.getElementById('shareOpt').checked = true"); await p2.evaluate("run()"); await p2.wait_for_timeout(400)
        rep = await p2.evaluate("(() => { const r = window.__reqs.find(r => r[0] === 'https://w.example/report'); return r ? { m: r[1], b: JSON.parse(r[2]) } : null; })()")
        check("opt-in: one POST /report with the documented payload", rep and rep["m"] == "POST" and rep["b"]["v"] == 1 and re.fullmatch(r"[0-9a-f]{32}", rep["b"]["id"]) and 1 <= len(rep["b"]["ips"]) <= 10 and all(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", x["ip"]) and 0 <= x["ms"] <= 5000 for x in rep["b"]["ips"]))
        check("payload carries only operator+IPs+id (no config/token)", rep and set(rep["b"].keys()) == {"v", "isp", "id", "ips"} and "(" in rep["b"]["isp"])
        await p2.evaluate("window.__reqs = []; document.getElementById('noIsp').checked = true"); await p2.evaluate("run()"); await p2.wait_for_timeout(400)
        check("operator detection off -> nothing is sent", await p2.evaluate("!window.__reqs.some(r => r[0].includes('/report'))"))
        await p2.evaluate("document.getElementById('noIsp').checked = false; ispName = 'X'")
        await p2.evaluate("window.__reqs = []; document.getElementById('shareOpt').checked = true; document.getElementById('cfgIn').value = 'vless://secret-uuid@h.com:443?type=ws#priv'"); await p2.evaluate("run()"); await p2.wait_for_timeout(400)
        body = await p2.evaluate("(window.__reqs.find(r => r[0].includes('/report')) || [])[2] || ''")
        check("a pasted config never appears in the report", "secret-uuid" not in body and "h.com" not in body)
        await p2.evaluate("document.getElementById('src').value = 'community'; document.getElementById('limit').value = '0'")
        t = await p2.evaluate("loadTargets()")
        check("community source: only Cloudflare-range IPv4 candidates (8.8.8.8 / junk dropped)", sorted(t["ips"]) == ["104.16.9.9", "172.64.2.2"] and "جمعی" in t["note"])
        await p2.evaluate("() => { window.fetch = async () => { throw new TypeError('x'); }; }"); t2 = await p2.evaluate("loadTargets()")
        check("community source falls back to the offline bank", len(t2["ips"]) > 10)
        check("no page errors (community page)", not e2); await b.close()
asyncio.run(main()); sys.exit(0 if ok else 1)
