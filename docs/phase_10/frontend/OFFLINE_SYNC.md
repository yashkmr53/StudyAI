# Frontend Offline Sync — Phase 10

**Status:** Complete offline support with detection, SW background sync, outbox state machine

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser Runtime                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ useOnline    │  │ Offline      │  │ Service Worker       │  │
│  │ Status Hook  │  │ Banner       │  │ (sw.js)              │  │
│  │              │  │              │  │ - backgroundSync     │  │
│  │ online/      │  │ Shows when   │  │ - cache-first static │  │
│  │ offline events│ │ offline      │  │ - network-first API  │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Outbox (IndexedDB)                                       │  │
│  │ pending → sending → acknowledged                         │  │
│  │               └──→ failed → retrying → sending           │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Online/Offline Detection (G5)

### Hook: `useOnlineStatus()`
**File:** `frontend/src/hooks/useOnlineStatus.ts`

```typescript
export function useOnlineStatus(): { isOnline: boolean; wasOffline: boolean } {
  const [isOnline, setIsOnline] = useState(() => 
    typeof navigator !== "undefined" ? navigator.onLine : true
  );
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      setWasOffline(true);
    };
    const handleOffline = () => {
      setIsOnline(false);
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  return { isOnline, wasOffline };
}
```

### Component: `OfflineBanner`
**File:** `frontend/src/components/OfflineBanner.tsx`

```tsx
export function OfflineBanner(): JSX.Element | null {
  const { isOnline, wasOffline } = useOnlineStatus();

  if (isOnline && !wasOffline) return null;

  return (
    <div style={{ /* fixed top banner */ }}>
      {isOnline 
        ? "Connection restored. Syncing changes..."
        : "You are offline. Changes will sync when reconnected."
      }
    </div>
  );
}
```

**Integration:** `frontend/src/app/App.tsx`
```tsx
<BrowserRouter>
  <OfflineBanner />
  <AppRoutes />
</BrowserRouter>
```

---

## Service Worker Background Sync (G6)

### SW File: `public/sw.js`
**Features:**
- Workbox-based with `backgroundSync` for outbox flush
- Cache-first for static assets
- Network-first for API (with offline fallback)
- Background sync tag: `outbox-flush`

**Key Handlers:**
```javascript
// Install: cache static assets
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

// Fetch: cache-first static, network-first API
self.addEventListener("fetch", (event) => {
  if (event.request.url.includes("/api/")) {
    event.respondWith(networkFirstWithOfflineFallback(event.request));
  } else {
    event.respondWith(cacheFirst(event.request));
  }
});

// Background Sync
self.addEventListener("sync", (event) => {
  if (event.tag === "outbox-flush") {
    event.waitUntil(flushOutboxFromSW());
  }
});
```

### Main Thread Communication
```javascript
// SW posts message to main thread for authenticated flush
await new Promise((resolve, reject) => {
  const channel = new MessageChannel();
  channel.port1.onmessage = (msgEvent) => {
    if (msgEvent.data.success) resolve();
    else reject(new Error(msgEvent.data.error));
  };
  clients[0].postMessage({ type: "FLUSH_OUTBOX", ... }, [channel.port2]);
});
```

### Registration
**File:** `frontend/src/main.tsx`
```typescript
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then(
      (reg) => console.log("[SW] Registered:", reg.scope),
      (err) => console.error("[SW] Registration failed:", err)
    );
  });
}
```

### Vite PWA Config
**File:** `frontend/vite.config.ts`
```typescript
VitePWA({
  registerType: "autoUpdate",
  workbox: {
    navigateFallbackDenylist: [/^\/api\//],
  },
});
```

---

## Outbox State Machine (G7)

### States
```typescript
type OutboxStatus = 
  | "pending"      // Queued, not yet sent
  | "sending"      // In-flight to server
  | "acknowledged" // Server confirmed (2xx)
  | "failed"       // Server error (4xx/5xx) or network error
  | "retrying";    // Scheduled for retry
```

### Transitions
```
pending ──flushOutbox()──► sending ──2xx──► acknowledged
                              │
                              └─► 4xx/5xx/network ──► failed
                                                    │
                                                    ▼ (retry)
                                              retrying ──flushOutbox()──► sending
```

### IndexedDB Schema
```typescript
interface SyncOperation {
  id?: number;                    // Auto-increment (client_sequence)
  device_id: string;              // Persistent device UUID
  session_id: string;             // Canvas session
  operation_type: string;         // "strokes.append"
  client_sequence: number;        // Monotonic = id
  payload: unknown;               // Operation data
  idempotency_key: string;        // Server deduplication
  status: OutboxStatus;           // Current state
  created_at: string;             // ISO timestamp
  acknowledged_at?: string;       // When acknowledged
}
```

### IndexedDB Indexes
- `by_status` → for filtering by state

### Key Functions
**File:** `frontend/src/services/sync/outbox.ts`

| Function | Description |
|----------|-------------|
| `queueOperation()` | Add to outbox (status=pending) |
| `flushOutbox()` | Batch flush, handles state transitions |
| `retryFailedOperations()` | failed → retrying |
| `updateOperationStatus()` | Low-level status update |

### Zustand Store
**File:** `frontend/src/state/useOutboxStore.ts`

```typescript
interface OutboxState {
  operations: SyncOperation[];
  pendingCount: number;
  sendingCount: number;
  failedCount: number;
  acknowledgedCount: number;
  retryingCount: number;
  isFlushing: boolean;
  lastFlushError: string | null;
  refresh(): Promise<void>;
  flush(): Promise<{ acked: number; lockLost: boolean }>;
  retry(): Promise<void>;
}
```

**Persistence:** Counts persisted to localStorage (via `persist` middleware)

---

## Configuration

### Environment
```bash
# No special env vars needed for offline features
# Service worker requires HTTPS or localhost
```

### Build
```bash
npm run build  # Generates sw.js, manifest.webmanifest in dist/
```

### PWA Manifest
```json
{
  "name": "StudyAI",
  "short_name": "StudyAI",
  "display": "standalone",
  "start_url": "/",
  "theme_color": "#111827",
  "background_color": "#f9fafb"
}
```

---

## Testing

### Manual
1. Open app in Chrome
2. Open DevTools → Application → Service Workers
3. Verify SW registered
4. Open Network tab → Offline checkbox
5. Verify OfflineBanner appears
6. Create stroke offline
7. Go online → verify sync

### Unit Tests (To Add)
```bash
# frontend/src/services/storage/outbox.test.ts
# frontend/src/state/useOutboxStore.test.ts
# frontend/src/hooks/useOnlineStatus.test.ts
```

### Coverage
```bash
npm run coverage  # vitest --coverage
```

---

## Browser Support

| Feature | Chrome | Firefox | Safari | Edge |
|---------|--------|---------|--------|------|
| Service Worker | ✅ | ✅ | ✅ | ✅ |
| Background Sync | ✅ | ✅ | ❌ | ✅ |
| IndexedDB | ✅ | ✅ | ✅ | ✅ |
| navigator.onLine | ✅ | ✅ | ✅ | ✅ |

**Safari Fallback:** Timer-based flush (every 30s when online)

---

## Related Documentation

- `docs/phase_10/architecture/SYSTEM_FLOWS.md` — Offline flow diagrams
- `docs/phase_10/operations/TESTING.md` — Frontend testing
- `docs/phase_4/frontend/OFFLINE_SYNC.md` — Base specification (updated)