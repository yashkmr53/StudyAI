import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { isUnfiledFolder } from "../../types/domain";
import {
  breadcrumbCrumbs,
  childrenOf,
  countNotesRecursive,
} from "../../utils/folderTree";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { FolderCard } from "./FolderCard";
import { NoteRow } from "../notes/NoteRow";
import { NewFolderDialog } from "./NewFolderDialog";
import { EmptyState } from "../ui/primitives";
import { FolderIcon, NoteIcon, PenIcon, PlusIcon } from "../ui/icons";

/**
 * Folder detail (§14): full-depth breadcrumbs, subfolders, notes.
 * Works identically for the virtual Unfiled bucket (§13).
 */
export function FolderDetailPage() {
  const { subjectId, folderId } = useParams<{
    subjectId: string;
    folderId: string;
  }>();
  const navigate = useNavigate();
  const location = useLocation();

  const subjects = useWorkspaceStore((s) => s.subjects);
  const folders = useWorkspaceStore((s) => s.folders);
  const notes = useWorkspaceStore((s) => s.notes);

  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const { t } = useTranslation();

  const subject = subjects.find((x) => x.id === subjectId);
  const subjectFolders = useMemo(
    () => folders.filter((f) => f.subjectId === subjectId),
    [folders, subjectId],
  );

  const unfiled = isUnfiledFolder(folderId ?? "");
  const folder = subjectFolders.find((f) => f.id === folderId);
  const childFolders = useMemo(
    () => childrenOf(subjectFolders, folderId ?? null),
    [subjectFolders, folderId],
  );
  const folderNotes = useMemo(
    () =>
      notes
        .filter((n) => n.subjectId === subjectId && n.folderId === folderId)
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    [notes, subjectId, folderId],
  );

  if (!subject || (!folder && !unfiled)) {
    return (
      <div className="content__inner">
        <EmptyState
          icon={<FolderIcon size={20} />}
          title={t("folders.detail.notFoundTitle")}
          description={t("folders.detail.notFoundMessage")}
        />
      </div>
    );
  }

  const displayName = unfiled ? t("folders.detail.unfiled") : (folder?.name ?? "");
  const crumbs = breadcrumbCrumbs(
    subjectFolders,
    folderId ?? "",
    subject.name,
    `/subjects/${subjectId}`,
  );
  const directCounts = new Map<string, number>();
  for (const n of notes) {
    if (!n.folderId) continue;
    directCounts.set(n.folderId, (directCounts.get(n.folderId) ?? 0) + 1);
  }
  const noteCountFor = (id: string) => countNotesRecursive(subjectFolders, id, directCounts);

  return (
    <div className="content__inner content__inner--wide">
      <Breadcrumbs crumbs={crumbs} />

      <div className="page-heading page-heading__row" style={{ marginTop: 14 }}>
        <div>
          <h1>{displayName}</h1>
          {!unfiled && (
            <p className="subtitle" style={{ marginTop: 5 }}>
              {[
                childFolders.length > 0
                  ? t("folders.detail.subfolderCount", { count: childFolders.length })
                  : null,
                t("folders.detail.noteCount", { count: folderNotes.length }),
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>
        <div className="page-heading__actions">
          {!unfiled && (
            <button type="button" className="btn btn--secondary" onClick={() => setNewFolderOpen(true)}>
              <PlusIcon size={13} />
              {t("folders.detail.newSubfolder")}
            </button>
          )}
          <button
            type="button"
            className="btn btn--primary"
            onClick={() =>
              navigate(`/subjects/${subjectId}/write`, {
                // Rule 15: writing returns to where it was opened from.
                state: { returnTo: location.pathname, folderId },
              })
            }
          >
            <PenIcon size={13} />
            {t("workspace.write")}
          </button>
        </div>
      </div>

      {unfiled && (
        <p className="hint-text" style={{ marginBottom: 16 }}>
          {t("folders.detail.unfiledHint")}
        </p>
      )}

      {childFolders.length > 0 && (
        <section className="panel-section" style={{ marginTop: 0 }} aria-label={t("folders.detail.foldersSection")}>
          <div className="panel-section__header">
            <h2 className="panel-section__title">{t("folders.detail.foldersSection")}</h2>
          </div>
          <div className="folder-grid">
            {childFolders.map((child) => (
              <FolderCard
                key={child.id}
                folder={child}
                subjectId={subject.id}
                noteCount={noteCountFor(child.id)}
              />
            ))}
          </div>
        </section>
      )}

      <section className="panel-section" aria-label={t("folders.detail.notesSection")}>
        <div className="panel-section__header">
          <h2 className="panel-section__title">{t("folders.detail.notesSection")}</h2>
          <span className="panel-section__spacer" />
        </div>
        {folderNotes.length === 0 ? (
          <EmptyState
            icon={<NoteIcon size={20} />}
            title={t("folders.detail.emptyFolderTitle")}
            description={t("folders.detail.emptyFolderDescription")}
            action={
              <button
                type="button"
                className="btn btn--primary"
                onClick={() =>
                  navigate(`/subjects/${subjectId}/write`, {
                    state: { returnTo: location.pathname, folderId },
                  })
                }
              >
                <PenIcon size={13} />
                {t("workspace.write")}
              </button>
            }
          />
        ) : (
          <div>
            {folderNotes.map((note) => (
              <NoteRow
                key={note.id}
                note={note}
                to={`/subjects/${subjectId}/notes/${note.id}`}
              />
            ))}
          </div>
        )}
      </section>

      {!unfiled && (
        <NewFolderDialog
          open={newFolderOpen}
          onClose={() => setNewFolderOpen(false)}
          subjectId={subject.id}
          defaultParentId={folder?.id ?? null}
        />
      )}
    </div>
  );
}
