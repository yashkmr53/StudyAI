import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { ModuleProvider, ServiceGate, type Services } from "../modules/ModuleContext";
import { ServiceCard } from "../modules/ServiceCard";
import { FolderCard } from "../folders/FolderCard";
import { NewFolderDialog } from "../folders/NewFolderDialog";
import { EmptyState, ErrorState } from "../ui/primitives";
import {
  ClipboardIcon,
  EditIcon,
  FolderIcon,
  PenIcon,
  PlusIcon,
  QuizIcon,
  TrashIcon,
  UploadIcon,
} from "../ui/icons";
import { useAuthStore } from "../../features/auth/authStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { documentsApi } from "../../services/api/documents";
import type { ModuleId } from "../../types/modules";
import { MODULE_SERVICE_MATRIX } from "../../types/modules";
import { UNFILED_FOLDER_ID } from "../../types/domain";
import { childrenOf } from "../../utils/folderTree";
import { ActionMenu } from "../ui/ActionMenu";
import { RenameDialog } from "../ui/RenameDialog";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { useToast } from "../ui/Toast";

/**
 * The central subject workspace (§8–§10). The active module is local UI
 * state: switching NoteSpace ↔ AI Classroom re-renders service-backed
 * elements instantly — no route change, no fetch, no reload (§8).
 */
