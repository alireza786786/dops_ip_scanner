async () => {
  const o = {}, T = async (name, fn) => { try { o[name] = await fn(); } catch (e) { o[name] = 'EXC: ' + (e && e.message || e); } };
  const mk = (ms = 50) => async () => ({ ok: true, ms: ms + Math.random() });
  const offlineFetch = async () => { throw new TypeError('offline'); };
  await T('rewrite', () => {
    const vl = 'vless://uuid@sub.example.com:2087?type=ws&security=tls&sni=old.com&path=%2Fws#My%20Node';
    const vm = 'vmess://' + b64e(JSON.stringify({ v: 2, ps: 'a%b', add: 'x.example.com', port: '8443', id: '1', net: 'ws', tls: 'tls' }));
    const ssOld = 'ss://' + b64e('aes-128-gcm:pw@1.2.3.4:8388') + '#n', real = 'vless://u@h.com:443?security=reality&type=tcp#r';
    $('customSni').value = 'my.dom.com'; const a = rewrite(vl, '1.1.1.1', true, false, false, 'cf_ranges'); $('customSni').value = '';
    const ipHost = rewrite('vless://u@5.6.7.8:443?security=tls&type=tcp#ipcfg', '1.1.1.1', true, false, false, 'cf_ranges');
    return { port: [cfgPort(vl), cfgPort(vm), cfgPort(ssOld), cfgPort(real)], custom: a, ssSame: rewrite(ssOld, '9.9.9.9', true, false, false, 'x') === ssOld,
      realSame: rewrite(real, '9.9.9.9', true, false, false, 'x') === real, vmAdd: JSON.parse(b64d(rewrite(vm, '5.5.5.5', true, false, false, 'x').slice(8))).add, ipHostCfg: ipHost };
  });
  await T('ports', () => { $('customPort').value = '2096, 8443 99999'; $('targetPort').value = 'custom'; const c = getPorts(); $('targetPort').value = 'all_tls'; return [c, getPorts().length, parseCustom('1.1.1.1 162.159.20.0/24').cd]; });
  await T('scan_each_source', async () => {
    const res = {}; window.fetch = offlineFetch;
    for (const src of ['cf_ranges', 'google', 'cloudfront', 'fastly_ranges', 'azure', 'gcore', 'arvancloud', 'warp', 'offline_db']) {
      probeOnce = mk(60); $('src').value = src; $('limit').value = '50'; $('targetPort').value = '443'; $('smart').checked = false; await run(); res[src] = results.length;
    } return res;
  });
  await T('smart_presets', async () => {
    ispName = 'T'; localStorage.removeItem(BLK_KEY); probeOnce = mk(60); window.fetch = offlineFetch;
    $('src').value = 'google'; $('limit').value = '50'; $('smart').checked = true; await run();
    const blocks = Object.keys(readBlocks()['T'] || {}).length; const t = await (async () => { $('src').value = 'google'; return loadTargets(); })();
    return { blocks, hotNote: /learned|یادگرفته/.test(t.note) };
  });
  await T('lang_quality', async () => {
    probeOnce = mk(60); $('src').value = 'offline_db'; $('limit').value = '50'; $('smart').checked = false; await run();
    const k = results[0].qk; currentLang = 'en'; applyI18n(); const row = $('rows').children[0].textContent; currentLang = 'fa'; applyI18n();
    return { qk: k, enRowHasEnglishQuality: /Excellent|Good|Fair/.test(row) };
  });
  await T('data_branch', async () => {
    const seen = []; window.fetch = async (u) => { seen.push(u); return u.endsWith('.json') ? { ok: true, json: async () => ({ scanned_at: new Date(Date.now() - 36e5).toISOString(), vantage: 'github-actions' }) } : { ok: true, text: async () => '104.16.1.1 ping=3ms\n' }; };
    $('src').value = 'outputs/alive_cloudflare.txt'; $('limit').value = '0'; const t = await loadTargets();
    return { ips: t.ips, dataFirst: !!seen[0] && seen[0].includes('/data/outputs/'), note: t.note.slice(0, 40) };
  });
  await T('fallback_relative', async () => {
    window.fetch = async (u) => u.startsWith('https://raw') ? { ok: false } : u.endsWith('.json') ? { ok: false } : { ok: true, text: async () => '104.16.9.9\n' };
    $('src').value = 'outputs/alive_cloudflare.txt'; return (await loadTargets()).ips;
  });
  await T('offline_bank_fallback', async () => { window.fetch = offlineFetch; $('src').value = 'outputs/alive_cloudflare.txt'; const t = await loadTargets(); return [t.ips.length > 10, t.note.slice(0, 20)]; });
  await T('cf2dns', async () => {
    window.fetch = async (u) => u.includes('ircfspace') ? { ok: true, json: async () => [{ ip: '198.41.208.160', time: '2026-09-11 00:56:32' }, { ip: '8.8.8.8', time: '2026-09-11 00:56:32' }, { ip: '104.16.200.25', time: '2026-09-11 00:56:32' }] } : { ok: true, text: async () => '173.245.48.0/20\n104.16.0.0/13\n198.41.128.0/17\n' };
    $('src').value = 'cf2dns'; $('limit').value = '0'; const t = await loadTargets(); srcUi(); return { ips: t.ips.sort(), note: t.note.slice(0, 70), warn: $('cdnWarn').style.display };
  });
  await T('warnings', () => { const r = {}; for (const v of ['cf_ranges', 'google', 'warp', 'cf2dns', 'offline_db']) { $('src').value = v; srcUi(); r[v] = $('cdnWarn').style.display; } return r; });
  await T('sni_keep', () => { const l = 'vless://u@sub.example.com:443?type=ws&security=tls#x'; return { keep: rewrite(l, '1.1.1.1', true, false, false, 'x'), noKeep: rewrite(l, '1.1.1.1', false, false, false, 'x') }; });
  await T('history', () => { ispName = 'A'; updateHistory(['1.1.1.1']); updateHistory(['1.1.1.1']); const a = getHistory()['1.1.1.1']; ispName = 'B'; return [a, getHistory()['1.1.1.1'] === undefined]; });
  await T('clash', () => { const c = buildClash(['vless://uuid1@s.com:443?type=ws&security=tls&sni=d.com&path=%2Fws&fp=chrome#My%20Node', 'trojan://pw@t.com:443?security=tls&sni=t.com#tj', 'vless://u@x.com:443?type=xhttp#bad']); return { text: c.text, count: c.count, skip: c.skip }; });
  await T('modal_clear', async () => {
    probeOnce = mk(60); window.fetch = offlineFetch; $('src').value = 'offline_db'; $('limit').value = '50'; $('cfgIn').value = 'vless://a@h.com:443?type=ws#x'; await run();
    copy = async t => { window.__c = t; }; $('bBottomCopy').click(); const m = !$('copyModal').hidden; $('cpAll').click(); const n = window.__c.split('\n').length;
    $('clearCfgOut').click(); const co = $('cfgOut').value; $('clearCfgIn').click(); return [m, n, co, $('cfgIn').value];
  });
  await T('remember', () => { $('remember').checked = true; $('cfgIn').value = 'vless://a@h.com:443#x'; $('cfgIn').dispatchEvent(new Event('change')); const a = !!JSON.parse(localStorage.getItem('dops-v14')).cfgIn; $('remember').checked = false; $('remember').dispatchEvent(new Event('change')); return [a, !JSON.parse(localStorage.getItem('dops-v14')).cfgIn]; });
  await T('sub_errors', async () => {
    const m = [];
    for (const e of [new TypeError('x'), Object.assign(new Error('a'), { name: 'AbortError' }), 0]) { getText = async () => { if (e === 0) return 'hello:// nothing'; throw e; }; $('subUrl').value = 'https://x.com/s'; await $('bSub').onclick(); m.push($('toast').textContent.slice(0, 22)); }
    return [...new Set(m)].length;
  });
  await T('tabs', () => { const r = []; for (let i = 1; i <= 5; i++) { showTab(i); r.push($('tab' + i).style.display); } return r; });
  await T('theme_lang', () => { toggleTheme(); const a = document.documentElement.dataset.theme; toggleTheme(); toggleLang(); const b = [document.documentElement.dir, localStorage.getItem('dops-lang')]; toggleLang(); return [a, b, document.documentElement.dir]; });
  await T('gh_clear', () => { const a = $('ghBtn'); $('manualIps').value = '104.16.1.1'; $('clearManual').click(); return { href: a.href, target: a.target, rel: a.rel, cleared: $('manualIps').value === '', inNav: !!a.closest('.nav-actions') }; });
  await T('i18n_keys', () => {
    const keys = [...new Set([...document.querySelectorAll('[data-i18n]')].map(e => e.dataset.i18n))];
    return { missingFa: keys.filter(k => !I18N.fa[k]), missingEn: keys.filter(k => !I18N.en[k]), faOnly: Object.keys(I18N.fa).filter(k => !(k in I18N.en)), enOnly: Object.keys(I18N.en).filter(k => !(k in I18N.fa)) };
  });
  return o;
}
