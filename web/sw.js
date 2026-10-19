const V = 'mw-v21';
const ASSETS = 'mw-assets-v1';
const SHELL = ['/', '/index.html', '/style.css', '/app.js', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(V).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== V && k !== ASSETS).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // page navigations: fresh when online, shell when not
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).catch(() => caches.match('/index.html').then((hit) => hit || caches.match('/')))
    );
    return;
  }

  if (url.pathname === '/api/week') {
    e.respondWith(
      fetch(req)
        .then((r) => {
          const copy = r.clone();
          caches.open(V).then((c) => c.put('/api/week', copy));
          return r;
        })
        .catch(() => caches.match('/api/week'))
    );
    return;
  }

  if (url.pathname.startsWith('/assets/')) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((r) => {
        const copy = r.clone();
        caches.open(ASSETS).then((c) => c.put(req, copy));
        return r;
      }))
    );
    return;
  }

  if (!url.pathname.startsWith('/api/')) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  }
});
