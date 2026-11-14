// Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See ../LICENSE.
/**
 * DOPS Worker (Cloudflare Workers, free plan)
 *  1) scheduled(): every cron tick it
 *       - dispatches the GitHub "scanner.yml" workflow (reliable replacement for GitHub's best-effort cron),
 *       - checks how old the published list is and sends a Telegram alert if it is stale (works even if GitHub Actions is dead).
 *  2) fetch(): OPT-IN anonymous community results
 *       POST /report  {v:1, isp, id, ips:[{ip, ms}]}     -> stored per operator, reporter id is hashed with a secret salt
 *       GET  /best?isp=...                                -> IPs reported by >= MIN_REPORTERS distinct reporters (used only as seeds)
 *     No reporter IP address, no config, no token is ever stored. Only Cloudflare-range IPv4 addresses are accepted.
 *
 * Bindings / variables (Cloudflare dashboard -> Worker -> Settings):
 *   KV namespace  : KV                      (community data + alert rate-limit)
 *   Secrets       : GH_TOKEN (fine-grained PAT, Actions: read/write on the repo), SALT (any long random text),
 *                   BOT_TOKEN, ADMIN_CHAT_ID (optional, stale alerts)
 *   Variables     : GH_REPO = "alireza786786/dops_ip_scanner", GH_WORKFLOW = "scanner.yml", GH_REF = "main",
 *                   ALLOWED_ORIGIN = "https://alireza786786.github.io"
 */
export const CF_V4 = ['173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18', '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22', '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13', '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22'];
export const LIMITS = { MIN_REPORTERS: 3, TTL_H: 24, MAX_IPS_PER_REPORT: 10, MAX_REPORTERS_PER_IP: 40, MAX_IDS: 400, MIN_GAP_MIN: 10, BODY_MAX: 4096, STALE_H: 3, ALERT_GAP_H: 6, BEST_MAX: 30 };

