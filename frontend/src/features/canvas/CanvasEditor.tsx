import { useCallback, useEffect, useRef, useState } from "react";
import { getStrokesForPage, putStroke } from "../../db/indexeddb/db";
import { flushOutbox, queueOperation, registerSyncContext } from "../../services/sync/outbox";
import { useAuthStore } from "../auth/authStore";
import { useCanvasStore } from "./canvasStore";

const CANVAS_W = 900;
const CANVAS_H = 620;
const HEARTBEAT_MS = 25_000; // spec §5: heartbeat every 20–30 s
const FLUSH_MS = 3_000;

interface SessionListItem {
  id: string;
  created_at?: string;
  pages: { id: string; page_number: number; is_finalized: boolean }[];
}

export function CanvasEditor() {
  const profileId = useAuthStore((s) => s.profile?.id ?? null);
  const {
    deviceId, sessionId, pages, activePageId, generation, lockLost,
    ensureDevice, newSession, openSession, addPage, setActivePage,
    applySession, markLockLost, recoverLock, finalizeActive,
  } = useCanvasStore();

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const currentPointsRef = useRef<number[]>([]);
  const sequenceRef = useRef<Record<string, number>>({});
  const stateRef = useRef({ deviceId, generation, sessionId });
  stateRef.current = { deviceId, generation, sessionId };

  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [status, setStatus] = useState<string>("");

  /* ---- sync context for the outbox transport ---- */
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

  /* ---- drawing ---- */
  const redraw = useCallback(async (pageId: string) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
    const strokes = await getStrokesForPage(pageId);
    let maxSeq = -1;
    for (const stroke of strokes) {
      maxSeq = Math.max(maxSeq, stroke.sequence_order);
      drawPolyline(ctx, stroke.points);
    }
    sequenceRef.current[pageId] = maxSeq + 1;
  }, []);

  useEffect(() => {
    if (activePageId) void redraw(activePageId);
  }, [activePageId, redraw]);

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
    currentPointsRef.current = [x, y];
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const [x, y] = toCanvasPoint(e);
    const pts = currentPointsRef.current;
    const lx = pts[pts.length - 2];
    const ly = pts[pts.length - 1];
    const ctx = canvasRef.current?.getContext("2d");
    if (ctx) drawSegment(ctx, lx, ly, x, y);
    pts.push(x, y);
  }

  async function onPointerUp() {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    const pageId = activePageId;
    const sessionId_ = sessionId;
    const points = currentPointsRef.current;
    if (!pageId || !sessionId_ || points.length < 4) return;

    const seq = sequenceRef.current[pageId] ?? 0;
    sequenceRef.current[pageId] = seq + 1;
    const stroke = {
      id: crypto.randomUUID(),
      sequence_order: seq,
      points,
      client_idempotency_key: crypto.randomUUID(),
    };
    // §4: strokes go to IndexedDB immediately; sync is decoupled.
    await putStroke({
      id: stroke.id,
      page_id: pageId,
      sequence_order: stroke.sequence_order,
      points,
      updated_at: new Date().toISOString(),
    });
    await queueOperation(sessionId_, "strokes.append", { page_id: pageId, stroke });
    void flushOutbox();
  }

  /* ---- timers: heartbeat + flush (§4/§5) ---- */
  useEffect(() => {
    if (!sessionId || lockLost) return;
    const beat = window.setInterval(async () => {
      try {
        const s = await import("../../services/api/canvas").then((m) =>
          m.canvasApi.heartbeat(sessionId, { device_id: stateRef.current.deviceId, lock_generation: stateRef.current.generation }),
        );
        applySession(s);
        // keep the active page selection stable across heartbeats
        if (activePageId) setActivePage(activePageId);
      } catch {
        /* transient — next beat retries */
      }
    }, HEARTBEAT_MS);
    const flush = window.setInterval(() => void flushOutbox(), FLUSH_MS);
    return () => {
      window.clearInterval(beat);
      window.clearInterval(flush);
    };
  }, [sessionId, lockLost, activePageId, applySession, setActivePage]);

  useEffect(() => {
    const flushOnLeave = () => void flushOutbox();
    document.addEventListener("visibilitychange", flushOnLeave);
    window.addEventListener("beforeunload", flushOnLeave);
    return () => {
      document.removeEventListener("visibilitychange", flushOnLeave);
      window.removeEventListener("beforeunload", flushOnLeave);
    };
  }, []);

  /* ---- session bootstrap ---- */
  async function startNewSession() {
    if (!profileId) return;
    setStatus("Creating session…");
    try {
      await newSession(profileId);
      setStatus("");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Failed to create session");
    }
  }

  async function loadSessions() {
    try {
      const { canvasApi } = await import("../../services/api/canvas");
      const listing = await canvasApi.listSessions();
      setSessions(listing.results);
    } catch {
      setStatus("Could not load sessions");
    }
  }

  useEffect(() => {
    ensureDevice();
    void loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activePage = pages.find((p) => p.id === activePageId);

  if (!sessionId) {
    return (
      <div className="placeholder">
        <h1>Canvas</h1>
        <p>Handwritten notes with offline autosave and fenced single-writer sync.</p>
        <button onClick={startNewSession} disabled={!profileId}>New sheet</button>
        {status && <p className="error-text">{status}</p>}
        <h3 style={{ marginTop: "2rem" }}>Recent sheets</h3>
        {sessions.length === 0 && <p style={{ color: "#6b7280" }}>No sheets yet.</p>}
        <ul>
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => openSession(s.id).catch(() => setStatus("Could not open session"))}
                style={{ margin: "0.25rem 0" }}
              >
                Sheet from {s.created_at ? new Date(s.created_at).toLocaleString() : s.id}
                {" · "}
                {s.pages.length} page(s)
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="placeholder">
      <h1>Canvas</h1>
      {lockLost && (
        <div style={{ background: "#fef3c7", border: "1px solid #f59e0b", padding: "0.75rem", borderRadius: 8, marginBottom: "1rem" }}>
          This sheet is now controlled by another device.
          <button style={{ marginLeft: "1rem" }} onClick={() => recoverLock().catch(() => markLockLost())}>
            Take over
          </button>
        </div>
      )}
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
        {pages.map((p) => (
          <button
            key={p.id}
            onClick={() => setActivePage(p.id)}
            style={{ background: p.id === activePageId ? "#2563eb" : "#111827" }}
          >
            Page {p.page_number}{p.is_finalized ? " ✓" : ""}
          </button>
        ))}
        <button onClick={() => addPage().catch(() => setStatus("Could not add page"))} disabled={lockLost}>
          + Page
        </button>
        <button
          onClick={() => finalizeActive().catch(() => setStatus("Finalize failed"))}
          disabled={lockLost || !activePage || activePage.is_finalized}
        >
          Finalize page
        </button>
      </div>
      <canvas
        ref={canvasRef}
        width={CANVAS_W}
        height={CANVAS_H}
        style={{
          background: "#fff",
          border: "1px solid #d1d5db",
          borderRadius: 8,
          touchAction: "none",
          cursor: lockLost || activePage?.is_finalized ? "not-allowed" : "crosshair",
          maxWidth: "100%",
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
      <p style={{ color: "#6b7280", fontSize: "0.85rem" }}>
        {activePage?.is_finalized
          ? "This page is finalized and read-only."
          : lockLost
            ? "Drawing disabled until you take over the session."
            : "Draw below — strokes autosave locally and sync in the background."}
      </p>
      {status && <p className="error-text">{status}</p>}
    </div>
  );
}

function drawSegment(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) {
  ctx.strokeStyle = "#111827";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
}

function drawPolyline(ctx: CanvasRenderingContext2D, points: number[]) {
  ctx.strokeStyle = "#111827";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  ctx.beginPath();
  for (let i = 0; i + 1 < points.length; i += 2) {
    if (i === 0) ctx.moveTo(points[0], points[1]);
    else ctx.lineTo(points[i], points[i + 1]);
  }
  ctx.stroke();
}
