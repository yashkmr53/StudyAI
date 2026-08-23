import { Outlet } from "react-router-dom";
import { OfflineBanner } from "../OfflineBanner";
import { NewSubjectDialog } from "../subjects/NewSubjectDialog";
import { Sidebar } from "./Sidebar";
import { useState } from "react";

/**
 * Desktop application shell (§5): sidebar + content outlet. AI capabilities
 * never appear here — they surface inside subject workspaces via services.
 */
export function AppShell() {
  const [newSubjectOpen, setNewSubjectOpen] = useState(false);

  return (
    <div className="shell">
      <Sidebar onNewSubject={() => setNewSubjectOpen(true)} />
      <div className="main">
        <OfflineBanner />
        <div className="content">
          <Outlet />
        </div>
      </div>
      <NewSubjectDialog open={newSubjectOpen} onClose={() => setNewSubjectOpen(false)} />
    </div>
  );
}
