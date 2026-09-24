import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { OfflineBanner } from "../OfflineBanner";
import { NewSubjectDialog } from "../subjects/NewSubjectDialog";
import { Sidebar } from "./Sidebar";
import { useUiStore } from "../../state/uiStore";
import { PanelLeftOpenIcon } from "../ui/icons";

/**
 * Desktop application shell (§5): dynamic collapsible sidebar + content outlet.
 * AI capabilities never appear here — they surface inside subject workspaces via services.
 */
export function AppShell() {
  const [newSubjectOpen, setNewSubjectOpen] = useState(false);
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  const mobileSidebarOpen = useUiStore((s) => s.mobileSidebarOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const closeMobileSidebar = useUiStore((s) => s.closeMobileSidebar);
  const location = useLocation();
  const { t } = useTranslation();

  // Close mobile drawer on navigation
  useEffect(() => {
    closeMobileSidebar();
  }, [location.pathname, closeMobileSidebar]);

  // Global hotkey: Cmd+\ / Cmd+/ (Mac) or Ctrl+\ / Ctrl+/ (Windows/Linux) to toggle sidebar
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && (e.key === "\\" || e.key === "/")) {
        e.preventDefault();
        toggleSidebar();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar]);

  return (
    <div
      className={`shell ${sidebarCollapsed ? "shell--collapsed" : ""} ${
        mobileSidebarOpen ? "shell--mobile-open" : ""
      }`}
    >
      {mobileSidebarOpen && (
        <div
          className="sidebar-backdrop"
          onClick={closeMobileSidebar}
          aria-hidden="true"
        />
      )}

      <Sidebar
        collapsed={sidebarCollapsed}
        onToggleCollapse={toggleSidebar}
        onNewSubject={() => setNewSubjectOpen(true)}
      />

      <div className="main">
        {sidebarCollapsed && (
          <button
            type="button"
            className="sidebar-expand-btn icon-btn"
            onClick={toggleSidebar}
            aria-label={t("nav.expandSidebar", "Expand sidebar")}
            data-tip={t("nav.expandSidebarTooltip", "Expand Sidebar (⌘/)")}
          >
            <PanelLeftOpenIcon size={18} />
          </button>
        )}
        <OfflineBanner />
        <div className="content">
          <Outlet />
        </div>
      </div>
      <NewSubjectDialog open={newSubjectOpen} onClose={() => setNewSubjectOpen(false)} />
    </div>
  );
}
