/*
 * Kuraigal.TN - Service Worker (Phase 8: PWA / Offline Mode)
 *
 * Strategy:
 * - Static assets (CSS/JS/icons): cache-first, so the app shell loads instantly
 *   and works offline once visited.
 * - HTML pages: network-first, falling back to a cached copy or the offline
 *   page when there's no connection - so a citizen who loses signal mid-report
 *   still sees something useful instead of the browser's default error page.
 */
const CACHE_NAME = 'neighborhood-tracker-v1';
const OFFLINE_URL = '/static/offline.html';

const PRECACHE_URLS = [
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/manifest.json',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  OFFLINE_URL,
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return; // never intercept POST/form submissions

  const url = new URL(req.url);
  const isStaticAsset = url.pathname.startsWith('/static/');

  if (isStaticAsset) {
    // Cache-first for static assets.
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req).then((res) => {
        const resClone = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
        return res;
      }).catch(() => cached))
    );
  } else {
    // Network-first for pages, falling back to cache, then the offline page.
    event.respondWith(
      fetch(req)
        .then((res) => {
          const resClone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
          return res;
        })
        .catch(() => caches.match(req).then((cached) => cached || caches.match(OFFLINE_URL)))
    );
  }
});
