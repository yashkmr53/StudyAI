import { apiRequest } from "./client";
import type { CanvasPageMeta, CanvasSessionInfo, StrokePayload } from "../../types/api";

export interface LockContext {
  device_id: string;
  lock_generation: number;
}

export const canvasApi = {
  createSession(profileId: string, deviceId: string): Promise<CanvasSessionInfo> {
    return apiRequest<CanvasSessionInfo>("/canvas/sessions", {
      method: "POST",
      body: { profile: profileId, device_id: deviceId },
    });
  },

  listSessions(): Promise<{ count: number; results: CanvasSessionInfo[] }> {
    return apiRequest("/canvas/sessions");
  },

  getSession(id: string): Promise<CanvasSessionInfo> {
    return apiRequest(`/canvas/sessions/${id}`);
  },

  heartbeat(id: string, ctx: LockContext): Promise<CanvasSessionInfo> {
    return apiRequest(`/canvas/sessions/${id}/heartbeat`, { method: "POST", body: ctx });
  },

  takeover(id: string, deviceId: string): Promise<CanvasSessionInfo> {
    return apiRequest(`/canvas/sessions/${id}/takeover`, {
      method: "POST",
      body: { device_id: deviceId },
    });
  },

  createPage(sessionId: string, pageNumber: number, ctx: LockContext): Promise<CanvasPageMeta & { session: string }> {
    return apiRequest("/canvas/pages", {
      method: "POST",
      body: {
        session: sessionId,
        page_number: pageNumber,
        device_id: ctx.device_id,
        lock_generation: ctx.lock_generation,
      },
    });
  },

  pushStrokes(
    pageId: string,
    ctx: LockContext,
    strokes: StrokePayload[],
  ): Promise<{ created: string[]; duplicate_keys: string[] }> {
    return apiRequest(`/canvas/pages/${pageId}/strokes`, {
      method: "POST",
      body: { ...ctx, strokes },
    });
  },

  finalizePage(pageId: string, ctx: LockContext): Promise<{ page_id: string; is_finalized: boolean; already_finalized: boolean; document_id?: string | null; revision_id?: string | null; job_id?: string | null }> {
    return apiRequest(`/canvas/pages/${pageId}/finalize`, { method: "POST", body: ctx });
  },
};
