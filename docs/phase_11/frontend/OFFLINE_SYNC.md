# Phase 11 — Frontend Provider Integration

**Date:** 2026-08-23

---

## Overview

Frontend interacts with providers indirectly through backend APIs. No direct provider SDKs in frontend.

---

## File Upload Flow

```
Frontend → Backend API → Presigned URL → MinIO/S3
```

### 1. Get Upload URL
```typescript
// frontend/src/services/storage/upload.ts
async function getUploadUrl(key: string, contentType: string): Promise<string> {
  const response = await fetch(`/api/v1/storage/upload-url/?key=${key}&content_type=${contentType}`, {
    headers: { Authorization: `Bearer ${accessToken}` }
  });
  const data = await response.json();
  return data.upload_url;
}
```

### 2. Upload Directly to Storage
```typescript
async function uploadFile(uploadUrl: string, file: File): Promise<void> {
  await fetch(uploadUrl, {
    method: 'PUT',
    body: file,
    headers: { 'Content-Type': file.type }
  });
}
```

### 3. Complete Upload (notify backend)
```typescript
async function completeUpload(key: string): Promise<void> {
  await fetch('/api/v1/storage/complete/', {
    method: 'POST',
    headers: { 
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`
    },
    body: JSON.stringify({ key })
  });
}
```

---

## File Download Flow

```
Frontend → Backend API → Presigned URL → MinIO/S3
```

```typescript
async function getDownloadUrl(key: string): Promise<string> {
  const response = await fetch(`/api/v1/storage/download-url/?key=${key}`, {
    headers: { Authorization: `Bearer ${accessToken}` }
  });
  const data = await response.json();
  return data.download_url;
}

// Use directly in <a>, <img>, or fetch
const url = await getDownloadUrl(key);
window.open(url, '_blank'); // or set as img src
```

---

## Offline Support (Phase 10 + Phase 11)

### Service Worker Background Sync
```typescript
// frontend/public/sw.js (Workbox)
import { backgroundSync } from 'workbox-background-sync';

const bgSync = new backgroundSync.BackgroundSyncPlugin('outbox-queue', {
  maxRetentionTime: 24 * 60 // 24 hours
});

registerRoute(
  ({ url }) => url.pathname.startsWith('/api/v1/strokes/'),
  new NetworkOnly({
    plugins: [bgSync]
  }),
  'POST'
);
```

### Outbox State Transitions (Phase 10 G7)
```typescript
// frontend/src/services/storage/outbox.ts
enum OutboxStatus {
  PENDING = 'pending',
  SENDING = 'sending',
  ACKNOWLEDGED = 'acknowledged',
  FAILED = 'failed',
  RETRYING = 'retrying'
}

// Transitions:
// PENDING → SENDING (flush starts)
// SENDING → ACKNOWLEDGED (2xx response)
// SENDING → FAILED (4xx/5xx non-retryable)
// FAILED → RETRYING (retryable error, after backoff)
// RETRYING → SENDING (retry attempt)
```

### Online/Offline Detection (Phase 10 G5)
```typescript
// frontend/src/hooks/useOnlineStatus.ts
function useOnlineStatus(): { isOnline: boolean; wasOffline: boolean } {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    const handleOnline = () => { setIsOnline(true); setWasOffline(true); };
    const handleOffline = () => { setIsOnline(false); };
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return { isOnline, wasOffline };
}
```

### Offline Banner Component
```tsx
// frontend/src/components/OfflineBanner.tsx
function OfflineBanner() {
  const { isOnline, wasOffline } = useOnlineStatus();
  
  if (isOnline && !wasOffline) return null;
  
  return (
    <div className="fixed top-0 left-0 right-0 bg-amber-500 text-white p-2 text-center z-50">
      {isOnline 
        ? "Connection restored — syncing..." 
        : "You're offline — changes will sync when reconnected"}
    </div>
  );
}
```

---

## Email Integration

### Password Reset Request
```typescript
// frontend/src/features/auth/PasswordResetRequest.tsx
async function requestPasswordReset(email: string): Promise<void> {
  await fetch('/api/v1/auth/password-reset/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  // Backend sends email via get_email_provider()
}
```

### Local Development (Mailpit)
- Web UI: `http://localhost:8025`
- API: `http://localhost:8025/api/v1/messages`
- View captured password reset emails during development

---

## Health Checks

```typescript
// frontend/src/services/health.ts
async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch('/healthz');
    return response.ok;
  } catch {
    return false;
  }
}

async function checkStorageHealth(): Promise<boolean> {
  try {
    const response = await fetch('/api/v1/storage/health/');
    return response.ok;
  } catch {
    return false;
  }
}
```

---

## Configuration

### Environment Variables (Vite)
```env
# .env.local
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_BASE_URL=ws://localhost:8000/ws
```

### Build-time Config
```typescript
// frontend/src/config/api.ts
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || '/ws';
```

---

## Testing

### Mock Providers in Tests
```typescript
// frontend/src/services/storage/__mocks__/upload.ts
export const mockUploadUrl = 'https://mock-storage.example.com/upload';
export const mockDownloadUrl = 'https://mock-storage.example.com/download';

// frontend/src/services/__mocks__/api.ts
export function mockFetch(response: any, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(response),
    status: ok ? 200 : 400
  });
}
```

### Offline Testing
```typescript
// frontend/src/__tests__/offline.test.ts
import { render, screen } from '@testing-library/react';
import { OfflineBanner } from '../components/OfflineBanner';

test('shows offline banner when offline', () => {
  Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
  window.dispatchEvent(new Event('offline'));
  
  render(<OfflineBanner />);
  expect(screen.getByText("You're offline")).toBeInTheDocument();
});

test('shows restored banner when online', () => {
  Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
  window.dispatchEvent(new Event('online'));
  
  render(<OfflineBanner />);
  expect(screen.getByText("Connection restored")).toBeInTheDocument();
});
```

---

## PWA Configuration (Phase 10)

```typescript
// frontend/vite.config.ts
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    VitePWA({
      registerType: 'autoUpdate',
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/api\.example\.com\/api\/v1\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 }
            }
          }
        ]
      },
      manifest: {
        name: 'StudyAI',
        short_name: 'StudyAI',
        theme_color: '#2563eb',
        background_color: '#ffffff',
        display: 'standalone',
        icons: [
          { src: '/icon-192.png', sizes: '192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512', type: 'image/png' }
        ]
      }
    })
  ]
});
```

---

## Provider-Specific Frontend Notes

### OCR
- No direct frontend integration
- Backend handles OCR during document ingestion
- Frontend only uploads images

### LLM
- No direct frontend integration
- All LLM calls go through backend (enrichment, chat, questions)
- Frontend receives structured results

### Embeddings
- No direct frontend integration
- Embeddings generated server-side during ingestion/enrichment
- Frontend uses search results from retrieval API

### Storage
- Direct MinIO/S3 upload/download via presigned URLs
- Frontend never sends file bytes through backend (after upload URL)
- Large file support without backend memory pressure

### Email
- No direct frontend integration
- Password reset request triggers backend email
- Local dev: Check Mailpit UI at `http://localhost:8025`