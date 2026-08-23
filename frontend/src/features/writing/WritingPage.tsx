import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { canvasApi } from "../../services/api/canvas";
import { flushOutbox, queueOperation, registerSyncContext } from "../../services/sync/outbox";
import { getStrokesForPage, putStroke } from "../../db/indexeddb/db";
import { useAuthStore } from "../../features/auth/authStore";
import { useCanvasStore } from "../../features/canvas/canvasStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { UNFILED_FOLDER_ID, type NoteMeta } from "../../types/domain";
import { drawSegment, drawStroke, strokeNear } from "./ink";
import { WritingToolbar, type ToolbarState } from "./WritingToolbar";

/**
 * Write flow (§21–§22).
 *
 * Opened via `navigate("/subjects/:id/write", { state: { returnTo, folderId? } })`.
 * - Subject-level writes land in Unfiled (Rule 13).
 * - Folder-level writes land in that folder.
 * - "Done" returns the user to wherever Write was opened from — never to
 *   Enriched and never auto-opening the new note (Rule 15 / §22).
 *
 * Ink persists to IndexedDB immediately; the offline outbox syncs it in the
 * background with fenced single-writer locking.
 */

const CANVAS_W = 900;
const CANVAS_H = 620;
const HEARTBEAT_MS = 25_000;
const FLUSH_MS = 3_000;

interface WriteLocationState {
  returnTo?: string;
  folderId?: string | null;
}

type UndoOp =
  | { kind: "add"; strokes: StrokeSnapshot[] }
  | { kind: "erase"; records: { id: string; wasDeleted: boolean }[] };

interface StrokeSnapshot {
  record: Omit<StrokeRecordLocal, "updated_at">;
}

type StrokeRecordLocal = {
  id: string;
  page_id: string;
  sequence_order: number;
  points: number[];
  pressures?: number[];
  tool?: "pen" | "highlighter";
  color?: string;
  width?: number;
};

