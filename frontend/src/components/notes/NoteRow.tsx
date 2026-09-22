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
    let cancelled = false;
    documentsApi
      .pages(documentId)
      .then((pages) => {
        if (!cancelled && pages && pages.length > 0) {
          setStatus(pages[0].ocr_status || "pending");
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
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
    let cancelled = false;
    enrichmentApi
      .get(noteId)
      .then((snap) => {
        if (!cancelled) setState(snap.state);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [noteId]);
  if (state === "not_enriched") return null;
  return <EnrichmentChip state={state} />;
}
