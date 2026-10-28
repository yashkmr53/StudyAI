import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { canvasApi } from "../../services/api/canvas";
import { documentsApi } from "../../services/api/documents";
import { getStrokesForPage } from "../../db/indexeddb/db";
import type { NoteMeta } from "../../types/domain";
import type { CanvasPageMeta, CanvasSessionInfo } from "../../types/api";
import { ErrorState, TranscriptionChip } from "../ui/primitives";
import type { LinePayload, PageStatus, RevisionInfo } from "../../services/api/documents";
import { CheckIcon, EditIcon, PlusIcon, RefreshIcon, TrashIcon } from "../ui/icons";
import { useToast } from "../ui/Toast";

/**
 * Handwritten tab (§16): the original source. Always available once a
 * source revision exists; never depends on enrichment (Rule 9).
 *
 * - canvas notes  : vector ink replayed from local IndexedDB + interactive review transcript
 * - upload notes  : page scan (when retrievable) + faithful interactive review transcript
 */

const BASE_WIDTH = 900;

interface Props {
  note: NoteMeta;
  /** 1-based page number to show. */
  page: number;
  onPageChange: (page: number) => void;
  /** Bump to flash-highlight the current page after a citation jump (§18). */
  highlightToken?: number;
}

export function HandwrittenView({ note, page, onPageChange, highlightToken }: Props) {
  return note.source === "canvas" ? (
    <CanvasSource note={note} page={page} onPageChange={onPageChange} highlightToken={highlightToken} />
  ) : (
    <UploadSource note={note} page={page} onPageChange={onPageChange} highlightToken={highlightToken} />
  );
}

/* ---------------- shared page chrome ---------------- */

function PageChrome({
  pageNumber,
  totalPages,
  onPageChange,
  zoom,
  onZoom,
  highlighted,
  statusChip,
  toggleMode,
  mode,
  children,
}: {
  pageNumber: number;
  totalPages: number;
  onPageChange: (p: number) => void;
  zoom: number;
  onZoom: (z: number) => void;
  highlighted: boolean;
  statusChip?: React.ReactNode;
  toggleMode?: (m: "split" | "source" | "transcript") => void;
  mode?: "split" | "source" | "transcript";
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className={highlighted ? "source-page highlighted" : "source-page"} data-page={pageNumber}>
      <div className="source-page__header">
        <span>{t("notes.handwritten.page", { number: pageNumber })}</span>
        {statusChip}

        {toggleMode && (
          <div className="transcript-toggle-bar" style={{ marginLeft: 12 }}>
            <button
              type="button"
              className={`transcript-toggle-btn ${mode === "split" ? "active" : ""}`}
              onClick={() => toggleMode("split")}
              title="Split view (Drawing & Transcript)"
            >
              Split
            </button>
            <button
              type="button"
              className={`transcript-toggle-btn ${mode === "source" ? "active" : ""}`}
              onClick={() => toggleMode("source")}
              title="Ink / Scan only"
            >
              Ink / Scan
            </button>
            <button
              type="button"
              className={`transcript-toggle-btn ${mode === "transcript" ? "active" : ""}`}
              onClick={() => toggleMode("transcript")}
              title="Transcript only"
            >
              Transcript
            </button>
          </div>
        )}

        <span style={{ flex: 1 }} />
        <button
          type="button"
          className="icon-btn"
          onClick={() => onPageChange(Math.max(1, pageNumber - 1))}
          disabled={pageNumber <= 1}
          aria-label={t("notes.handwritten.prevPage")}
          data-tip={t("notes.handwritten.prevPage")}
        >
          {t("notes.handwritten.prevSymbol")}
        </button>
        <span className="faint small nowrap">
          {t("notes.handwritten.pageRange", { current: pageNumber, total: totalPages })}
        </span>
        <button
          type="button"
          className="icon-btn"
          onClick={() => onPageChange(Math.min(totalPages, pageNumber + 1))}
          disabled={pageNumber >= totalPages}
          aria-label={t("notes.handwritten.nextPage")}
          data-tip={t("notes.handwritten.nextPage")}
        >
          {t("notes.handwritten.nextSymbol")}
        </button>
        <span style={{ width: 8 }} />
        <button
          type="button"
          className="icon-btn"
          onClick={() => onZoom(Math.max(0.5, Math.round((zoom - 0.1) * 10) / 10))}
          aria-label={t("notes.handwritten.zoomOut")}
          data-tip={t("notes.handwritten.zoomOut")}
        >
          {t("notes.handwritten.zoomOutSymbol")}
        </button>
        <span className="faint small nowrap">{Math.round(zoom * 100)}%</span>
        <button
          type="button"
          className="icon-btn"
          onClick={() => onZoom(Math.min(2, Math.round((zoom + 0.1) * 10) / 10))}
          aria-label={t("notes.handwritten.zoomIn")}
          data-tip={t("notes.handwritten.zoomIn")}
        >
          {t("notes.handwritten.zoomInSymbol")}
        </button>
      </div>
      {children}
    </div>
  );
}

