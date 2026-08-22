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
    throw new ApiError(response.status, errorBody);
  }
  return payload as T;
}
