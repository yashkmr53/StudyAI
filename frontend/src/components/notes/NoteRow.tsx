import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { UNFILED_FOLDER_ID, type NoteMeta } from "../../types/domain";
import { EnrichmentChip, timeAgo, TranscriptionChip } from "../ui/primitives";
import { useServices } from "../modules/ModuleContext";
import { NoteIcon, EditIcon, FolderIcon, TrashIcon } from "../ui/icons";
import { documentsApi } from "../../services/api/documents";
import { enrichmentApi } from "../../services/api/enrichment";
import { ActionMenu } from "../ui/ActionMenu";
import { RenameDialog } from "../ui/RenameDialog";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { MoveNoteDialog } from "./MoveNoteDialog";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { useToast } from "../ui/Toast";

/**
 * One note in a folder listing. Status chips follow the active module:
 * transcription always (Rule 9); enrichment only when the module exposes
 * EnrichmentService (Rule 5).
 */
export function NoteRow({ note, to }: { note: NoteMeta; to: string }) {
  const services = useServices();
  const { t } = useTranslation();
  const toast = useToast();
  const notes = useWorkspaceStore((s) => s.notes);
  const renameNote = useWorkspaceStore((s) => s.renameNote);
  const removeNote = useWorkspaceStore((s) => s.removeNote);

  const [renameOpen, setRenameOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const docId = note.refId || note.id;

  async function handleRename(newTitle: string) {
    try {
      await renameNote(note.id, newTitle);
      toast.success(t("crud.success.noteRenamed", "Note renamed"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("crud.errors.renameNote", "Failed to rename note"));
      throw err;
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await removeNote(note.id);
      toast.success(t("crud.success.noteDeleted", "Note deleted"));
      setDeleteOpen(false);
    } catch (err) {
      toast.error(t("crud.errors.deleteNote", "Failed to delete note"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <Link to={to} className="note-row" style={{ textDecoration: "none" }}>
        <span className="sidebar__item-icon">
          <NoteIcon size={16} />
        </span>
        <span className="grow" style={{ minWidth: 0 }}>
          <span
            className="note-row__title"
            style={{ display: "block", color: "var(--text)" }}
            title={note.title}
          >
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
          <ActionMenu
            ariaLabel={t("crud.noteActions", { defaultValue: "Note actions" })}
            items={[
              {
                key: "rename",
                label: t("crud.rename", "Rename"),
                icon: <EditIcon size={14} />,
                onClick: () => setRenameOpen(true),
              },
              {
                key: "move",
                label: t("crud.moveToFolder", "Move to folder…"),
                icon: <FolderIcon size={14} />,
                onClick: () => setMoveOpen(true),
              },
              {
                key: "delete",
                label: t("crud.delete", "Delete"),
                icon: <TrashIcon size={14} />,
                danger: true,
                onClick: () => setDeleteOpen(true),
              },
            ]}
          />
        </span>
      </Link>

      <RenameDialog
        open={renameOpen}
        title={t("crud.renameNote", "Rename Note")}
        initialValue={note.title}
        label={t("crud.titleLabel", "Title")}
        existingNames={notes
          .filter(
            (n) =>
              n.id !== note.id &&
              n.subjectId === note.subjectId &&
              (n.folderId || UNFILED_FOLDER_ID) === (note.folderId || UNFILED_FOLDER_ID)
          )
          .map((n) => n.title)}
        duplicateErrorMessage={
          note.folderId && note.folderId !== UNFILED_FOLDER_ID
            ? t("crud.errors.duplicateNoteInFolder", "A note with this name already exists in this folder")
            : t("crud.errors.duplicateNoteInSubject", "A note with this name already exists in this subject")
        }
        onSave={handleRename}
        onClose={() => setRenameOpen(false)}
      />

      <MoveNoteDialog
        open={moveOpen}
        noteId={note.id}
        noteTitle={note.title}
        currentFolderId={note.folderId}
        subjectId={note.subjectId}
        onMoved={() => toast.success(t("crud.success.noteMoved", "Note moved"))}
        onClose={() => setMoveOpen(false)}
      />

      <ConfirmDialog
        open={deleteOpen}
        title={t("crud.deleteNote", "Delete Note")}
        message={
          <>
            <p style={{ fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
              {t("crud.deleteNoteConfirm", { title: note.title })}
            </p>
            <p>{t("crud.deleteNoteWarning")}</p>
          </>
        }
        confirmLabel={t("common.actions.delete", "Delete")}
        busy={deleting}
        onConfirm={() => void handleDelete()}
        onClose={() => setDeleteOpen(false)}
      />
    </>
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
