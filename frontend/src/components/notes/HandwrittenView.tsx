import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { canvasApi } from "../../services/api/canvas";
import { documentsApi } from "../../services/api/documents";
import { getStrokesForPage } from "../../db/indexeddb/db";
import type { NoteMeta } from "../../types/domain";
import type { CanvasPageMeta, CanvasSessionInfo } from "../../types/api";
import { ErrorState, TranscriptionChip } from "../ui/primitives";
import type { LinePayload, RevisionInfo } from "../../services/api/documents";

/**
 * Handwritten tab (§16): the original source. Always available once a
 * source revision exists; never depends on enrichment (Rule 9).
 *
 * - canvas notes  : vector ink replayed from local IndexedDB
 * - upload notes  : page scan (when retrievable) + faithful transcription
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
  children,
}: {
  pageNumber: number;
  totalPages: number;
  onPageChange: (p: number) => void;
  zoom: number;
  onZoom: (z: number) => void;
  highlighted: boolean;
  statusChip?: React.ReactNode;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className={highlighted ? "source-page highlighted" : "source-page"} data-page={pageNumber}>
      <div className="source-page__header">
        <span>{t("notes.handwritten.page", { number: pageNumber })}</span>
        {statusChip}
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

  useEffect(() => {
    let cancelled = false;
    setSession(null);
    setError(null);
    canvasApi
      .getSession(note.refId)
      .then((s) => !cancelled && setSession(s))
      .catch(() => !cancelled && setError(t("notes.handwritten.loadPagesFailed")));
    return () => {
      cancelled = true;
    };
  }, [note.refId]);

  useEffect(() => {
    if (!highlightToken) return;
    setHighlighted(true);
    const t = window.setTimeout(() => setHighlighted(false), 1600);
    return () => window.clearTimeout(t);
  }, [highlightToken]);

  const pages = session?.pages ?? [];
  const sortedPages = useMemo(
    () => [...pages].sort((a, b) => a.page_number - b.page_number),
    [pages],
  );
  const activePageMeta: CanvasPageMeta | undefined =
    sortedPages.find((p) => p.page_number === page) ?? sortedPages[0];

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
          canvasApi
            .getSession(note.refId)
            .then(setSession)
            .catch(() => setError(t("notes.handwritten.loadPagesFailed")));
        }}
      />
    );
  }
  if (!session) {
    return (
      <div className="skeleton" style={{ height: 420, borderRadius: 14 }} aria-label={t("notes.handwritten.loadingPage")} />
    );
  }

  return (
    <PageChrome
      pageNumber={activePageMeta?.page_number ?? 1}
      totalPages={sortedPages.length}
      onPageChange={onPageChange}
      zoom={zoom}
      onZoom={setZoom}
      highlighted={highlighted}
      statusChip={<TranscriptionChip status="transcribed" />}
    >
      <div className="source-page__canvas-wrap">
        {activePageMeta && (
          <CanvasReplay key={activePageMeta.id} pageId={activePageMeta.id} zoom={zoom} />
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
  imageUrl: string | null;
  revision: RevisionInfo | null;
}

function UploadSource({ note, page, onPageChange, highlightToken }: Omit<Props, "note"> & { note: NoteMeta }) {
  const { t } = useTranslation();
  const [pages, setPages] = useState<PageData[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [highlighted, setHighlighted] = useState(false);

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
        loaded.push({ id: p.id, pageNumber: p.page_number, ocrStatus: p.ocr_status, imageUrl, revision });
      }
      setPages(loaded);
    } catch {
      setError(t("notes.detail.loadFailed"));
    }
  }, [note.refId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!highlightToken) return;
    setHighlighted(true);
    const t = window.setTimeout(() => setHighlighted(false), 1600);
    return () => window.clearTimeout(t);
  }, [highlightToken]);

  if (error) {
    return <ErrorState
        title={t("notes.detail.loadFailed")}
        message={t("errors.genericTryAgain")}
        onRetry={() => void load()}
      />;
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

  return (
    <PageChrome
      pageNumber={active.pageNumber}
      totalPages={pages.length}
      onPageChange={onPageChange}
      zoom={zoom}
      onZoom={setZoom}
      highlighted={highlighted}
      statusChip={<TranscriptionChip status={active.ocrStatus} />}
    >
      {active.imageUrl && (
        <img
          src={active.imageUrl}
          alt={t("notes.handwritten.scanAlt", { number: active.pageNumber })}
          style={{ display: "block", width: `${Math.round(BASE_WIDTH * zoom)}px`, maxWidth: "100%", margin: "0 auto" }}
        />
      )}
      <TranscriptPanel revision={active.revision} />
    </PageChrome>
  );
}

interface PageStatusWire {
  image_ref?: string | null;
}

function TranscriptPanel({ revision }: { revision: RevisionInfo | null }) {
  const { t } = useTranslation();
  if (!revision) {
    return (
      <p className="hint-text" style={{ padding: "12px 18px" }}>
        {t("notes.handwritten.transcriptPending")}
      </p>
    );
  }
  return (
    <div className="transcript-lines">
      {revision.lines.map((line: LinePayload) => (
        <div
          key={line.line_index}
          className={line.is_heading ? "transcript-line is-heading" : "transcript-line"}
        >
          <span className="transcript-line__index">{line.line_index + 1}</span>
          <span>{line.text}</span>
        </div>
      ))}
    </div>
  );
}
