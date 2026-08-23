import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { ModuleProvider, useSubjectModule } from "../modules/ModuleContext";
import { HandwrittenView } from "./HandwrittenView";
import { EnrichedView } from "./EnrichedView";
import { useWorkspaceStore } from "../../state/workspaceStore";
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

  const { moduleId, services } = useSubjectModule(subjectId);

  const subject = subjects.find((x) => x.id === subjectId);
  const note = notes.find((n) => n.id === noteId);

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
    if (!subject || !note) return [{ label: "Subjects", to: "/subjects" }];
    const subjectFolders = folders.filter((f) => f.subjectId === subject.id);
    const base = breadcrumbCrumbs(
      subjectFolders,
      note.folderId ?? UNFILED_FOLDER_ID,
      subject.name,
      `/subjects/${subject.id}`,
    );
    return [...base, { label: note.title }];
  }, [subject, note, folders]);

  function onCitation(targetPage: number) {
    setPage(targetPage);
    setTab("handwritten");
    setHighlightToken((t) => t + 1);
  }

  if (!subject || !note) {
    return (
      <div className="content__inner">
        <p className="muted">{t("notes.detail.loadFailed")}</p>
      </div>
    );
  }

  return (
    <ModuleProvider value={{ moduleId, services }}>
      <div className="content__inner content__inner--wide">
        <Breadcrumbs crumbs={crumbs} />

        <div className="page-heading" style={{ marginTop: 14 }}>
          <h1>{note.title}</h1>
          <p className="subtitle" style={{ marginTop: 5 }}>
            <Link to={`/subjects/${subjectId}`}>{subject.name}</Link>
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
