#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""Automated accessibility checks (WCAG 2.x AA subset): names, contrast in both themes/languages, target size, dialogs, focus styles."""
import asyncio, json, os, sys
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); URL = "file://" + os.path.join(ROOT, "index.html")
ok = True
def check(name, cond, detail=None):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
    if not cond and detail: print("   ", json.dumps(detail, ensure_ascii=False)[:900])
CONTRAST = r"""() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return [0, 0, 0, 0]; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (top, bot) => { const a = top[3]; return [top[0] * a + bot[0] * (1 - a), top[1] * a + bot[1] * (1 - a), top[2] * a + bot[2] * (1 - a), 1]; };
  const bgOf = el => { const layers = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c[3] > 0) layers.push(c); if (c[3] === 1) break; } let base = [255, 255, 255, 1]; if (!layers.length || layers[layers.length - 1][3] < 1) { const b = parse(getComputedStyle(document.body).backgroundColor); base = b[3] > 0 ? [b[0], b[1], b[2], 1] : (getComputedStyle(document.documentElement).colorScheme === 'dark' ? [7, 11, 20, 1] : [255, 255, 255, 1]); } return layers.reduceRight((acc, l) => over(l, acc), base); };
  const lum = c => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05); };
  const bad = [], seen = new Set();
  document.querySelectorAll('body *').forEach(el => {
    if (['SCRIPT', 'STYLE', 'SVG', 'PATH', 'RECT', 'POLYLINE', 'CIRCLE', 'ELLIPSE', 'LINE', 'G', 'TITLE', 'OPTION', 'OPTGROUP', 'DEFS', 'LINEARGRADIENT', 'STOP', 'TEXT'].includes(el.tagName.toUpperCase())) return;
    if (el.closest('#splash') || el.closest('[hidden]') || el.closest('svg')) return;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
    const own = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim().length > 1); if (!own.length) return;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || +cs.opacity === 0) return;
    const fg = parse(cs.color), bg = bgOf(el), fgc = over(fg, bg), size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700, large = size >= 24 || (size >= 18.66 && bold), need = large ? 3 : 4.5, rt = ratio(fgc, bg);
    if (rt < need) { const key = (el.id || el.className || el.tagName) + '|' + cs.color + '|' + cs.backgroundColor; if (!seen.has(key)) { seen.add(key); bad.push({ el: (el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0]), ratio: Math.round(rt * 100) / 100, need, color: cs.color, text: el.textContent.trim().slice(0, 24) }); } }
  });
  return bad;
}"""
NAMES = r"""() => {
  const bad = [];
  document.querySelectorAll('button, a[href], input, select, textarea, summary, [role=button]').forEach(el => {
    if (el.closest('[hidden]') || el.type === 'hidden') return;
    const lab = el.getAttribute('aria-label') || el.getAttribute('title') || (el.labels && el.labels.length && [...el.labels].some(l => l.textContent.trim())) || el.textContent.trim() || (el.closest('label') && el.closest('label').textContent.trim()) || el.getAttribute('aria-labelledby') || (el.tagName === 'SELECT' && el.closest('.row') && el.closest('.row').textContent.trim()) || (el.tagName === 'INPUT' && el.closest('.row') && el.closest('.row').textContent.trim()) || el.getAttribute('placeholder');
    if (!lab) bad.push(el.id || el.tagName + ':' + el.outerHTML.slice(0, 60));
  }); return bad;
}"""
TARGETS = r"""() => [...document.querySelectorAll('button, a[href], select, input:not([type=checkbox]):not([type=hidden]), summary')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height && !e.closest('[hidden]') && !e.closest('#splash') && getComputedStyle(e).visibility !== 'hidden'; }).map(e => { const r = e.getBoundingClientRect(); return { id: e.id || e.tagName + ':' + (e.textContent || '').trim().slice(0, 12), w: Math.round(r.width), h: Math.round(r.height) }; }).filter(x => x.w < 24 || x.h < 24)"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 390, "height": 900}); await pg.goto(URL); await pg.wait_for_timeout(2900)
        await pg.add_style_tag(content="*{transition:none!important;animation:none!important}")   # measure final colours, not mid-transition ones
        await pg.evaluate("() => { document.getElementById('privacy').open = true; document.getElementById('trend').open = true; document.getElementById('fakeWarn').hidden = false; }")
        for theme in ("dark", "light"):
            for lang in ("fa", "en"):
                await pg.evaluate("([th, lg]) => { if (currentTheme !== th) toggleTheme(); if (currentLang !== lg) toggleLang(); }", [theme, lang]); await pg.wait_for_timeout(150)
                bad = await pg.evaluate(CONTRAST)
                check(f"text contrast AA — {theme}/{lang}", not bad, bad)
        names = await pg.evaluate(NAMES); check("every control has an accessible name", not names, names)
        small = await pg.evaluate(TARGETS); check("touch targets are at least 24x24 CSS px (WCAG 2.2 AA)", not small, small)
        meta = await pg.evaluate("({lang: document.documentElement.lang, dir: document.documentElement.dir, h1: document.querySelectorAll('h1').length, focus: [...document.styleSheets].some(s => { try { return [...s.cssRules].some(r => r.cssText.includes(':focus-visible')); } catch { return false; } })})")
        check("html lang/dir set, a single h1, visible focus style", meta["lang"] in ("fa", "en") and meta["dir"] in ("rtl", "ltr") and meta["h1"] == 1 and meta["focus"], meta)
        dlg = await pg.evaluate("[...document.querySelectorAll('.modal')].filter(m => m.getAttribute('role') !== 'dialog' || m.getAttribute('aria-modal') !== 'true').map(m => m.id)")
        check("modals declare role=dialog aria-modal", not dlg, dlg)
        dec = await pg.evaluate("[...document.querySelectorAll('svg')].filter(s => !s.closest('[hidden]') && s.getAttribute('aria-hidden') !== 'true' && s.getAttribute('role') !== 'img').length")
        check("every SVG is decorative (aria-hidden) or labelled (role=img)", dec == 0, dec)
        await pg.evaluate("document.activeElement && document.activeElement.blur()"); await pg.keyboard.press("Tab"); await pg.keyboard.press("Tab")
        check("keyboard Tab reaches interactive elements", await pg.evaluate("['A', 'BUTTON', 'SUMMARY', 'INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)"))
        await b.close()
asyncio.run(main()); sys.exit(0 if ok else 1)
