#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""The in-page QR encoder is checked by DECODING its output with OpenCV (requires opencv-python-headless + numpy)."""
import asyncio, os, sys
import cv2, numpy as np
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); URL = "file://" + os.path.join(ROOT, "index.html")
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
DET = cv2.QRCodeDetectorAruco() if hasattr(cv2, "QRCodeDetectorAruco") else cv2.QRCodeDetector()
def decode(img): return DET.detectAndDecode(img)[0]
def text(n, seed):
    s, x = "", seed
    while len(s) < n: x = (x * 1103515245 + 12345) & 0x7FFFFFFF; s += "abcdefghijklmnopqrstuvwxyz0123456789-_/:?=&%#.@"[x % 46]
    return s
def render(rows, scale=6, q=4):
    n = len(rows); img = np.full(((n + 2 * q) * scale,) * 2, 255, np.uint8)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == "1": img[(y + q) * scale:(y + q + 1) * scale, (x + q) * scale:(x + q + 1) * scale] = 0
    return img
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(); await pg.goto(URL); await pg.wait_for_timeout(300)
        lens = [1, 17, 32, 78, 134, 230, 271, 367, 458, 520, 600, 700, 858, 1000, 1273]
        payloads = [text(n, i + 3) for i, n in enumerate(lens)] + ["vless://uuid@104.16.1.1:443?type=ws&security=tls&sni=d.com&path=%2Fws#My%20Node", "سلام دنیا — پاک کردن اینها 🌐"]
        bad = []
        for t in payloads:
            m = await pg.evaluate("t => { const q = QR.encode(t); return { v: q.version, rows: q.modules.map(r => r.map(b => b ? '1' : '0').join('')) }; }", t)
            if decode(render(m["rows"])) != t: bad.append((m["v"], len(t.encode())))
        check(f"{len(payloads)} payloads (v1..v25, UTF-8 incl.) decode to the exact text", not bad); print("   failures:", bad)
        # the real SVG the user sees (screenshot of #qrBox svg) decodes too
        line = "vless://u@104.16.1.1:443?type=ws&security=tls&sni=example.com&path=%2Fws&fp=chrome#My%20Node"
        await pg.set_viewport_size({"width": 420, "height": 700})
        await pg.evaluate("l => { document.getElementById('splash')?.remove(); document.getElementById('qrBox').innerHTML = QR.svg(l, 300); document.getElementById('qrModal').hidden = false; }", line)
        png = await pg.locator("#qrBox svg").screenshot()
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
        check("the displayed SVG decodes to the config", decode(img) == line)
        try: await pg.evaluate("QR.encode('x'.repeat(3000))"); check("over-long payload is rejected", False)
        except Exception: check("over-long payload is rejected", True)
        await b.close()
asyncio.run(main()); sys.exit(0 if ok else 1)
