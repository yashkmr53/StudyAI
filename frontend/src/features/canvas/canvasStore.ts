import { create } from "zustand";
import { canvasApi } from "../../services/api/canvas";
import { newDeviceId } from "../../services/sync/outbox";
import type { CanvasPageMeta, CanvasSessionInfo } from "../../types/api";

interface CanvasState {
  deviceId: string;
  sessionId: string | null;
  session: CanvasSessionInfo | null;
  pages: CanvasPageMeta[];
  activePageId: string | null;
  generation: number;
  lockLost: boolean;
  lastFinalizedDocumentId: string | null;
  lastFinalizedRevisionId: string | null;

  ensureDevice: () => string;
  newSession: (profileId: string, subjectId?: string | null) => Promise<void>;
  openSession: (sessionId: string) => Promise<void>;
  addPage: () => Promise<void>;
  setActivePage: (pageId: string) => void;
  applySession: (session: CanvasSessionInfo) => void;
  markLockLost: () => void;
  recoverLock: () => Promise<void>;
  finalizeActive: (title?: string) => Promise<{ page_id: string; is_finalized: boolean; already_finalized: boolean; document_id?: string | null; revision_id?: string | null; job_id?: string | null } | null>;
  reset: () => void;
}

export const useCanvasStore = create<CanvasState>((set, get) => ({
  deviceId: "",
  sessionId: null,
  session: null,
  pages: [],
  activePageId: null,
  generation: 1,
  lockLost: false,
  lastFinalizedDocumentId: null,
  lastFinalizedRevisionId: null,

  ensureDevice() {
    const existing = localStorage.getItem("studyai.device_id");
    const id = existing ?? newDeviceId();
    set({ deviceId: id });
    return id;
  },

  async newSession(profileId, subjectId) {
    const device = get().ensureDevice();
    const session = await canvasApi.createSession(profileId, device, subjectId);
    get().applySession(session);
    await get().addPage();
  },

  async openSession(sessionId) {
    const session = await canvasApi.getSession(sessionId);
    get().applySession(session);
  },

  async addPage() {
    const { sessionId, generation, deviceId, pages } = get();
    if (!sessionId) return;
    const nextNumber = pages.reduce((max, p) => Math.max(max, p.page_number), 0) + 1;
    const page = await canvasApi.createPage(
      sessionId,
      nextNumber,
      { device_id: deviceId, lock_generation: generation },
    );
    set((s) => ({
      pages: [...s.pages, { id: page.id, page_number: page.page_number, is_finalized: false }],
      activePageId: page.id,
    }));
  },

  setActivePage(pageId) {
    set({ activePageId: pageId });
  },

  applySession(session) {
    set({
      sessionId: session.id,
      session,
      pages: session.pages,
      generation: session.lock_generation,
      lockLost: false,
      activePageId: session.pages[0]?.id ?? null,
    });
  },

  markLockLost() {
    set({ lockLost: true });
  },

  async recoverLock() {
    const { sessionId, deviceId } = get();
    if (!sessionId) return;
    const session = await canvasApi.takeover(sessionId, deviceId);
    get().applySession(session);
  },

  async finalizeActive(title?: string) {
    const { activePageId, deviceId, generation, pages } = get();
    if (!activePageId) return null;
    const result = await canvasApi.finalizePage(activePageId, {
      device_id: deviceId,
      lock_generation: generation,
      ...(title ? { title } : {}),
    });
    if (result.is_finalized) {
      set({
        pages: pages.map((p) => (p.id === activePageId ? { ...p, is_finalized: true } : p)),
        lastFinalizedDocumentId: result.document_id ?? null,
        lastFinalizedRevisionId: result.revision_id ?? null,
      });
    }
    return result;
  },

  reset() {
    set({ sessionId: null, session: null, pages: [], activePageId: null, lockLost: false, lastFinalizedDocumentId: null, lastFinalizedRevisionId: null });
  },
}));
