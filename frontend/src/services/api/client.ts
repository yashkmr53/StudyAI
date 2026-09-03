import { ApiError, type ApiErrorBody } from "../../types/api";

const API_BASE = "/api/v1";

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  retry?: boolean;
}

let accessToken: string | null = null;
let refreshToken: string | null = null;
let onSessionExpired: (() => void) | null = null;
let activeProfileId: string | null = null;

export function setActiveProfileId(profileId: string | null): void {
  activeProfileId = profileId;
}

export function setTokens(access: string | null, refresh: string | null): void {
  accessToken = access;
  refreshToken = refresh;
  if (access && refresh) {
    localStorage.setItem("studyai.access", access);
    localStorage.setItem("studyai.refresh", refresh);
  } else {
    localStorage.removeItem("studyai.access");
    localStorage.removeItem("studyai.refresh");
  }
}

/** Restore persisted tokens on app start. */
export function loadPersistedTokens(): void {
  accessToken = localStorage.getItem("studyai.access");
  refreshToken = localStorage.getItem("studyai.refresh");
}

export function getRefreshToken(): string | null {
  return refreshToken;
}

export function setSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler;
}

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshToken) return false;
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: refreshToken }),
  });
  if (!response.ok) {
    setTokens(null, null);
    return false;
  }
  const data = (await response.json()) as { access: string; refresh?: string };
  accessToken = data.access;
  if (data.refresh) refreshToken = data.refresh;
  return true;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, retry = true } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  if (activeProfileId) headers["X-Active-Profile"] = activeProfileId;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && auth && retry && (await refreshAccessToken())) {
    return apiRequest<T>(path, { ...options, retry: false });
  }

  if (response.status === 401 && auth) {
    onSessionExpired?.();
  }

  if (response.status === 204) return undefined as T;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const errorBody = (payload as ApiErrorBody | null)?.error ?? {
      code: "INTERNAL_ERROR",
      message: response.statusText || "Request failed",
      request_id: "req_unknown",
      details: {},
    };
    // Prefer concrete field messages ("You already have a subject called
    // "DSA".") over the generic envelope message ("Validation failed.").
    const detailMessages = Object.values(errorBody.details ?? {})
      .flat()
      .map((m) => String(m))
      .filter(Boolean);
    throw new ApiError(response.status, {
      ...errorBody,
      message: detailMessages[0] ?? errorBody.message,
    });
  }
  return payload as T;
}

/**
 * Server-Sent Event streamed from a fetch response.
 *
 * `EventSource` cannot send custom Authorization headers, so we consume
 * the `text/event-stream` response with a streaming `fetch` and parse the
 * wire format (`event:` / `data:` lines separated by blank lines)
 * ourselves.
 */
export interface SseEvent<T = unknown> {
  event: string;
  data: T;
}

export interface StreamRequestOptions extends Omit<RequestOptions, "retry"> {
  signal?: AbortSignal;
}

export async function* apiStream<T = unknown>(
  path: string,
  options: StreamRequestOptions = {},
): AsyncGenerator<SseEvent<T>, void, void> {
  const { method = "POST", body, auth = true, signal } = options;

  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  if (activeProfileId) headers["X-Active-Profile"] = activeProfileId;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  if (response.status === 401 && auth && (await refreshAccessToken())) {
    yield* apiStream<T>(path, { method, body, auth, signal });
    return;
  }

  if (response.status === 401 && auth) {
    onSessionExpired?.();
  }

  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const errorBody = (payload as ApiErrorBody | null)?.error ?? {
      code: "INTERNAL_ERROR",
      message: response.statusText || "Request failed",
      request_id: "req_unknown",
      details: {},
    };
    const detailMessages = Object.values(errorBody.details ?? {})
      .flat()
      .map((m) => String(m))
      .filter(Boolean);
    throw new ApiError(response.status, {
      ...errorBody,
      message: detailMessages[0] ?? errorBody.message,
    });
  }

  if (!response.body) {
    throw new ApiError(500, {
      code: "STREAM_UNAVAILABLE",
      message: "Streaming response body unavailable.",
      request_id: "req_unknown",
      details: {},
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let currentEvent = "message";
  const dataLines: string[] = [];

  const flush = (): SseEvent<T> | null => {
    if (dataLines.length === 0) return null;
    const dataStr = dataLines.join("\n");
    dataLines.length = 0;
    let data: T;
    try {
      data = dataStr ? (JSON.parse(dataStr) as T) : (undefined as unknown as T);
    } catch {
      data = dataStr as unknown as T;
    }
    const evt: SseEvent<T> = { event: currentEvent || "message", data };
    currentEvent = "message";
    return evt;
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIndex = buffer.indexOf("\n\n");
      while (sepIndex !== -1) {
        const rawEvent = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        currentEvent = "message";
        dataLines.length = 0;

        for (const line of rawEvent.split("\n")) {
          if (!line || line.startsWith(":")) continue;
          const colonIdx = line.indexOf(":");
          const field = colonIdx === -1 ? line : line.slice(0, colonIdx);
          let value = colonIdx === -1 ? "" : line.slice(colonIdx + 1);
          if (value.startsWith(" ")) value = value.slice(1);
          if (field === "event") {
            currentEvent = value;
          } else if (field === "data") {
            dataLines.push(value);
          }
        }

        const evt = flush();
        if (evt) yield evt;
        sepIndex = buffer.indexOf("\n\n");
      }
    }

    // Drain trailing buffered content as a final event if any.
    if (buffer.trim()) {
      currentEvent = "message";
      dataLines.length = 0;
      for (const line of buffer.split("\n")) {
        if (!line || line.startsWith(":")) continue;
        const colonIdx = line.indexOf(":");
        const field = colonIdx === -1 ? line : line.slice(0, colonIdx);
        let value = colonIdx === -1 ? "" : line.slice(colonIdx + 1);
        if (value.startsWith(" ")) value = value.slice(1);
        if (field === "event") currentEvent = value;
        else if (field === "data") dataLines.push(value);
      }
      const evt = flush();
      if (evt) yield evt;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore
    }
  }
}