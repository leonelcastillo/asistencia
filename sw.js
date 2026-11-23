// Asistencia OCAS: primero internet (datos frescos); sin señal, lo último guardado.
const CACHE = 'asistencia-v1';
const BASE = ['./', 'index.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'semanas.json'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASE)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(caches.keys()
  .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  const clave = new Request(u.origin + u.pathname);  // sin el ?hora del cache-busting
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const c2 = r.clone(); caches.open(CACHE).then(c => c.put(clave, c2)); } return r; })
    .catch(() => caches.match(clave).then(g => g || (e.request.mode === 'navigate' ? caches.match('index.html') : Response.error()))));
});
