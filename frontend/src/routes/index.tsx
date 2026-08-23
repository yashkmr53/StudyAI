import { useEffect } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";
import { ProfileStep } from "../features/onboarding/ProfileStep";
import { ModuleStep } from "../features/onboarding/ModuleStep";
import { SubjectsStep } from "../features/onboarding/SubjectsStep";
import { useAuthStore } from "../features/auth/authStore";
import { useWorkspaceStore } from "../state/workspaceStore";import { useSubjectModule } from "../components/modules/ModuleContext";
import { isOnboarded, loadProgress } from "../features/onboarding/onboardingState";
import type { ServiceId } from "../types/modules";
import { SubjectsPage } from "../components/subjects/SubjectsPage";
import { SubjectWorkspace } from "../components/subjects/SubjectWorkspace";
import { FolderDetailPage } from "../components/folders/FolderDetailPage";
import { NoteDetailPage } from "../components/notes/NoteDetailPage";
import { WritingPage } from "../features/writing/WritingPage";
import { TestsPage } from "../components/tests/TestsPage";
import { PracticePage } from "../components/practice/PracticePage";
import { ChatPage } from "../components/chat/ChatPage";

/** Restores the session and loads the workspace once authenticated. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const email = useAuthStore((s) => s.email);
  const initialized = useAuthStore((s) => s.initialized);
  const init = useAuthStore((s) => s.init);
  const profile = useAuthStore((s) => s.profile);
  const loadWorkspace = useWorkspaceStore((s) => s.loadWorkspace);
  const resetWorkspace = useWorkspaceStore((s) => s.resetWorkspace);

  useEffect(() => {
    void init();
  }, [init]);

  // Load (or reload) the workspace whenever the active profile changes —
  // including after a refresh, where the profile is restored from storage.
  useEffect(() => {
    if (!email || !profile?.id) return;
    const ws = useWorkspaceStore.getState();
    if (ws.profileId !== profile.id || !ws.loaded) {
      if (ws.profileId !== profile.id) resetWorkspace();
      void loadWorkspace(profile.id);
    }
  }, [email, profile?.id, loadWorkspace, resetWorkspace]);

  // Signing out must not leak the previous profile's data into the UI.
  useEffect(() => {
    if (initialized && !email) resetWorkspace();
  }, [initialized, email, resetWorkspace]);

  if (!initialized) return null;
  if (!email) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/** Sends fresh accounts through the four-step flow (§6). */
function RequireOnboarding({ children }: { children: React.ReactNode }) {
  const profile = useAuthStore((s) => s.profile);
  const pathname = window.location.pathname;

  if (!profile) return <Navigate to="/onboarding/profile" replace />;
  if (isOnboarded(profile.id)) {
    return <Navigate to="/subjects" replace />;
  }
  const progress = loadProgress();
  const expected =
    progress?.lastStep === "subjects"
      ? "/onboarding/subjects"
      : progress?.lastStep === "module"
        ? "/onboarding/module"
        : "/onboarding/profile";
  // Only redirect when landing on this guard outside onboarding routes.
  if (pathname === "/") {
    return <Navigate to={expected} replace />;
  }
  return <>{children}</>;
}

/**
 * Deep links into service-scoped features resolve against the *active*
 * module's services: a disabled capability bounces back to the workspace
 * instead of rendering a dead feature screen.
 */
function ServiceRoute({ service, children }: { service: ServiceId; children: React.ReactNode }) {
  const { subjectId } = useParams<{ subjectId: string }>();
  const { services } = useSubjectModule(subjectId);
  if (!services[service]) return <Navigate to={`/subjects/${subjectId ?? ""}`} replace />;
  return <>{children}</>;
}

/** "/" decides between finishing onboarding and the subjects home. */
function RootRedirect() {
  const profile = useAuthStore((s) => s.profile);
  if (!profile) return <Navigate to="/onboarding/profile" replace />;
  if (!isOnboarded(profile.id)) {
    const progress = loadProgress();
    const target =
      progress?.lastStep === "subjects"
        ? "/onboarding/subjects"
        : progress?.lastStep === "module"
          ? "/onboarding/module"
          : "/onboarding/profile";
    return <Navigate to={target} replace />;
  }
  return <Navigate to="/subjects" replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      {/* public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* onboarding */}
      <Route path="/onboarding/profile" element={<RequireAuth><ProfileStep /></RequireAuth>} />
      <Route path="/onboarding/module" element={<RequireAuth><RequireOnboarding><ModuleStep /></RequireOnboarding></RequireAuth>} />
      <Route path="/onboarding/subjects" element={<RequireAuth><RequireOnboarding><SubjectsStep /></RequireOnboarding></RequireAuth>} />

      {/* application shell */}
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<RootRedirect />} />
        <Route path="subjects" element={<SubjectsPage />} />
        <Route path="subjects/:subjectId" element={<SubjectWorkspace />} />
        <Route path="subjects/:subjectId/write" element={<WritingPage />} />
        <Route path="subjects/:subjectId/folders/:folderId" element={<FolderDetailPage />} />
        <Route path="subjects/:subjectId/notes/:noteId" element={<NoteDetailPage />} />
        <Route
          path="subjects/:subjectId/tests"
          element={
            <ServiceRoute service="tests">
              <TestsPage />
            </ServiceRoute>
          }
        />
        <Route
          path="subjects/:subjectId/practice"
          element={
            <ServiceRoute service="qa">
              <PracticePage />
            </ServiceRoute>
          }
        />
        <Route
          path="subjects/:subjectId/chat"
          element={
            <ServiceRoute service="chat">
              <ChatPage />
            </ServiceRoute>
          }
        />
      </Route>

      {/* legacy paths from earlier phases */}
      <Route path="/notespace" element={<Navigate to="/subjects" replace />} />
      <Route path="/canvas" element={<Navigate to="/subjects" replace />} />
      <Route path="/tests" element={<Navigate to="/subjects" replace />} />
      <Route path="/chat" element={<Navigate to="/subjects" replace />} />
      <Route path="/revision" element={<Navigate to="/subjects" replace />} />
      <Route path="/ai-classroom" element={<Navigate to="/subjects" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