/* ---------------- canvas source ---------------- */

function CanvasSource({
  note,
  page,
  onPageChange,
  highlightToken,
}: Omit<Props, "note"> & { note: NoteMeta }) {
  const { t } = useTranslation();
  const [session, setSession] = useState<CanvasSessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [highlighted, setHighlighted] = useState(false);
  const [mode, setMode] = useState<"split" | "source" | "transcript">("split");

  // Document page and revision state
  const [docPage, setDocPage] = useState<PageStatus | null>(null);
  const [revision, setRevision] = useState<RevisionInfo | null>(null);

  const targetSessionId = note.sessionId || note.refId || note.id;
  const documentId = session?.document || note.documentId || note.refId || note.id;

  const loadSession = useCallback(() => {
    return canvasApi
      .getSession(targetSessionId)
      .then((s) => {
        setSession(s);
        return s;
      })
      .catch(() => {
        setError(t("notes.handwritten.loadPagesFailed"));
        return null;
      });
  }, [targetSessionId, t]);

  useEffect(() => {
    let cancelled = false;
    setSession(null);
    setError(null);
    canvasApi
      .getSession(targetSessionId)
      .then((s) => {
        if (!cancelled) setSession(s);
      })
      .catch(() => {
        if (!cancelled) setError(t("notes.handwritten.loadPagesFailed"));
      });
    return () => {
      cancelled = true;
    };
  }, [targetSessionId, t]);

  const pages = session?.pages ?? [];
  const sortedPages = useMemo(
    () => [...pages].sort((a, b) => a.page_number - b.page_number),
    [pages],
  );
  const activePageMeta: CanvasPageMeta | undefined =
    sortedPages.find((p) => p.page_number === page) ?? sortedPages[0];

  // Fetch document page status and revision for the current page
  const loadPageTranscript = useCallback(async () => {
    if (!documentId) return;
    try {
      const pageStatuses = await documentsApi.pages(documentId);
      const match = pageStatuses.find(
        (p) => p.page_number === (activePageMeta?.page_number ?? page),
      );
      if (match) {
        setDocPage(match);
        if (match.current_revision_id) {
          const revs = await documentsApi.revisions(documentId, match.id);
          revs.sort((a, b) => b.revision_number - a.revision_number);
          setRevision(revs[0] ?? null);
        } else {
          setRevision(null);
        }
      }
    } catch (err) {
      console.warn("Could not load transcript for canvas note:", err);
    }
  }, [documentId, activePageMeta?.page_number, page]);

  useEffect(() => {
    void loadPageTranscript();
  }, [loadPageTranscript]);

  useEffect(() => {
    if (!highlightToken) return;
    setHighlighted(true);
    const tTimer = window.setTimeout(() => setHighlighted(false), 1600);
    return () => window.clearTimeout(tTimer);
  }, [highlightToken]);

  useEffect(() => {
    if (!activePageMeta || activePageMeta.page_number === page) return;
    onPageChange(activePageMeta.page_number);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePageMeta?.id]);

  if (error) {
    return (
      <ErrorState
        title={t("notes.detail.loadFailed")}
        message={t("errors.genericTryAgain")}
        onRetry={() => {
          setError(null);
          loadSession();
        }}
      />
    );
  }
  if (!session) {
    return (
      <div className="skeleton" style={{ height: 420, borderRadius: 14 }} aria-label={t("notes.handwritten.loadingPage")} />
    );
  }

  const effectiveStatus = docPage?.review_status || docPage?.ocr_status || "transcribed";

  return (
    <PageChrome
      pageNumber={activePageMeta?.page_number ?? 1}
      totalPages={sortedPages.length}
      onPageChange={onPageChange}
      zoom={zoom}
      onZoom={setZoom}
      highlighted={highlighted}
      statusChip={<TranscriptionChip status={effectiveStatus} />}
      toggleMode={setMode}
      mode={mode}
    >
      <div className={mode === "split" ? "source-page__split" : ""}>
        {(mode === "split" || mode === "source") && (
          <div className="source-page__canvas-wrap">
            {activePageMeta && (
              <CanvasReplay key={activePageMeta.id} pageId={activePageMeta.id} zoom={zoom} />
            )}
          </div>
        )}
        {(mode === "split" || mode === "transcript") && (
          <TranscriptPanel
            documentId={documentId}
            pageId={docPage?.id}
            reviewStatus={docPage?.review_status}
            isApproved={docPage?.is_approved}
            revision={revision}
            onRefresh={loadPageTranscript}
          />
        )}
      </div>
    </PageChrome>
  );
}

