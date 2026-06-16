/* 한능검 2급 합격 마스터 — 서비스워커 (오프라인 캐시) */
const CACHE = 'hanguksa2-v5';
const ASSETS = [
  './',
  './index.html',
  './firebase-sync.js',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './data/exam-1.js',
  './data/exam-2.js',
  './data/exam-3.js',
  './data/exam-4.js',
  './data/exam-5.js',
  './data/exam-6.js',
  './data/exam-7.js',
  './data/exam-8.js',
  './data/exam-9.js',
  './data/exam-10.js',
  './data/exam-11.js',
  './data/exam-12.js',
  './data/exam-13.js',
  './data/exam-14.js',
  './data/exam-15.js',
  './data/exam-16.js',
  './data/exam-17.js',
  './data/exam-18.js',
  './data/exam-19.js',
  './data/exam-20.js',
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
