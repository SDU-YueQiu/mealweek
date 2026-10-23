/* MealWeek service worker: shell + week + every image, so an installed
   app opens instantly with the PC off and away from the wifi.
   Bump V whenever index.html / app.js / style.css / sw.js changes. */
const V = 'mw-v31';
const ASSETS = 'mw-assets-v1';
const SHELL = ['/', '/index.html', '/style.css', '/app.js', '/manifest.webmanifest'];

const OFFLINE_HTML = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#FBF7F0"><title>本周菜单 · 离线</title>
<style>
html,body{margin:0;background:#fbf7f0;color:#241f1a;font:16px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif}
.w{max-width:420px;margin:0 auto;padding:72px 24px;text-align:center}
h1{font-size:24px;margin:0 0 14px}p{color:#6f6355;font-size:14px;margin:8px 0}
button{margin-top:24px;padding:11px 26px;border:0;border-radius:99px;background:#241f1a;color:#fff;font:inherit;font-size:15px}
</style></head><body><div class="w"><h1>本周菜单</h1>
<p>离线缓存还没准备好，或者这台设备还没装好。</p>
<p>连上电脑打开一次，等同步完成；或者下载单文件离线包。</p>
<button onclick="location.reload()">重试</button></div></body></html>`;

async function cacheUrls(cache, urls, limit) {
  let i = 0;
  const worker = async () => {
    while (i < urls.length) {
      const u = urls[i++];
      try {
        if (await cache.match(u)) continue;
        const r = await fetch(u, { cache: 'reload' });
        if (r && r.ok) await cache.put(u, r);
      } catch (err) { /* keep going */ }
    }
  };
  const n = Math.max(1, Math.min(limit || 4, urls.length || 1));
  await Promise.all(Array.from({ length: n }, worker));
}

async function cachedResponse(hit) {
  const headers = new Headers(hit.headers);
  headers.set('X-MW-Cache', '1');
  return new Response(await hit.blob(), {
    status: hit.status, statusText: hit.statusText, headers,
  });
}

async function networkFirst(req, key) {
  const cache = await caches.open(V);
  try {
    const r = await fetch(req);
    if (r.ok) await cache.put(key, r.clone());
    return r;
  } catch (err) {
    const hit = await cache.match(key);
    if (hit) return cachedResponse(hit);
    return new Response(JSON.stringify({ error: 'offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json; charset=utf-8', 'X-MW-Cache': '1' },
    });
  }
}

async function cacheFirst(req, name) {
  const cache = await caches.open(name);
  const hit = await cache.match(req);
  if (hit) return hit;
  try {
    const r = await fetch(req);
    if (r.ok && r.type === 'basic') await cache.put(req, r.clone());
    return r;
  } catch (err) {
    return new Response('', { status: 504, statusText: 'offline' });
  }
}

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const cache = await caches.open(V);
    await cacheUrls(cache, SHELL, 4);
    try {
      const r = await fetch('/api/week', { cache: 'no-store' });
      if (r.ok) {
        const data = await r.clone().json();
        await cache.put('/api/week', r);
        const urls = [];
        for (const kind of ['dish', 'food']) {
          const m = (data.assets || {})[kind] || {};
          for (const id in m) {
            urls.push(`/assets/${kind}/${encodeURIComponent(id)}.webp?v=${m[id]}`);
          }
        }
        await cacheUrls(await caches.open(ASSETS), urls, 6);
      }
    } catch (err) { /* first load without a server is not fatal */ }
    try {
      const r = await fetch('/api/events', { cache: 'no-store' });
      if (r.ok) await cache.put('/api/events', r);
    } catch (err) { /* keep the shell */ }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter((k) => k !== V && k !== ASSETS)
      .map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Page loads: cached shell immediately, refresh quietly when online.
  if (req.mode === 'navigate') {
    const network = (async () => {
      try {
        const r = await fetch(req);
        if (r.ok) {
          const cache = await caches.open(V);
          await cache.put('/index.html', r.clone());
        }
        return r;
      } catch (err) {
        return null;
      }
    })();
    e.waitUntil(network.then(() => {}, () => {}));
    e.respondWith((async () => {
      const cache = await caches.open(V);
      const hit = (await cache.match('/index.html')) || (await cache.match('/'));
      if (hit) return hit;
      const fresh = await network;
      if (fresh) return fresh;
      return new Response(OFFLINE_HTML, {
        headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' },
      });
    })());
    return;
  }

  if (url.pathname === '/api/week') {
    e.respondWith(networkFirst(req, '/api/week'));
    return;
  }
  if (url.pathname === '/api/events') {
    e.respondWith(networkFirst(req, '/api/events'));
    return;
  }
  // The offline pack must always be generated fresh, never served stale.
  if (url.pathname === '/offline.html' || url.pathname === '/offline') return;

  if (url.pathname.startsWith('/assets/')) {
    e.respondWith(cacheFirst(req, ASSETS));
    return;
  }
  if (!url.pathname.startsWith('/api/')) {
    e.respondWith(cacheFirst(req, V));
  }
});







