import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "../features/auth/authStore";

const NAV_ITEMS = [
  { to: "/notespace", label: "NoteSpace" },
  { to: "/ai-classroom", label: "AI Classroom" },
  { to: "/canvas", label: "Canvas" },
  { to: "/tests", label: "Tests" },
  { to: "/chat", label: "Chat" },
  { to: "/revision", label: "Revision" },
];

export function Layout() {
  const email = useAuthStore((s) => s.email);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  async function onLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="brand">StudyAI</div>
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? "active" : "")}>
            {item.label}
          </NavLink>
        ))}
        <div style={{ marginTop: "auto" }}>
          <span style={{ fontSize: "0.8rem", color: "#9ca3af" }}>{email}</span>
          <button onClick={onLogout} style={{ width: "100%", marginTop: "0.5rem" }}>
            Sign out
          </button>
        </div>
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
