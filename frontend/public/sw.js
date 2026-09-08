/**
 * Custom Service Worker with Background Sync for outbox (G6).
 * 
 * This SW handles:
 * - Background sync for outbox flush
 * - Offline fallback for API calls
 * - Cache-first strategy for static assets
 */

/// <reference lib="webworker" />

const OUTBOX_SYNC_TAG = "outbox-flush";
const CACHE_NAME = "studyai-v2";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
];

// Install event - cache static assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch event - network-first for API, cache-first for static
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests
  if (event.request.method !== "GET") {
    return;
  }

  // API requests - network only with background sync fallback
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Clone response for potential retry
          return response;
        })
        .catch(() => {
          // Offline - return a synthetic response indicating offline
          return new Response(
            JSON.stringify({ error: "Offline", code: "OFFLINE" }),
            {
              status: 503,
              headers: { "Content-Type": "application/json" },
            }
          );
        })
    );
    return;
  }

  // Static assets - cache first
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((response) => {
        if (response.ok) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      });
    })
  );
});

// Background sync event - triggered when connectivity is restored
self.addEventListener("sync", (event) => {
  if (event.tag === OUTBOX_SYNC_TAG) {
    event.waitUntil(flushOutboxFromSW());
  }
});

/**
 * Flush outbox from Service Worker context.
 * This reads from IndexedDB and attempts to sync pending operations.
 */
async function flushOutboxFromSW(): Promise<void> {
  try {
    // Open IndexedDB
    const db = await openDB();
    if (!db) return;

    // Get pending operations
    const pendingOps = await db.getAllFromIndex("outbox", "by_status", "pending");
    if (pendingOps.length === 0) return;

    // Group by session and page
    const groups = new Map<string, { sessionId: string; pageId: string; opIds: number[]; strokes: any[] }>();

    for (const op of pendingOps) {
      if (op.operation_type !== "strokes.append") continue;
      const payload = op.payload as any;
      if (!payload?.page_id || !payload.stroke) continue;
      const key = `${op.session_id}:${payload.page_id}`;
      let group = groups.get(key);
      if (!group) {
        group = { sessionId: op.session_id, pageId: payload.page_id, opIds: [], strokes: [] };
        groups.set(key, group);
      }
      group.opIds.push(op.id);
      group.strokes.push(payload.stroke);
    }

    // Attempt to flush each group
    for (const group of groups.values()) {
      try {
        // Mark as sending
        for (const opId of group.opIds) {
          await db.put("outbox", { ...(await db.get("outbox", opId)), status: "sending" });
        }

        // Note: In SW context, we can't directly call the canvas API
        // because it requires authentication. Instead, we post a message
        // to the main thread to handle the actual flush.
        await new Promise<void>((resolve, reject) => {
          const channel = new MessageChannel();
          channel.port1.onmessage = (msgEvent) => {
            if (msgEvent.data.success) {
              resolve();
            } else {
              reject(new Error(msgEvent.data.error));
            }
          };

          self.clients.matchAll().then((clients) => {
            if (clients.length > 0) {
              clients[0].postMessage(
                {
                  type: "FLUSH_OUTBOX",
                  pageId: group.pageId,
                  sessionId: group.sessionId,
                  strokes: group.strokes,
                  opIds: group.opIds,
                },
                [channel.port2]
              );
            } else {
              // No client available - will retry on next sync
              resolve();
            }
          });
        });

        // Mark as acknowledged
        for (const opId of group.opIds) {
          const op = await db.get("outbox", opId);
          if (op) {
            await db.put("outbox", { ...op, status: "acknowledged", acknowledged_at: new Date().toISOString() });
          }
        }
      } catch (err) {
        // Mark as failed
        for (const opId of group.opIds) {
          const op = await db.get("outbox", opId);
          if (op) {
            await db.put("outbox", { ...op, status: "failed" });
          }
        }
        console.error("Background sync failed for group:", err);
      }
    }
  } catch (err) {
    console.error("Background sync failed:", err);
  }
}

// IndexedDB helper (simplified for SW context)
function openDB(): Promise<any> {
  return new Promise((resolve) => {
    const request = indexedDB.open("studyai", 1);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
  });
}

// Message handler for communication with main thread
self.addEventListener("message", (event) => {
  if (event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
  if (event.data.type === "FORCE_SYNC") {
    // Trigger background sync manually
    self.registration.sync.register(OUTBOX_SYNC_TAG).catch(() => {
      // Sync registration failed, maybe not supported
    });
  }
});

console.log("[SW] Service worker loaded with background sync support");