/** Replays stored ink onto a static canvas (read-only view). */
function CanvasReplay({ pageId, zoom }: { pageId: string; zoom: number }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLCanvasElement | null>(null);

  const draw = useCallback(async () => {
    const canvas = ref.current;
    if (!canvas) return;
    canvas.width = BASE_WIDTH;
    canvas.height = 620;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const strokes = await getStrokesForPage(pageId);
    for (const stroke of strokes.filter((s) => !s.deleted_at)) {
      drawPolyline(ctx, stroke.points);
    }
  }, [pageId]);

  useEffect(() => {
    void draw();
  }, [draw]);

  return (
    <canvas
      ref={ref}
      className="source-page__canvas"
      style={{ width: `${BASE_WIDTH * zoom}px`, maxWidth: "100%", height: "auto" }}
      aria-label={t("notes.handwritten.canvasAria")}
    />
  );
}

function drawPolyline(ctx: CanvasRenderingContext2D, points: number[]) {
  if (points.length < 4) return;
  ctx.strokeStyle = "#1d2433";
  ctx.lineWidth = 2.2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(points[0], points[1]);
  for (let i = 2; i + 1 < points.length; i += 2) {
    ctx.lineTo(points[i], points[i + 1]);
  }
  ctx.stroke();
}

/* ---------------- uploaded scan source ---------------- */

interface PageData {
  id: string;
  pageNumber: number;
  ocrStatus: string;
  reviewStatus?: string;
  isApproved?: boolean;
  imageUrl: string | null;
  revision: RevisionInfo | null;
}

