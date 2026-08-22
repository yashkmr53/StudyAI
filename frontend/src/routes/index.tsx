import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Placeholder } from "../components/Placeholder";
import { CanvasEditor } from "../features/canvas/CanvasEditor";
import { NotespacePage } from "../features/notespace/NotespacePage";
import { useAuthStore } from "../features/auth/authStore";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const email = useAuthStore((s) => s.email);
  const initialized = useAuthStore((s) => s.initialized);
  const init = useAuthStore((s) => s.init);

  useEffect(() => {
    void init();
  }, [init]);

  if (!initialized) return null;
  if (!email) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Placeholder title="Home" description="Your study dashboard will live here." />} />
        <Route path="/notespace" element={<NotespacePage />} />
        <Route
          path="/ai-classroom"
          element={
            <Placeholder
              title="AI Classroom"
              description="Enriched notes, tags, adaptive tests, chatbot and revision plans grounded in your notes."
            />
          }
        />
        <Route path="/canvas" element={<CanvasEditor />} />
        <Route path="/tests" element={<Placeholder title="Tests" description="Adaptive tests built from your material." />} />
        <Route path="/chat" element={<Placeholder title="Chat" description="Ask questions scoped to your subjects." />} />
        <Route
          path="/revision"
          element={<Placeholder title="Revision" description="Mastery-driven revision planning." />}
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
