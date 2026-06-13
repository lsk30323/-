/* 한능검 2급 합격 마스터 — 서비스워커 (오프라인 캐시) */
const CACHE = 'hanguksa2-v1';
const ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './data/exam-1.js',
  './data/exam-2.js',
  './data/exam-3.js',
  './data/exam-4.js',
  './data/exam-5.js',
  './data/concepts.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then(
      (hit) =>
        hit ||
        fetch(e.request)
          .then((resp) => {
            const copy = resp.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
            return resp;
          })
          .catch(() => caches.match('./index.html')),
    ),
  );
});