function UploadSource({ note, page, onPageChange, highlightToken }: Omit<Props, "note"> & { note: NoteMeta }) {
  const { t } = useTranslation();
  const [pages, setPages] = useState<PageData[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [highlighted, setHighlighted] = useState(false);
  const [mode, setMode] = useState<"split" | "source" | "transcript">("split");
  const pollTimer = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const load = useCallback(async () => {
    setError(null);
    try {
      const statuses = await documentsApi.pages(note.refId);
      const loaded: PageData[] = [];
      for (const p of [...statuses].sort((a, b) => a.page_number - b.page_number)) {
        let imageUrl: string | null = null;
        const wire = p as PageStatusWire;
        if (wire.image_ref) {
          try {
            const dl = await documentsApi.getPageDownloadUrl(p.id);
            imageUrl = dl.url;
          } catch {
            imageUrl = null;
          }
        }
        let revision: RevisionInfo | null = null;
        if (p.current_revision_id) {
          const revs = await documentsApi.revisions(note.refId, p.id);
          revs.sort((a, b) => b.revision_number - a.revision_number);
          revision = revs[0] ?? null;
        }
        loaded.push({
          id: p.id,
          pageNumber: p.page_number,
          ocrStatus: p.ocr_status,
          reviewStatus: p.review_status,
          isApproved: p.is_approved,
          imageUrl,
          revision,
        });
      }
      setPages(loaded);
      return loaded;
    } catch {
      setError(t("notes.detail.loadFailed"));
      return null;
    }
  }, [note.refId, t]);

  useEffect(() => {
    void load();
    return stopPolling;
  }, [load, stopPolling]);

  // Poll while any page is pending or processing
  useEffect(() => {
    const hasPending = pages?.some(
      (p) =>
        p.ocrStatus === "pending" ||
        p.ocrStatus === "processing" ||
        p.reviewStatus === "ocr_pending" ||
        p.reviewStatus === "ocr_processing",
    );
    if (!hasPending) {
      stopPolling();
      return;
    }
    stopPolling();
    pollTimer.current = window.setInterval(async () => {
      const updated = await load();
      const stillPending = updated?.some(
        (p) =>
          p.ocrStatus === "pending" ||
          p.ocrStatus === "processing" ||
          p.reviewStatus === "ocr_pending" ||
          p.reviewStatus === "ocr_processing",
      );
      if (!stillPending) {
        stopPolling();
      }
    }, 2500);
    return stopPolling;
  }, [pages, load, stopPolling]);

  useEffect(() => {
    if (!highlightToken) return;
    setHighlighted(true);
    const tTimer = window.setTimeout(() => setHighlighted(false), 1600);
    return () => window.clearTimeout(tTimer);
  }, [highlightToken]);

  if (error) {
    return (
      <ErrorState
        title={t("notes.detail.loadFailed")}
        message={t("errors.genericTryAgain")}
        onRetry={() => void load()}
      />
    );
  }
  if (!pages) {
    return <div className="skeleton" style={{ height: 420, borderRadius: 14 }} aria-label={t("notes.handwritten.loadingNote")} />;
  }

  const active = pages.find((p) => p.pageNumber === page) ?? pages[0];
  if (!active) {
    return (
      <ErrorState
        title={t("notes.handwritten.noPagesTitle")}
        message={t("notes.handwritten.noPagesMessage")}
      />
    );
  }

  const effectiveStatus = active.reviewStatus || active.ocrStatus;

  return (
    <PageChrome
      pageNumber={active.pageNumber}
      totalPages={pages.length}
      onPageChange={onPageChange}
      zoom={zoom}
      onZoom={setZoom}
      highlighted={highlighted}
      statusChip={<TranscriptionChip status={effectiveStatus} />}
      toggleMode={setMode}
      mode={mode}
    >
      <div className={mode === "split" ? "source-page__split" : ""}>
        {(mode === "split" || mode === "source") && active.imageUrl && (
          <div style={{ overflow: "auto", padding: 12 }}>
            <img
              src={active.imageUrl}
              alt={t("notes.handwritten.scanAlt", { number: active.pageNumber })}
              style={{ display: "block", width: `${Math.round(BASE_WIDTH * zoom)}px`, maxWidth: "100%", margin: "0 auto" }}
            />
          </div>
        )}
        {(mode === "split" || mode === "transcript") && (
          <TranscriptPanel
            documentId={note.refId}
            pageId={active.id}
            reviewStatus={active.reviewStatus}
            isApproved={active.isApproved}
            revision={active.revision}
            onRefresh={load}
          />
        )}
      </div>
    </PageChrome>
  );
}

interface PageStatusWire {
  image_ref?: string | null;
}

interface TranscriptPanelProps {
  documentId: string;
  pageId?: string;
  reviewStatus?: string;
  isApproved?: boolean;
  revision: RevisionInfo | null;
  onRefresh: () => void | Promise<any>;
}

function TranscriptPanel({
  documentId,
  pageId,
  reviewStatus,
  isApproved,
  revision,
  onRefresh,
}: TranscriptPanelProps) {
  const { t } = useTranslation();
  const toast = useToast();

  const [isEditing, setIsEditing] = useState(false);
  const [draftLines, setDraftLines] = useState<Array<{ line_index: number; text: string; is_heading?: boolean }>>([]);
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);
  const [retrying, setRetrying] = useState(false);

  // Initialize draft lines when revision changes
  useEffect(() => {
    if (revision?.lines) {
      setDraftLines(
        revision.lines.map((l) => ({
          line_index: l.line_index,
          text: l.text,
          is_heading: l.is_heading,
        })),
      );
    } else {
      setDraftLines([]);
    }
    setIsEditing(false);
  }, [revision?.id]);

  const handleStartEdit = () => {
    if (revision?.lines && revision.lines.length > 0) {
      setDraftLines(
        revision.lines.map((l) => ({
          line_index: l.line_index,
          text: l.text,
          is_heading: l.is_heading,
        })),
      );
    } else {
      setDraftLines([{ line_index: 0, text: "" }]);
    }
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    if (revision?.lines) {
      setDraftLines(
        revision.lines.map((l) => ({
          line_index: l.line_index,
          text: l.text,
          is_heading: l.is_heading,
        })),
      );
    }
    setIsEditing(false);
  };

  const handleLineChange = (index: number, text: string) => {
    setDraftLines((prev) => {
      const next = [...prev];
      if (next[index]) {
        next[index] = { ...next[index], text };
      }
      return next;
    });
  };

  const handleAddLine = (atIndex?: number) => {
    setDraftLines((prev) => {
      const next = [...prev];
      const insertAt = atIndex !== undefined ? atIndex + 1 : next.length;
      next.splice(insertAt, 0, { line_index: insertAt, text: "" });
      return next.map((l, i) => ({ ...l, line_index: i }));
    });
  };

  const handleDeleteLine = (index: number) => {
    setDraftLines((prev) => {
      const next = prev.filter((_, i) => i !== index);
      return next.map((l, i) => ({ ...l, line_index: i }));
    });
  };

  const handleMoveLine = (index: number, direction: -1 | 1) => {
    setDraftLines((prev) => {
      const target = index + direction;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      const temp = next[index];
      next[index] = next[target];
      next[target] = temp;
      return next.map((l, i) => ({ ...l, line_index: i }));
    });
  };

  const handleToggleHeading = (index: number) => {
    setDraftLines((prev) => {
      const next = [...prev];
      if (next[index]) {
        next[index] = { ...next[index], is_heading: !next[index].is_heading };
      }
      return next;
    });
  };

  const handleSaveAndApprove = async () => {
    if (!pageId) return;
    const cleanLines = draftLines
      .map((l) => ({ ...l, text: l.text.trim() }))
      .filter((l) => l.text.length > 0)
      .map((l, i) => ({ ...l, line_index: i }));

    if (cleanLines.length === 0) {
      toast.error("Please enter at least one line of text.");
      return;
    }

    setSaving(true);
    try {
      await documentsApi.submitEdit(documentId, pageId, cleanLines);
      toast.success("Transcript updated and approved! Indexed for AI search.");
      setIsEditing(false);
      await onRefresh();
    } catch (err: any) {
      toast.error(err?.message || "Failed to save transcript revision.");
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!pageId) return;
    setApproving(true);
    try {
      await documentsApi.approvePage(documentId, pageId);
      toast.success("Transcript approved! Indexed for AI search.");
      await onRefresh();
    } catch (err: any) {
      toast.error(err?.message || "Failed to approve transcript.");
    } finally {
      setApproving(false);
    }
  };

  const handleRetryOcr = async () => {
    if (!pageId) return;
    setRetrying(true);
    try {
      await documentsApi.retryPageOcr(documentId, pageId);
      toast.success("OCR re-transcription started.");
      await onRefresh();
    } catch (err: any) {
      toast.error(err?.message || "Failed to retry OCR.");
    } finally {
      setRetrying(false);
    }
  };

  if (!revision) {
    return (
      <div className="transcript-review-panel">
        <p className="hint-text" style={{ padding: "12px 18px" }}>
          {t("notes.handwritten.transcriptPending")}
        </p>
        {pageId && (
          <div style={{ padding: "0 18px" }}>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleRetryOcr}
              disabled={retrying}
            >
              <RefreshIcon size={14} /> Re-run OCR
            </button>
          </div>
        )}
      </div>
    );
  }

  const approved = isApproved || reviewStatus === "approved";
  const needsReview = reviewStatus === "needs_review";

  return (
    <div className="transcript-review-panel">
      {/* Review Status Banner */}
      <div className={`transcript-review-banner ${approved ? "approved" : needsReview ? "needs-review" : "pending-review"}`}>
        <div>
          <div style={{ fontWeight: 650, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
            {approved ? (
              <>
                <CheckIcon size={15} />
                <span>Transcript Approved</span>
              </>
            ) : needsReview ? (
              <span style={{ color: "#d97706" }}>⚠ Needs Review</span>
            ) : (
              <span style={{ color: "#2563eb" }}>Awaiting Review</span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
            {approved
              ? "This transcript is approved and indexed in your knowledge base."
              : "Review and approve this transcript to enable AI search and chat citations."}
          </div>
        </div>

        <div className="transcript-review-banner__actions">
          {!isEditing && (
            <>
              {!approved && (
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={handleApprove}
                  disabled={approving}
                  style={{ background: "#059669", borderColor: "#059669" }}
                >
                  <CheckIcon size={14} /> {approving ? "Approving..." : "Approve Transcript"}
                </button>
              )}
              <button
                type="button"
                className="btn btn--secondary"
                onClick={handleStartEdit}
              >
                <EditIcon size={14} /> Edit Transcript
              </button>
              {!approved && (
                <button
                  type="button"
                  className="icon-btn"
                  onClick={handleRetryOcr}
                  disabled={retrying}
                  title="Re-run OCR"
                >
                  <RefreshIcon size={14} />
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Main content: Edit Mode or View Mode */}
      {isEditing ? (
        <div className="transcript-edit-wrap">
          <div style={{ marginBottom: 10, fontSize: 12, color: "var(--text-secondary)" }}>
            Correct misread words, reorder lines, or add missing text. Saving will automatically approve and re-index the note.
          </div>
          {draftLines.map((line, idx) => (
            <div key={idx} className="transcript-line-edit">
              <span className="transcript-line__index">{idx + 1}</span>
              <input
                type="text"
                value={line.text}
                onChange={(e) => handleLineChange(idx, e.target.value)}
                placeholder="Line text..."
                style={line.is_heading ? { fontWeight: 650 } : {}}
              />
              <button
                type="button"
                className={`icon-btn ${line.is_heading ? "active" : ""}`}
                onClick={() => handleToggleHeading(idx)}
                title={line.is_heading ? "Heading (click to make body)" : "Make heading"}
                style={{ fontSize: 11, fontWeight: 700, padding: "2px 6px" }}
              >
                H
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={() => handleMoveLine(idx, -1)}
                disabled={idx === 0}
                title="Move up"
              >
                ↑
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={() => handleMoveLine(idx, 1)}
                disabled={idx === draftLines.length - 1}
                title="Move down"
              >
                ↓
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={() => handleDeleteLine(idx)}
                title="Delete line"
                style={{ color: "#dc2626" }}
              >
                <TrashIcon size={13} />
              </button>
            </div>
          ))}

          <div style={{ display: "flex", gap: 10, marginTop: 12, justifyContent: "space-between" }}>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => handleAddLine()}
              style={{ fontSize: 12 }}
            >
              <PlusIcon size={14} /> Add Line
            </button>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={handleCancelEdit}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleSaveAndApprove}
                disabled={saving}
                style={{ background: "#059669", borderColor: "#059669" }}
              >
                <CheckIcon size={14} /> {saving ? "Saving..." : "Save & Approve"}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="transcript-lines" style={{ padding: 0 }}>
          {revision.lines.length === 0 ? (
            <p className="hint-text" style={{ padding: "8px 0" }}>
              No text detected on this page.
            </p>
          ) : (
            revision.lines.map((line: LinePayload) => (
              <div
                key={line.line_index}
                className={line.is_heading ? "transcript-line is-heading" : "transcript-line"}
              >
                <span className="transcript-line__index">{line.line_index + 1}</span>
                <span>{line.text}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
