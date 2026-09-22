import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { ModuleProvider, useSubjectModule } from "../modules/ModuleContext";
import { HandwrittenView } from "./HandwrittenView";
import { EnrichedView } from "./EnrichedView";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { documentsApi } from "../../services/api/documents";
import type { NoteMeta } from "../../types/domain";
import { UNFILED_FOLDER_ID } from "../../types/domain";
import { breadcrumbCrumbs } from "../../utils/folderTree";

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

  const subjects = useWorkspaceStore((s) => s.subjects);
  const folders = useWorkspaceStore((s) => s.folders);
  const notes = useWorkspaceStore((s) => s.notes);
  const workspaceLoading = useWorkspaceStore((s) => s.loading);
  const workspaceLoaded = useWorkspaceStore((s) => s.loaded);

  const { moduleId, services } = useSubjectModule(subjectId);

  const [remoteNote, setRemoteNote] = useState<NoteMeta | null>(null);
  const [fetchingRemote, setFetchingRemote] = useState<boolean>(false);
  const [fetchFailed, setFetchFailed] = useState<boolean>(false);

  const storeNote = notes.find((n) => n.id === noteId || n.refId === noteId);
  const activeNote = storeNote || remoteNote;

  useEffect(() => {
    if (!noteId) return;
    const existing = notes.find((n) => n.id === noteId || n.refId === noteId);
    if (existing) {
      setRemoteNote(null);
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

  if ((workspaceLoading && !activeNote) || fetchingRemote) {
    return (
      <div className="content__inner content__inner--wide">
        <div className="skeleton" style={{ height: 400, borderRadius: 14 }} />
      </div>
    );
  }

  if (!activeNote && (fetchFailed || workspaceLoaded)) {
    return (
      <div className="content__inner">
        <p className="muted">{t("notes.detail.loadFailed")}</p>
      </div>
    );
  }

  if (!activeNote) return null;

  const note = activeNote;
  const displaySubject = subject || { id: subjectId || "", name: "Subject" };

  return (
    <ModuleProvider value={{ moduleId, services }}>
      <div className="content__inner content__inner--wide">
        <Breadcrumbs crumbs={crumbs} />

        <div className="page-heading" style={{ marginTop: 14 }}>
          <h1>{note.title}</h1>
          <p className="subtitle" style={{ marginTop: 5 }}>
            <Link to={`/subjects/${displaySubject.id}`}>{displaySubject.name}</Link>
            {" · "}
            {note.source === "canvas"
              ? t("notes.source.canvas")
              : t("notes.source.upload")}
          </p>
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
