/**
 * MK OS Service Worker
 * =====================
 * Provides offline support with a cache-first strategy for static assets
 * and network-first strategy for API calls.
 *
 * API responses are cached with a timestamp header and expire after
 * API_CACHE_MAX_AGE_MS (5 minutes by default). Stale cache entries
 * are served only when the network is unavailable, giving the UI a
 * chance to display a "data may be stale" indicator.
 */

const CACHE_NAME = "mk-os-v2";
const STATIC_ASSETS = ["/", "/index.html"];

// Maximum age for cached API responses (5 minutes)
const API_CACHE_MAX_AGE_MS = 5 * 60 * 1000;

// Install: pre-cache the app shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

/**
 * Check if a cached API response is still fresh based on the
 * x-sw-cached-at header we add when storing it.
 */
function isApiCacheFresh(response) {
  const cachedAt = response.headers.get("x-sw-cached-at");
  if (!cachedAt) return false;
  const age = Date.now() - parseInt(cachedAt, 10);
  return age < API_CACHE_MAX_AGE_MS;
}

/**
 * Clone a response and add a cache timestamp header.
 */
function addCacheTimestamp(response) {
  const headers = new Headers(response.headers);
  headers.set("x-sw-cached-at", String(Date.now()));
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: headers,
  });
}

// Fetch: cache-first for static assets, network-first for API calls
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Network-first for API calls with time-based cache expiry
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Cache successful GET responses with a timestamp
          if (request.method === "GET" && response.status === 200) {
            const stamped = addCacheTimestamp(response.clone());
            caches.open(CACHE_NAME).then((cache) => cache.put(request, stamped));
          }
          return response;
        })
        .catch(async () => {
          // Network failed: serve from cache only if still fresh
          const cached = await caches.match(request);
          if (cached && isApiCacheFresh(cached)) {
            return cached;
          }
          // Return stale cache with a warning header so the UI can indicate staleness
          if (cached) {
            const headers = new Headers(cached.headers);
            headers.set("x-sw-stale", "true");
            return new Response(cached.body, {
              status: cached.status,
              statusText: cached.statusText,
              headers: headers,
            });
          }
          // No cache at all
          return new Response(JSON.stringify({ error: "Network unavailable" }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          });
        })
    );
    return;
  }

  // Cache-first for static assets (JS, CSS, images, fonts)
  if (
    request.method === "GET" &&
    (url.pathname.endsWith(".js") ||
      url.pathname.endsWith(".css") ||
      url.pathname.endsWith(".svg") ||
      url.pathname.endsWith(".png") ||
      url.pathname.endsWith(".woff2") ||
      url.pathname.endsWith(".woff"))
  ) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.status === 200) {
              const clone = response.clone();
              caches.open(CACHE_NAME).then((cache) =>
                cache.put(request, clone)
              );
            }
            return response;
          })
      )
    );
    return;
  }

  // Network-first for navigation requests (HTML pages)
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match("/index.html").then((cached) => cached || caches.match("/"))
      )
    );
    return;
  }

  // Default: try network, fall back to cache
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});
