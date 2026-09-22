import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { NoteMeta } from "../../types/domain";
import { EnrichmentChip, timeAgo, TranscriptionChip } from "../ui/primitives";
import { useServices } from "../modules/ModuleContext";
import { NoteIcon } from "../ui/icons";
import { documentsApi } from "../../services/api/documents";
import { enrichmentApi } from "../../services/api/enrichment";

/**
 * One note in a folder listing. Status chips follow the active module:
 * transcription always (Rule 9); enrichment only when the module exposes
 * EnrichmentService (Rule 5).
 */
export function NoteRow({ note, to }: { note: NoteMeta; to: string }) {
  const services = useServices();
  const { t } = useTranslation();
  const docId = note.refId || note.id;

  return (
    <Link to={to} className="note-row" style={{ textDecoration: "none" }}>
      <span className="sidebar__item-icon">
        <NoteIcon size={16} />
      </span>
      <span className="grow" style={{ minWidth: 0 }}>
        <span className="note-row__title" style={{ display: "block", color: "var(--text)" }}>
          {note.title}
        </span>
        <span className="note-row__meta">
          {t("notes.row.updated", {
            time: timeAgo(note.updatedAt) ?? "",
          })}
          {" · "}
          {note.source === "canvas"
            ? t("notes.source.canvas")
            : t("notes.source.upload")}
        </span>
      </span>
      <span className="note-row__end">
        {note.source === "upload" && <NoteOcrStatusChip documentId={docId} />}
        {services.enrichment && <EnrichmentStateChip noteId={docId} />}
      </span>
    </Link>
  );
}

function NoteOcrStatusChip({ documentId }: { documentId: string }) {
  const [status, setStatus] = useState<string>("pending");
  useEffect(() => {
    let timer: number | null = null;
    let cancelled = false;

    async function check() {
      try {
        const pages = await documentsApi.pages(documentId);
        if (cancelled || !pages || pages.length === 0) return;
        const s = pages[0].ocr_status || "pending";
        setStatus(s);
        if (s === "completed" || s === "failed" || s === "needs_review") {
          if (timer) {
            window.clearInterval(timer);
            timer = null;
          }
        }
      } catch {
        // non-fatal
      }
    }

    void check();
    timer = window.setInterval(check, 3000);

    return () => {
      cancelled = true;
      if (timer) {
        window.clearInterval(timer);
        timer = null;
      }
    };
  }, [documentId]);
  return <TranscriptionChip status={status} />;
}

/**
 * Enrichment chip resolved from the live enrichment snapshot. Kept lazy:
 * rows render instantly and the chip hydrates when the fetch resolves.
 */
function EnrichmentStateChip({ noteId }: { noteId: string }) {
  const [state, setState] = useState<string>("not_enriched");
  useEffect(() => {
    let timer: number | null = null;
    let cancelled = false;

    async function check() {
      try {
        const snap = await enrichmentApi.get(noteId);
        if (cancelled) return;
        setState(snap.state);
        if (snap.state === "enriched" || snap.state === "out_of_date" || snap.state === "failed") {
          if (timer) {
            window.clearInterval(timer);
            timer = null;
          }
        }
      } catch {
        // non-fatal
      }
    }

    void check();
    timer = window.setInterval(check, 4000);

    return () => {
      cancelled = true;
      if (timer) {
        window.clearInterval(timer);
        timer = null;
      }
    };
  }, [noteId]);
  if (state === "not_enriched") return null;
  return <EnrichmentChip state={state} />;
}
