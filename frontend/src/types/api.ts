export interface User {
  id: string;
  email: string;
  date_joined?: string;
}

export interface Profile {
  id: string;
  name: string;
  created_at?: string;
  updated_at?: string;
}

export interface Subject {
  id: string;
  profile: string;
  name: string;
  created_at?: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface RegisterResponse extends AuthTokens {
  user: User;
  profile: Profile;
}

/** API error contract (architecture §61). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
    details: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody["error"]) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.requestId = body.request_id;
    this.details = body.details;
  }
}

/* ---- Canvas (Phase 2) ---- */

export interface CanvasPageMeta {
  id: string;
  page_number: number;
  is_finalized: boolean;
}

export interface CanvasSessionInfo {
  id: string;
  profile: string;
  subject?: string | null;
  device_id: string;
  lock_holder: string | null;
  lock_generation: number;
  lock_expires_at: string | null;
  document?: string | null;
  pages: CanvasPageMeta[];
  created_at?: string;
  updated_at?: string;
}

export interface StrokePayload {
  id?: string;
  sequence_order: number;
  points: number[];
  client_idempotency_key: string;
}
