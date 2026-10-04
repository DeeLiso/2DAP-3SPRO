const VERSION = 'v9';
const STATIC_CACHE = `2d-parser-static-${VERSION}`;
const OFFLINE_URL = '/static/offline.html';

const PRECACHE = [
    '/static/manifest.json',
    '/static/icon-192.png',
    '/static/icon-512.png',
    '/static/css/mobile.css',
    '/static/css/dark.css',
    '/static/js/pwa.js',
    '/static/js/dark.js',
    OFFLINE_URL
];

const CDN_HOSTS = [
    'cdn.tailwindcss.com',
    'cdnjs.cloudflare.com',
    'fonts.googleapis.com',
    'fonts.gstatic.com'
];

const isApi = (path) =>
    path.startsWith('/api/') ||
    path === '/api' ||
    path.includes('/api/');

self.addEventListener('install', (e) => {
    e.waitUntil(
        (async () => {
            const cache = await caches.open(STATIC_CACHE);
            await Promise.allSettled(
                PRECACHE.map((url) => cache.add(new Request(url, { cache: 'reload' })))
            );
            await self.skipWaiting();
        })()
    );
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        (async () => {
            const keys = await caches.keys();
            await Promise.all(
                keys
                    .filter((k) => k.startsWith('2d-parser') && k !== STATIC_CACHE)
                    .map((k) => caches.delete(k))
            );
            await self.clients.claim();
        })()
    );
});

const offlineJson = () =>
    new Response(JSON.stringify({ ok: false, error: 'offline' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' }
    });

const staleWhileRevalidate = async (request) => {
    const cache = await caches.open(STATIC_CACHE);
    const cached = await cache.match(request);

    const network = fetch(request)
        .then((response) => {
            if (response && (response.ok || response.type === 'opaque')) {
                cache.put(request, response.clone());
            }
            return response;
        })
        .catch(() => null);

    if (cached) {
        network.catch(() => null);
        return cached;
    }

    const response = await network;
    return response || offlineJson();
};

const networkFirst = async (request) => {
    const cache = await caches.open(STATIC_CACHE);
    try {
        const response = await fetch(request);
        if (response && response.ok) cache.put(request, response.clone());
        return response;
    } catch (err) {
        const cached = await cache.match(request);
        if (cached) return cached;
        throw err;
    }
};

const APP_BUNDLE = ['/static/app/app.js', '/static/app/app.css'];

self.addEventListener('fetch', (e) => {
    const request = e.request;
    if (request.method !== 'GET') return;

    let url;
    try {
        url = new URL(request.url);
    } catch (err) {
        return;
    }

    if (isApi(url.pathname)) {
        e.respondWith(
            fetch(request).catch(() =>
                new Response(JSON.stringify({ ok: false, error: 'offline' }), {
                    status: 503,
                    headers: { 'Content-Type': 'application/json' }
                })
            )
        );
        return;
    }

    if (request.mode === 'navigate') {
        e.respondWith(
            fetch(request).catch(() => caches.match(OFFLINE_URL).then((r) => r || offlineJson()))
        );
        return;
    }

    const sameOrigin = url.origin === self.location.origin;
    if (!sameOrigin && !CDN_HOSTS.includes(url.hostname)) return;

    if (sameOrigin && APP_BUNDLE.includes(url.pathname)) {
        e.respondWith(
            networkFirst(request).catch(() =>
                new Response('', { status: 504, headers: { 'Content-Type': 'text/plain' } })
            )
        );
        return;
    }

    e.respondWith(staleWhileRevalidate(request));
});