export function SubjectWorkspace() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const profile = useAuthStore((s) => s.profile);
  const subjects = useWorkspaceStore((s) => s.subjects);
  const folders = useWorkspaceStore((s) => s.folders);
  const notes = useWorkspaceStore((s) => s.notes);
  const loading = useWorkspaceStore((s) => s.loading);
  const touchSubject = useWorkspaceStore((s) => s.touchSubject);
  const renameSubject = useWorkspaceStore((s) => s.renameSubject);
  const removeSubject = useWorkspaceStore((s) => s.removeSubject);
  const toast = useToast();

  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [renameSubjectOpen, setRenameSubjectOpen] = useState(false);
  const [deleteSubjectOpen, setDeleteSubjectOpen] = useState(false);
  const [deletingSubject, setDeletingSubject] = useState(false);
  const { t } = useTranslation();

  const subject = subjects.find((x) => x.id === subjectId);

  async function handleRenameSubject(newName: string) {
    if (!subject) return;
    try {
      await renameSubject(subject.id, newName);
      toast.success(t("crud.success.subjectRenamed", "Subject renamed"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("crud.errors.renameSubject", "Failed to rename subject"));
      throw err;
    }
  }

  async function handleDeleteSubject() {
    if (!subject) return;
    setDeletingSubject(true);
    try {
      await removeSubject(subject.id);
      toast.success(t("crud.success.subjectDeleted", "Subject deleted"));
      setDeleteSubjectOpen(false);
      navigate("/subjects");
    } catch (err) {
      toast.error(t("crud.errors.deleteSubject", "Failed to delete subject"));
    } finally {
      setDeletingSubject(false);
    }
  }

  useEffect(() => {
    if (subjectId) void touchSubject(subjectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectId]);

  const moduleId: ModuleId = (profile?.module as ModuleId) ?? "NOTE_SPACE";
  const services: Services = MODULE_SERVICE_MATRIX[moduleId] ?? MODULE_SERVICE_MATRIX.NOTE_SPACE;

  const subjectFolders = useMemo(
    () => folders.filter((f) => f.subjectId === subjectId),
    [folders, subjectId],
  );
  const rootFolders = useMemo(
    () => childrenOf(subjectFolders, null),
    [subjectFolders],
  );
  const unfiledCount = notes.filter(
    (n) => n.subjectId === subjectId && (n.folderId === UNFILED_FOLDER_ID || !n.folderId),
  ).length;

  function countNotesIn(folderId: string): number {
    let total = notes.filter((n) => n.folderId === folderId).length;
    const stack = childrenOf(subjectFolders, folderId).map((f) => f.id);
    while (stack.length > 0) {
      const current = stack.pop();
      if (!current) break;
      total += notes.filter((n) => n.folderId === current).length;
      stack.push(...childrenOf(subjectFolders, current).map((f) => f.id));
    }
    return total;
  }

  if (!subject && !loading) {
    return (
      <div className="content__inner">
        <ErrorState
          title={t("workspace.notFoundTitle")}
          message={t("workspace.notFoundMessage")}
        />
      </div>
    );
  }

  if (!subject) return null;

  const writeState = { returnTo: `${location.pathname}` };

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !subjectId || !profile) return;
    setUploading(true);
    setUploadError(null);
    try {
      const created = await documentsApi.create(profile.id, file.name, "image", subjectId);
      await documentsApi.uploadToSignedUrl(created.upload.url, await file.arrayBuffer(), file.type);
      await documentsApi.finalizeUpload(created.document.id, created.page.id);
      await useWorkspaceStore.getState().registerUploadNote({
        documentId: created.document.id,
        profileId: profile.id,
        subjectId,
        folderId: UNFILED_FOLDER_ID,
        title: file.name,
      });
      navigate(`/subjects/${subjectId}/notes/${created.document.id}`);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : t("workspace.uploadError", "Failed to upload note. Please try again."));
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  return (
    <ModuleProvider value={{ moduleId, services }}>
      <div className="content__inner content__inner--wide">
        <Breadcrumbs
          crumbs={[
            { label: t("common.breadcrumb.subjects"), to: "/subjects" },
            { label: subject.name },
          ]}
        />

        <div className="page-heading page-heading__row" style={{ marginTop: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1 className="truncate" title={subject.name}>{subject.name}</h1>
            <ActionMenu
              ariaLabel={t("crud.subjectActions", { defaultValue: "Subject actions" })}
              items={[
                {
                  key: "rename",
                  label: t("crud.renameSubject", "Rename Subject"),
                  icon: <EditIcon size={14} />,
                  onClick: () => setRenameSubjectOpen(true),
                },
                {
                  key: "delete",
                  label: t("crud.deleteSubject", "Delete Subject"),
                  icon: <TrashIcon size={14} />,
                  danger: true,
                  onClick: () => setDeleteSubjectOpen(true),
                },
              ]}
            />
          </div>
        </div>

        {/* AI Classroom capability cards — each gated by its own service */}
        {services.tests || services.qa ? (
          <section className="ai-banner" aria-label={t("modules.classroomBanner")}>
            <div className="ai-banner__label">{t("modules.classroomBanner")}</div>
            <div className="card-grid">
              <ServiceGate service="qa">
                <ServiceCard
                  title={t("modules.cards.qa.title")}
                  description={t("modules.cards.qa.description")}
                  icon={<QuizIcon size={17} />}
                  iconColor={{ bg: "#e5f6ee", fg: "#188554" }}
                  to={`/subjects/${subjectId}/practice`}
                />
              </ServiceGate>
              <ServiceGate service="tests">
                <ServiceCard
                  title={t("modules.cards.tests.title")}
                  description={t("modules.cards.tests.description")}
                  icon={<ClipboardIcon size={17} />}
                  iconColor={{ bg: "#fdf3d8", fg: "#9a6700" }}
                  to={`/subjects/${subjectId}/tests`}
                />
              </ServiceGate>
            </div>
          </section>
        ) : null}

        {uploadError && (
          <div className="form-error" role="alert" style={{ marginBottom: 16 }}>
            {uploadError}
          </div>
        )}

        <section className="panel-section" aria-label={t("workspace.foldersTitle")}>
          <div className="panel-section__header">
            <h2 className="panel-section__title">{t("workspace.foldersTitle")}</h2>
            <span className="panel-section__spacer" />
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => setNewFolderOpen(true)}>
              <PlusIcon size={13} />
              {t("workspace.newFolder")}
            </button>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() =>
                navigate(`/subjects/${subjectId}/write`, { state: writeState })
              }
              data-tip={t("workspace.writeTooltip")}
            >
              <PenIcon size={13} />
              {t("workspace.write")}
            </button>
            <label className="btn btn--secondary btn--sm" style={{ cursor: "pointer" }}>
              <UploadIcon size={13} />
              {uploading ? t("workspace.uploading") : t("workspace.upload")}
              <input
                type="file"
                accept="image/*,.pdf"
                style={{ display: "none" }}
                disabled={uploading}
                onChange={handleUpload}
              />
            </label>
          </div>

          {rootFolders.length === 0 && unfiledCount === 0 ? (
            <EmptyState
              icon={<FolderIcon size={20} />}
              title={t("workspace.foldersEmpty.title")}
              description={t("workspace.foldersEmpty.description")}
              action={
                <div className="row">
                  <button type="button" className="btn btn--secondary" onClick={() => setNewFolderOpen(true)}>
                    <PlusIcon size={13} />
                    {t("workspace.newFolder")}
                  </button>
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={() => navigate(`/subjects/${subjectId}/write`, { state: writeState })}
                  >
                    <PenIcon size={13} />
                    {t("workspace.write")}
                  </button>
                </div>
              }
            />
          ) : (
            <div className="folder-grid">
              {rootFolders.map((folder) => (
                <FolderCard
                  key={folder.id}
                  folder={folder}
                  subjectId={subject.id}
                  noteCount={countNotesIn(folder.id)}
                />
              ))}
              <FolderCard
                folder={{ id: UNFILED_FOLDER_ID, name: t("workspace.unfiled") }}
                subjectId={subject.id}
                noteCount={unfiledCount}
                variant="unfiled"
              />
            </div>
          )}
        </section>
      </div>

      <NewFolderDialog
        open={newFolderOpen}
        onClose={() => setNewFolderOpen(false)}
        subjectId={subject.id}
      />

      <RenameDialog
        open={renameSubjectOpen}
        title={t("crud.renameSubject", "Rename Subject")}
        initialValue={subject.name}
        label={t("crud.nameLabel", "Name")}
        existingNames={subjects.filter((s) => s.id !== subject.id).map((s) => s.name)}
        duplicateErrorMessage={t("crud.errors.duplicateSubject", "A subject with this name already exists in this profile")}
        onSave={handleRenameSubject}
        onClose={() => setRenameSubjectOpen(false)}
      />

      <ConfirmDialog
        open={deleteSubjectOpen}
        title={t("crud.deleteSubject", "Delete Subject")}
        message={
          <>
            <p style={{ fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
              {t("crud.deleteSubjectConfirm", { name: subject.name })}
            </p>
            <p>{t("crud.deleteSubjectWarning")}</p>
          </>
        }
        confirmLabel={t("common.actions.delete", "Delete")}
        busy={deletingSubject}
        onConfirm={() => void handleDeleteSubject()}
        onClose={() => setDeleteSubjectOpen(false)}
      />
    </ModuleProvider>
  );
}