export function WritingPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as WriteLocationState;
  const returnTo = state.returnTo ?? `/subjects/${subjectId}`;

  const profileId = useAuthStore((s) => s.profile?.id ?? null);
  const registerCanvasNote = useWorkspaceStore((s) => s.registerCanvasNote);
  const subjects = useWorkspaceStore((s) => s.subjects);
  const folders = useWorkspaceStore((s) => s.folders);
  const { t } = useTranslation();
  const subjectName = subjects.find((s) => s.id === subjectId)?.name ?? t("writer.subjectFallback");

  const {
    deviceId, sessionId, pages, activePageId, generation, lockLost,
    ensureDevice, newSession, addPage, setActivePage,
    applySession, markLockLost, recoverLock, finalizeActive, reset,
  } = useCanvasStore();

  const [note, setNote] = useState<NoteMeta | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  /* ---- tool state ---- */
  const [toolbar, setToolbar] = useState<ToolbarState>({
    tool: "pen",
    color: "#1d2433",
    sizeIndex: 1,
    canUndo: false,
    canRedo: false,
  });
  const undoStack = useRef<UndoOp[]>([]);
  const redoStack = useRef<UndoOp[]>([]);

  function pushUndo(op: UndoOp) {
    undoStack.current.push(op);
    if (undoStack.current.length > 100) undoStack.current.shift();
    redoStack.current = [];
    refreshToolFlags();
  }
  function refreshToolFlags() {
    setToolbar((t) => ({
      ...t,
      canUndo: undoStack.current.length > 0,
      canRedo: redoStack.current.length > 0,
    }));
  }

  /* ---- canvas refs ---- */
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const currentPointsRef = useRef<number[]>([]);
  const currentPressuresRef = useRef<number[]>([]);
  const sequenceRef = useRef<Record<string, number>>({});
  const eraserTrailRef = useRef<Array<[number, number]>>([]);
  const erasedInStrokeRef = useRef<Map<string, boolean>>(new Map());
  const stateRef = useRef({ deviceId, generation, sessionId });
  stateRef.current = { deviceId, generation, sessionId };
  const toolRef = useRef(toolbar);
  toolRef.current = toolbar;

  /* ---- boot: create session + note record ---- */
  const bootedRef = useRef(false);
  const noteRef = useRef<NoteMeta | null>(null);
  noteRef.current = note;

  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;
    async function boot() {
      if (!profileId || !subjectId) return;
      try {
        ensureDevice();
        await newSession(profileId);
        const created = await registerCanvasNote({
          sessionId: useCanvasStore.getState().sessionId!,
          profileId,
          subjectId,
          folderId: state.folderId ?? UNFILED_FOLDER_ID,
        });
        setNote(created);
      } catch {
        setBootError(t("writer.bootError"));
      }
    }
    void boot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId, subjectId]);

  // Abandoned empty sessions shouldn't leave phantom notes behind.
  useEffect(() => {
    return () => {
      const mountedNote = noteRef.current;
      if (mountedNote && !leftWithInk.current) {
        void import("../../db/indexeddb/db").then((m) => m.deleteNote(mountedNote.id));
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- sync context for outbox transport ---- */
  useEffect(() => {
    registerSyncContext(
      () => {
        const { deviceId: d, generation: g, sessionId: s } = stateRef.current;
        return s ? { device_id: d, lock_generation: g } : null;
      },
      () => markLockLost(),
    );
    return () => registerSyncContext(null);
  }, [markLockLost]);

  /* ---- redraw current page from local ink ---- */
  const redraw = useCallback(async (pageId: string) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = CANVAS_W;
    canvas.height = CANVAS_H;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
    const strokes = await getStrokesForPage(pageId);
    let maxSeq = -1;
    for (const stroke of strokes.filter((s) => !s.deleted_at)) {
      maxSeq = Math.max(maxSeq, stroke.sequence_order);
      drawStroke(ctx, stroke as never);
    }
    sequenceRef.current[pageId] = maxSeq + 1;
  }, []);

  useEffect(() => {
    if (activePageId) void redraw(activePageId);
  }, [activePageId, redraw]);

  /* ---- timers: heartbeat + flush ---- */
  useEffect(() => {
    if (!sessionId || lockLost) return;
    const beat = window.setInterval(async () => {
      try {
        const s = await canvasApi.heartbeat(sessionId, {
          device_id: stateRef.current.deviceId,
          lock_generation: stateRef.current.generation,
        });
        applySession(s);
      } catch {
        /* transient */
      }
    }, HEARTBEAT_MS);
    const flush = window.setInterval(() => void flushOutbox(), FLUSH_MS);
    return () => {
      window.clearInterval(beat);
      window.clearInterval(flush);
    };
  }, [sessionId, lockLost, applySession]);

  useEffect(() => {
    const flushOnLeave = () => void flushOutbox();
    document.addEventListener("visibilitychange", flushOnLeave);
    window.addEventListener("beforeunload", flushOnLeave);
    return () => {
      document.removeEventListener("visibilitychange", flushOnLeave);
      window.removeEventListener("beforeunload", flushOnLeave);
    };
  }, []);

  /* ---- pointer handling ---- */
  function toCanvasPoint(e: React.PointerEvent<HTMLCanvasElement>): [number, number] {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const scaleX = CANVAS_W / rect.width;
    const scaleY = CANVAS_H / rect.height;
    return [(e.clientX - rect.left) * scaleX, (e.clientY - rect.top) * scaleY];
  }

  function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (lockLost || !activePageId || pages.find((p) => p.id === activePageId)?.is_finalized) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drawingRef.current = true;
    const [x, y] = toCanvasPoint(e);
    const tool = toolRef.current.tool;

    if (tool === "eraser") {
      eraserTrailRef.current = [[x, y]];
      erasedInStrokeRef.current = new Map();
      return;
    }

    currentPointsRef.current = [x, y];
    currentPressuresRef.current = [e.pressure > 0 ? e.pressure : 0.6];
    const ctx = canvasRef.current?.getContext("2d");
    if (ctx) {
      drawSegment(
        ctx,
        { tool: tool === "highlighter" ? "highlighter" : "pen", color: toolRef.current.color, width: widthFor(toolRef.current) },
        x, y, x, y,
      );
    }
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const [x, y] = toCanvasPoint(e);
    const tool = toolRef.current.tool;

    if (tool === "eraser") {
      const trail = eraserTrailRef.current;
      const last = trail[trail.length - 1];
      trail.push([x, y]);
      eraseNear(activePageId!, last[0], last[1], x, y);
      return;
    }

    const pts = currentPointsRef.current;
    const lx = pts[pts.length - 2];
    const ly = pts[pts.length - 1];
    const ctx = canvasRef.current?.getContext("2d");
    if (ctx) {
      drawSegment(
        ctx,
        { tool: tool === "highlighter" ? "highlighter" : "pen", color: toolRef.current.color, width: widthFor(toolRef.current) },
        lx, ly, x, y,
      );
    }
    pts.push(x, y);
    currentPressuresRef.current.push(e.pressure > 0 ? e.pressure : 0.6);
  }

  function widthFor(t: ToolbarState): number {
    return t.tool === "highlighter"
      ? [12, 18, 26][t.sizeIndex] ?? 18
      : [2, 3.5, 5.5][t.sizeIndex] ?? 3.5;
  }

  async function onPointerUp(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    const pageId = activePageId;
    const sessionId_ = sessionId;
    if (!pageId || !sessionId_) return;

    const tool = toolRef.current.tool;

    if (tool === "eraser") {
      const erased = [...erasedInStrokeRef.current.entries()];
      if (erased.length > 0) {
        pushUndo({ kind: "erase", records: erased.map(([id]) => ({ id, wasDeleted: false })) });
      }
      eraserTrailRef.current = [];
      return;
    }

    const points = currentPointsRef.current;
    const pressures = currentPressuresRef.current;
    if (points.length < 4) return;

    const seq = sequenceRef.current[pageId] ?? 0;
    sequenceRef.current[pageId] = seq + 1;
    const stroke = {
      id: crypto.randomUUID(),
      page_id: pageId,
      sequence_order: seq,
      points,
      pressures,
      tool: tool === "highlighter" ? ("highlighter" as const) : ("pen" as const),
      color: toolRef.current.color,
      width: widthFor(toolRef.current),
    };

    // §4: ink goes to IndexedDB immediately; syncing is decoupled.
    await putStroke({ ...stroke, updated_at: new Date().toISOString() });
    await queueOperation(sessionId_, "strokes.append", {
      page_id: pageId,
      stroke: {
        id: stroke.id,
        sequence_order: stroke.sequence_order,
        points: stroke.points,
        client_idempotency_key: crypto.randomUUID(),
      },
    });
    void flushOutbox();

    pushUndo({
      kind: "add",
      strokes: [{ record: { ...stroke } }],
    });

    void e;
  }

  /* ---- eraser hit test between two trail points ---- */
  async function eraseNear(pageId: string, x1: number, y1: number, x2: number, y2: number) {
    const strokes = await getStrokesForPage(pageId);
    let changed = false;
    for (const stroke of strokes) {
      if (stroke.deleted_at) continue;
      if (segmentIntersects(stroke, x1, y1, x2, y2)) {
        await putStroke({ ...stroke, deleted_at: new Date().toISOString() });
        erasedInStrokeRef.current.set(stroke.id, true);
        changed = true;
      }
    }
    if (changed) void redraw(pageId);
  }

  function segmentIntersects(stroke: { points: number[] }, x1: number, y1: number, x2: number, y2: number): boolean {
    // sample along the eraser segment
    const steps = Math.max(1, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / 8));
    for (let i = 0; i <= steps; i++) {
      const px = x1 + ((x2 - x1) * i) / steps;
      const py = y1 + ((y2 - y1) * i) / steps;
      if (strokeNear(stroke as never, px, py, 10)) return true;
    }
    return false;
  }

  /* ---- undo / redo ---- */
  async function applyUndo() {
    const op = undoStack.current.pop();
    if (!op || !activePageId) return;
    if (op.kind === "add") {
      for (const snap of op.strokes) {
        const existing = await findStroke(snap.record.id);
        if (existing) {
          await putStroke({ ...existing, deleted_at: new Date().toISOString() });
        }
      }
      redoStack.current.push(op);
    } else {
      for (const rec of op.records) {
        const existing = await findStroke(rec.id);
        if (existing && existing.deleted_at) {
          const { deleted_at: _drop, ...rest } = existing;
          void _drop;
          await putStroke(rest);
        }
      }
      redoStack.current.push(op);
    }
    refreshToolFlags();
    void redraw(activePageId);
  }

  async function applyRedo() {
    const op = redoStack.current.pop();
    if (!op || !activePageId) return;
    if (op.kind === "add") {
      for (const snap of op.strokes) {
        const existing = await findStroke(snap.record.id);
        if (existing) {
          const { deleted_at: _drop, ...rest } = existing;
          void _drop;
          await putStroke(rest);
        }
      }
    } else {
      for (const rec of op.records) {
        const existing = await findStroke(rec.id);
        if (existing) {
          await putStroke({ ...existing, deleted_at: new Date().toISOString() });
        }
      }
    }
    undoStack.current.push(op);
    refreshToolFlags();
    void redraw(activePageId);
  }

  async function findStroke(id: string) {
    const all = await getStrokesForPage(activePageId!);
    return all.find((s) => s.id === id) ?? null;
  }

  /* ---- keyboard shortcuts ---- */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) void applyRedo();
        else void applyUndo();
      } else if (meta && e.key.toLowerCase() === "y") {
        e.preventDefault();
        void applyRedo();
      } else if (!meta && e.key.toLowerCase() === "p") {
        setToolbar((t) => ({ ...t, tool: "pen" }));
      } else if (!meta && e.key.toLowerCase() === "h") {
        setToolbar((t) => ({ ...t, tool: "highlighter" }));
      } else if (!meta && e.key.toLowerCase() === "e") {
        setToolbar((t) => ({ ...t, tool: "eraser" }));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePageId]);

  /* ---- leaving (§22): return to origin ---- */
  const leftWithInk = useRef(false);
  async function finishWriting() {
    leftWithInk.current =
      activePageId != null &&
      (await getStrokesForPage(activePageId)).some((s) => !s.deleted_at);
    try {
      const active = pages.find((p) => p.id === activePageId);
      if (active && !active.is_finalized) await finalizeActive();
      await flushOutbox();
    } catch {
      /* finalize is best-effort; ink is safe locally */
    }
    reset();
    navigate(returnTo, { replace: false });
  }

  /* ---------------- render ---------------- */

  if (bootError) {
    return (
      <div className="content__inner">
        <p className="form-error">{bootError}</p>
        <button type="button" className="btn btn--secondary" onClick={() => navigate(returnTo)}>
          {t("writer.goBack")}
        </button>
      </div>
    );
  }

  const activePage = pages.find((p) => p.id === activePageId);

  return (
    <div className="writer">
      <header className="writer-toolbar" style={{ justifyContent: "space-between" }}>
        <div className="row" style={{ gap: 10 }}>
          <button
            type="button"
            className="icon-btn"
            onClick={() => void finishWriting()}
            aria-label={t("writer.closeAria")}
            data-tip={t("writer.back")}
          >
            ‹
          </button>
          <strong style={{ fontSize: 13.5 }}>
            {note?.title ?? t("writer.untitledNote")}
          </strong>
          <span className="faint small nowrap">
            {subjectName}
            {(state.folderId ?? UNFILED_FOLDER_ID) === UNFILED_FOLDER_ID
              ? ` · ${t("workspace.unfiled")}`
              : (() => {
                  const targetFolder = folders.find((f) => f.id === state.folderId);
                  return targetFolder ? ` · ${targetFolder.name}` : "";
                })()}
          </span>
        </div>
        <button type="button" className="btn btn--primary btn--sm" onClick={() => void finishWriting()}>
          {t("writer.done")}
        </button>
      </header>

      <WritingToolbar
        state={toolbar}
        onTool={(tool) => setToolbar((t) => ({ ...t, tool }))}
        onColor={(color) => setToolbar((t) => ({ ...t, color }))}
        onSize={(sizeIndex) => setToolbar((t) => ({ ...t, sizeIndex }))}
        onUndo={() => void applyUndo()}
        onRedo={() => void applyRedo()}
      />

      {lockLost && (
        <div className="banner-warning" role="alert">
          {t("writer.lockLost")}
          <span style={{ flex: 1 }} />
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            onClick={() => recoverLock().catch(() => markLockLost())}
          >
            {t("common.actions.takeOver")}
          </button>
        </div>
      )}

      <div className="writer-canvas-area">
        <div className="writer-paper" style={{ width: CANVAS_W, maxWidth: "100%" }}>
          <canvas
            ref={canvasRef}
            width={CANVAS_W}
            height={CANVAS_H}
            style={{
              width: "100%",
              cursor:
                lockLost || activePage?.is_finalized
                  ? "not-allowed"
                  : toolbar.tool === "eraser"
                    ? "cell"
                    : "crosshair",
              touchAction: "none",
            }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            aria-label={t("writer.canvasAria")}
          />
        </div>
      </div>

      <footer className="writer-statusbar">
        <div className="page-tabs" role="tablist" aria-label={t("writer.pagesAria")}>
          {pages.map((p) => (
            <button
              key={p.id}
              type="button"
              role="tab"
              aria-selected={p.id === activePageId}
              className={p.id === activePageId ? "page-tab active" : "page-tab"}
              onClick={() => setActivePage(p.id)}
            >
              {t("writer.pageTab", { number: p.page_number })}
              {p.is_finalized ? t("writer.finalizedMark") : ""}
            </button>
          ))}
          <button
            type="button"
            className="page-tab"
            disabled={lockLost}
            data-tip={t("writer.addPageTip")}
            onClick={() => addPage().catch(() => undefined)}
          >
            {t("writer.addPage")}
          </button>
        </div>
        <span style={{ flex: 1 }} />
        <span>
          {activePage?.is_finalized
            ? t("writer.statusFinalized")
            : lockLost
              ? t("writer.statusLockLost")
              : t("writer.statusSyncing")}
        </span>
      </footer>
    </div>
  );
}
