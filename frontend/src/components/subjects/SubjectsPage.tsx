import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../features/auth/authStore";
import { useModuleConfigStore } from "../../state/moduleConfigStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { EmptyState, ErrorState, SkeletonCardGrid } from "../ui/primitives";
import { BookIcon, PlusIcon } from "../ui/icons";
import { NewSubjectDialog } from "./NewSubjectDialog";
import { SubjectCard } from "./SubjectCard";

/** Subjects home (§7): clean grid; no AI surface lives here (Rule 1). */
export function SubjectsPage() {
  const profile = useAuthStore((s) => s.profile);
  const profiles = useAuthStore((s) => s.profiles);
  const subjects = useWorkspaceStore((s) => s.subjects);
  const loading = useWorkspaceStore((s) => s.loading);
  const error = useWorkspaceStore((s) => s.error);
  const loaded = useWorkspaceStore((s) => s.loaded);
  const loadWorkspace = useWorkspaceStore((s) => s.loadWorkspace);

  const hydrateConfig = useModuleConfigStore((s) => s.hydrateFor);
  const [newSubjectOpen, setNewSubjectOpen] = useState(false);
  const { t } = useTranslation();

  // Module/service config is hydrated exactly once when the profile session
  // starts — never on navigation or module toggles (§26).
  useEffect(() => {
    if (profile?.id) hydrateConfig(profile.id);
  }, [profile?.id, hydrateConfig]);

  useEffect(() => {
    if (profile?.id && !loaded && !loading) void loadWorkspace(profile.id);
  }, [profile?.id, loaded, loading, loadWorkspace]);

  return (
    <div className="content__inner content__inner--wide">
      <div className="page-heading page-heading__row">
        <div>
<h1>{t("subjectsPage.title")}</h1>
          <p className="subtitle" style={{ marginTop: 5 }}>
            {profile ? t("subjectsPage.studyingAs", { name: profile.name }) : ""}
            {" "}
            {profiles.length > 1
              ? t("subjectsPage.profilesCount", { count: profiles.length })
              : ""}
          </p>
        </div>
        <div className="page-heading__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => setNewSubjectOpen(true)}
          >
            <PlusIcon size={14} />
            {t("subjectsPage.newSubject")}
          </button>
        </div>
      </div>

      {error && (
        <ErrorState
          title={t("subjectsPage.loadFailed.title")}
          message={t("subjectsPage.loadFailed.message")}
          retryLabel={t("subjectsPage.loadFailed.retry")}
          onRetry={() => profile?.id && void loadWorkspace(profile.id)}
        />
      )}

      {loading && !loaded && <SkeletonCardGrid count={6} />}

      {!loading && !error && subjects.length === 0 && (
        <EmptyState
          icon={<BookIcon size={20} />}
          title={t("subjectsPage.empty.title")}
          description={t("subjectsPage.empty.description")}
          action={
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setNewSubjectOpen(true)}
            >
              <PlusIcon size={14} />
              {t("subjectsPage.empty.action")}
            </button>
          }
        />
      )}

      {subjects.length > 0 && (
        <div className="card-grid">
          {subjects.map((subject) => (
            <SubjectCard key={subject.id} subject={subject} />
          ))}
        </div>
      )}

      <NewSubjectDialog open={newSubjectOpen} onClose={() => setNewSubjectOpen(false)} />
    </div>
  );
}