export const ipToInt = ip => { const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ip); if (!m) return null; const p = m.slice(1).map(Number); if (p.some(x => x > 255)) return null; return ((p[0] * 16777216) + (p[1] << 16) + (p[2] << 8) + p[3]) >>> 0; };
export const inCidr = (ip, cidr) => { const [b, m] = cidr.split('/'), n = ipToInt(ip), s = ipToInt(b); if (n === null || s === null) return false; const size = 2 ** (32 - +m); return n >= s - (s % size) && n < s - (s % size) + size; };
export const isCfIp = ip => ipToInt(ip) !== null && CF_V4.some(c => inCidr(ip, c));
export const normIsp = s => { if (typeof s !== 'string') return null; const t = s.normalize('NFKC').replace(/\s+/g, ' ').trim().slice(0, 64); return /^[\p{L}\p{N} .,&()\-_/'’]{2,64}$/u.test(t) ? t.toLowerCase() : null; };
export async function hashId(id, salt) { const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${salt}:${id}`)); return [...new Uint8Array(d)].slice(0, 8).map(b => b.toString(16).padStart(2, '0')).join(''); }

const json = (obj, status, headers) => new Response(JSON.stringify(obj), { status: status || 200, headers: { 'content-type': 'application/json; charset=utf-8', ...(headers || {}) } });
function corsHeaders(request, env) {
  const origin = request.headers.get('Origin'), allowed = env.ALLOWED_ORIGIN || '';
  const ok = allowed === '*' || (origin && origin === allowed);
  return { 'Vary': 'Origin', ...(ok ? { 'Access-Control-Allow-Origin': allowed === '*' ? '*' : origin, 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'content-type', 'Access-Control-Max-Age': '86400' } : {}) };
}
const docKey = isp => `isp:${isp}`;
async function readDoc(env, isp) { const raw = await env.KV.get(docKey(isp)); try { const d = raw ? JSON.parse(raw) : null; return d && d.ips && d.ids ? d : { ips: {}, ids: {} }; } catch { return { ips: {}, ids: {} }; } }

export async function handleReport(request, env, now = Date.now()) {
  if (!env.KV || !env.SALT) return json({ error: 'not_configured' }, 503);
  const text = await request.text(); if (text.length > LIMITS.BODY_MAX) return json({ error: 'too_large' }, 413);
  let b; try { b = JSON.parse(text); } catch { return json({ error: 'bad_json' }, 400); }
  const isp = normIsp(b && b.isp); if (!isp) return json({ error: 'bad_isp' }, 400);
  if (!b || b.v !== 1 || typeof b.id !== 'string' || !/^[0-9a-f]{32}$/.test(b.id)) return json({ error: 'bad_id' }, 400);
  if (!Array.isArray(b.ips) || !b.ips.length || b.ips.length > LIMITS.MAX_IPS_PER_REPORT) return json({ error: 'bad_ips' }, 400);
  const clean = [];
  for (const x of b.ips) { if (!x || typeof x.ip !== 'string' || !isCfIp(x.ip) || !Number.isInteger(x.ms) || x.ms < 0 || x.ms > 5000) return json({ error: 'bad_ip_entry' }, 400); clean.push([x.ip, x.ms]); }
  const idh = await hashId(b.id, env.SALT), doc = await readDoc(env, isp), ttl = LIMITS.TTL_H * 3600e3;
  if (doc.ids[idh] && now - doc.ids[idh] < LIMITS.MIN_GAP_MIN * 60e3) return json({ error: 'too_soon' }, 429);
  for (const ip of Object.keys(doc.ips)) { doc.ips[ip] = doc.ips[ip].filter(r => now - r[1] < ttl); if (!doc.ips[ip].length) delete doc.ips[ip]; }
  for (const [ip, ms] of clean) { const arr = (doc.ips[ip] = (doc.ips[ip] || []).filter(r => r[0] !== idh)); arr.push([idh, now, ms]); if (arr.length > LIMITS.MAX_REPORTERS_PER_IP) arr.splice(0, arr.length - LIMITS.MAX_REPORTERS_PER_IP); }
  doc.ids[idh] = now; const ids = Object.entries(doc.ids).filter(([, t]) => now - t < ttl).sort((a, c) => c[1] - a[1]).slice(0, LIMITS.MAX_IDS); doc.ids = Object.fromEntries(ids);
  await env.KV.put(docKey(isp), JSON.stringify(doc), { expirationTtl: 48 * 3600 });
  return json({ ok: true, accepted: clean.length });
}
export async function handleBest(url, env, now = Date.now()) {
  if (!env.KV) return json({ error: 'not_configured' }, 503);
  const isp = normIsp(url.searchParams.get('isp')); if (!isp) return json({ error: 'bad_isp' }, 400);
  const doc = await readDoc(env, isp), ttl = LIMITS.TTL_H * 3600e3, out = [];
  for (const [ip, rs] of Object.entries(doc.ips)) { const live = rs.filter(r => now - r[1] < ttl), n = new Set(live.map(r => r[0])).size; if (n >= LIMITS.MIN_REPORTERS && isCfIp(ip)) out.push({ ip, n, ms: Math.round(live.reduce((a, r) => a + r[2], 0) / live.length) }); }
  out.sort((a, c) => c.n - a.n || a.ms - c.ms);
  return json({ isp, min_reporters: LIMITS.MIN_REPORTERS, generated: new Date(now).toISOString(), ips: out.slice(0, LIMITS.BEST_MAX) }, 200, { 'cache-control': 'public, max-age=300' });
}

export async function dispatchWorkflow(env, fetchFn = fetch) {
  if (!env.GH_TOKEN || !env.GH_REPO) return { skipped: true };
  const r = await fetchFn(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${env.GH_WORKFLOW || 'scanner.yml'}/dispatches`, {
    method: 'POST', headers: { Accept: 'application/vnd.github+json', Authorization: `Bearer ${env.GH_TOKEN}`, 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'dops-worker', 'content-type': 'application/json' },
    body: JSON.stringify({ ref: env.GH_REF || 'main', inputs: { from: 'worker' } }) });
  return { status: r.status, ok: r.status === 204 };
}
export async function checkStale(env, now = Date.now(), fetchFn = fetch) {
  if (!env.GH_REPO) return { skipped: true };
  let ageH = null;
  try { const r = await fetchFn(`https://raw.githubusercontent.com/${env.GH_REPO}/data/outputs/alive_cloudflare.json`, { headers: { 'User-Agent': 'dops-worker' } }); if (r.ok) { const j = await r.json(), t = Date.parse(j.scanned_at); if (Number.isFinite(t)) ageH = (now - t) / 3600e3; } } catch { /* unknown age counts as stale */ }
  const stale = ageH === null || ageH > LIMITS.STALE_H;
  if (!stale || !env.BOT_TOKEN || !env.ADMIN_CHAT_ID) return { stale, ageH, alerted: false };
  if (env.KV) { const last = Number(await env.KV.get('alert:at')) || 0; if (now - last < LIMITS.ALERT_GAP_H * 3600e3) return { stale, ageH, alerted: false }; }
  const text = ageH === null ? '⚠️ DOPS: سن لیست مخزن نامعلوم است (فایل data خوانده نشد).' : `⚠️ DOPS: لیست مخزن ${ageH.toFixed(1)} ساعت است به‌روز نشده.`;
  let r = null;
  try { r = await fetchFn(`https://api.telegram.org/bot${env.BOT_TOKEN}/sendMessage`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ chat_id: env.ADMIN_CHAT_ID, text }) }); } catch { /* alert failed; will retry next tick */ }
  const sent = !!(r && r.ok);
  if (sent && env.KV) await env.KV.put('alert:at', String(now));
  return { stale, ageH, alerted: sent };
}

export default {
  async scheduled(event, env, ctx) { ctx.waitUntil((async () => { const d = await dispatchWorkflow(env).catch(e => ({ error: String(e) })); const s = await checkStale(env).catch(e => ({ error: String(e) })); console.log(JSON.stringify({ dispatch: d, stale: s })); })()); },
  async fetch(request, env) {
    const url = new URL(request.url), cors = corsHeaders(request, env);
    const wrap = async p => { const r = await p; const h = new Headers(r.headers); Object.entries(cors).forEach(([k, v]) => h.set(k, v)); return new Response(r.body, { status: r.status, headers: h }); };
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (url.pathname === '/health') return wrap(json({ ok: true, community: !!(env.KV && env.SALT), dispatch: !!(env.GH_TOKEN && env.GH_REPO) }));
    if (url.pathname === '/report' && request.method === 'POST') { if (!cors['Access-Control-Allow-Origin']) return json({ error: 'forbidden_origin' }, 403); return wrap(handleReport(request, env)); }
    if (url.pathname === '/best' && request.method === 'GET') return wrap(handleBest(url, env));
    return json({ error: 'not_found' }, 404);
  },
};
