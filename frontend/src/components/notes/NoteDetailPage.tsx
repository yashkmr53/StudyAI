import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { ModuleProvider, useSubjectModule } from "../modules/ModuleContext";
import { HandwrittenView } from "./HandwrittenView";
import { EnrichedView } from "./EnrichedView";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { documentsApi } from "../../services/api/documents";
import type { NoteMeta } from "../../types/domain";
import { UNFILED_FOLDER_ID } from "../../types/domain";
import { breadcrumbCrumbs } from "../../utils/folderTree";
import { ActionMenu } from "../ui/ActionMenu";
import { RenameDialog } from "../ui/RenameDialog";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { MoveNoteDialog } from "./MoveNoteDialog";
import { EditIcon, FolderIcon, TrashIcon } from "../ui/icons";
import { useToast } from "../ui/Toast";

/**
 * Note detail (§15–§20).
 * - Handwritten is always the landing tab and the default (Rule 9).
 * - The Enriched tab exists only when EnrichmentService is enabled (Rule 5);
 *   switching to NoteSpace while viewing Enriched falls back silently to
 *   Handwritten (§20).
 */
export function NoteDetailPage() {
  const { subjectId, noteId } = useParams<{
    subjectId: string;
    noteId: string;
  }>();
  const navigate = useNavigate();
  const toast = useToast();

  const subjects = useWorkspaceStore((s) => s.subjects);
  const folders = useWorkspaceStore((s) => s.folders);
  const notes = useWorkspaceStore((s) => s.notes);
  const workspaceLoading = useWorkspaceStore((s) => s.loading);
  const renameNote = useWorkspaceStore((s) => s.renameNote);
  const removeNote = useWorkspaceStore((s) => s.removeNote);

  const [renameOpen, setRenameOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const { moduleId, services } = useSubjectModule(subjectId);

  const storeNote = notes.find((n) => n.id === noteId || n.refId === noteId);
  const [remoteNote, setRemoteNote] = useState<NoteMeta | null>(null);
  const [fetchingRemote, setFetchingRemote] = useState<boolean>(!storeNote && !!noteId);
  const [fetchFailed, setFetchFailed] = useState<boolean>(false);

  const activeNote = storeNote || remoteNote;

  useEffect(() => {
    if (!noteId) return;
    const existing = notes.find((n) => n.id === noteId || n.refId === noteId);
    if (existing) {
      setRemoteNote(null);
      setFetchingRemote(false);
      setFetchFailed(false);
      return;
    }
    let cancelled = false;
    setFetchingRemote(true);
    documentsApi
      .get(noteId)
      .then((doc) => {
        if (cancelled) return;
        const title = (doc as any).title || (doc as any).filename || `Note ${doc.id.slice(0, 8)}`;
        const meta: NoteMeta = {
          id: doc.id,
          refId: doc.id,
          profileId: doc.profile,
          subjectId: doc.subject || subjectId || "",
          folderId: UNFILED_FOLDER_ID,
          title,
          source: (doc.source === "canvas" ? "canvas" : "upload"),
          createdAt: doc.created_at,
          updatedAt: doc.created_at,
        };
        setRemoteNote(meta);
        setFetchFailed(false);
        void useWorkspaceStore.getState().upsertNote(meta).catch(() => undefined);
      })
      .catch(() => {
        if (!cancelled) setFetchFailed(true);
      })
      .finally(() => {
        if (!cancelled) setFetchingRemote(false);
      });
    return () => {
      cancelled = true;
    };
  }, [noteId, notes, subjectId]);

  const subject =
    subjects.find((x) => x.id === subjectId) ||
    (activeNote?.subjectId ? subjects.find((x) => x.id === activeNote.subjectId) : null) ||
    (subjectId ? { id: subjectId, name: "Subject" } : null);

  // Handwritten is always the default landing tab.
  const [tab, setTab] = useState<"handwritten" | "enriched">("handwritten");
  const [page, setPage] = useState(1);
  const [highlightToken, setHighlightToken] = useState(0);
  const { t } = useTranslation();

  // Rule: never leave the user on a tab their module doesn't expose.
  useEffect(() => {
    if (!services.enrichment && tab === "enriched") {
      setTab("handwritten");
    }
  }, [services.enrichment, tab]);

  const crumbs = useMemo(() => {
    if (!activeNote) return [{ label: t("common.breadcrumb.subjects", "Subjects"), to: "/subjects" }];
    const targetSubject = subject || { id: subjectId || "", name: "Subject" };
    const subjectFolders = folders.filter((f) => f.subjectId === targetSubject.id);
    const base = breadcrumbCrumbs(
      subjectFolders,
      activeNote.folderId ?? UNFILED_FOLDER_ID,
      targetSubject.name,
      `/subjects/${targetSubject.id}`,
    );
    return [...base, { label: activeNote.title }];
  }, [subject, activeNote, folders, subjectId, t]);

  function onCitation(targetPage: number) {
    setPage(targetPage);
    setTab("handwritten");
    setHighlightToken((t) => t + 1);
  }

  if (!activeNote && (fetchingRemote || (workspaceLoading && !fetchFailed))) {
    return (
      <div className="content__inner content__inner--wide">
        <div className="skeleton" style={{ height: 400, borderRadius: 14 }} />
      </div>
    );
  }

  if (!activeNote && fetchFailed) {
    return (
      <div className="content__inner">
        <p className="muted">{t("notes.detail.loadFailed")}</p>
      </div>
    );
  }

  if (!activeNote) return null;

  const note = activeNote;
  const displaySubject = subject || { id: subjectId || "", name: "Subject" };

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
      navigate(displaySubject.id ? `/subjects/${displaySubject.id}` : "/subjects");
    } catch (err) {
      toast.error(t("crud.errors.deleteNote", "Failed to delete note"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <ModuleProvider value={{ moduleId, services }}>
      <div className="content__inner content__inner--wide">
        <Breadcrumbs crumbs={crumbs} />

        <div className="page-heading page-heading__row" style={{ marginTop: 14 }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h1 className="truncate" title={note.title}>{note.title}</h1>
            <p className="subtitle" style={{ marginTop: 5 }}>
              <Link to={`/subjects/${displaySubject.id}`} title={displaySubject.name}>{displaySubject.name}</Link>
              {" · "}
              {note.source === "canvas"
                ? t("notes.source.canvas")
                : t("notes.source.upload")}
            </p>
          </div>
          <div className="page-heading__actions">
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
          </div>
        </div>

        {/* Enriched tab is conditional on EnrichmentService alone */}
        {services.enrichment ? (
          <div className="tabs" role="tablist">
            <TabButton active={tab === "handwritten"} onClick={() => setTab("handwritten")}>
              {t("notes.detail.tabHandwritten")}
            </TabButton>
            <TabButton active={tab === "enriched"} onClick={() => setTab("enriched")}>
              {t("notes.detail.tabEnriched")}
            </TabButton>
          </div>
        ) : null}

        <div role="tabpanel">
          {tab === "handwritten" ? (
            <HandwrittenView
              note={note}
              page={page}
              onPageChange={setPage}
              highlightToken={highlightToken}
            />
          ) : (
            <EnrichedView note={note} onCitation={onCitation} />
          )}
        </div>
      </div>

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
        subjectId={note.subjectId || displaySubject.id}
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
    </ModuleProvider>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button type="button" role="tab" aria-selected={active} className={active ? "tab active" : "tab"} onClick={onClick}>
      {children}
    </button>
  );
}
