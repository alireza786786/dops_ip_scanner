/* DOPS V14 Meridian — Service Worker
   Strategy: network-first for cross-origin (probes, APIs) — never cached,
   cache-first with background refresh for same-origin app shell (full offline). */
const CACHE = 'dops-v14-shell-v1';
const SHELL = ['./dops_scanner_v14.html', './manifest.json', './icon-192.png', './icon-512.png', './icon-512-maskable.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  /* Cross-origin (ipwho.is, Telegram, IP probes...): network only */
  if (url.origin !== self.location.origin) return;
  /* Same-origin app shell: cache-first, refresh in background */
  e.respondWith(
    caches.match(e.request).then(cached => {
      const fresh = fetch(e.request).then(res => {
        if (res && res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone()));
        return res;
      }).catch(() => cached);
      return cached || fresh;
    })
  );
});
