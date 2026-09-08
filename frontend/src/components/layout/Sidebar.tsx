import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../features/auth/authStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { profilesApi } from "../../services/api/profiles";
import {
  BookIcon,
  CheckIcon,
  ChevronDownIcon,
  PlusIcon,
} from "../ui/icons";
import type { ModuleId } from "../../types/modules";
import type { Profile } from "../../types/api";

const GLYPH_PALETTE = [
  "#eef0fc,#4f5bd5",
  "#e5f6ee,#188554",
  "#fdf3d8,#9a6700",
  "#fbeaea,#c93a3a",
  "#e8f4fd,#2270b8",
];

export function subjectGlyph(name: string): { background: string; color: string; label: string } {
  const hash = [...name].reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  const [background, color] = GLYPH_PALETTE[hash % GLYPH_PALETTE.length].split(",");
  return { background, color, label: name.slice(0, 1).toUpperCase() };
}

/** Left navigation: brand, subjects, add-subject — nothing else (§5). */
export function Sidebar({ onNewSubject }: { onNewSubject: () => void }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const subjects = useWorkspaceStore((s) => s.subjects);
  const loading = useWorkspaceStore((s) => s.loading);

  const profile = useAuthStore((s) => s.profile);
  const switchToProfile = useAuthStore((s) => s.switchToProfile);
  const addProfile = useAuthStore((s) => s.addProfile);
  const refreshProfiles = useAuthStore((s) => s.refreshProfiles);
  const logout = useAuthStore((s) => s.logout);
  const module = useAuthStore((s) => s.module);

  const [switcherOpen, setSwitcherOpen] = useState(false);
  const popRef = useRef<HTMLDivElement | null>(null);
  const [dropdownModule, setDropdownModule] = useState<ModuleId>(module);
  const [dropdownProfiles, setDropdownProfiles] = useState<Profile[]>([]);

  useEffect(() => {
    void refreshProfiles().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!switcherOpen) return;
    const onDown = (e: MouseEvent) => {
      if (popRef.current && !popRef.current.contains(e.target as Node)) {
        setSwitcherOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [switcherOpen]);

  // Sync dropdown module with the actual app module when the dropdown opens.
  useEffect(() => {
    if (switcherOpen) {
      setDropdownModule(module);
    }
  }, [switcherOpen, module]);

  // Fetch profiles for the currently selected dropdown module.
  useEffect(() => {
    if (!switcherOpen) return;
    let cancelled = false;
    profilesApi.list(dropdownModule).then((list) => {
      if (!cancelled) setDropdownProfiles(list);
    });
    return () => {
      cancelled = true;
    };
  }, [dropdownModule, switcherOpen]);

  async function onAddProfile() {
    const name = window.prompt(t("nav.newProfilePrompt"));
    if (!name?.trim()) return;
    try {
      await addProfile(name.trim());
      setSwitcherOpen(false);
      navigate("/subjects");
    } catch {
      /* surfaced via global error handling later */
    }
  }

  async function onSignOut() {
    await logout();
    navigate("/login");
  }

  async function onProfileClick(selected: Profile) {
    switchToProfile(selected);
    await refreshProfiles();
    setSwitcherOpen(false);
    navigate("/subjects");
  }

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__brand-mark">S</div>
        <div className="sidebar__brand-name">{t("app.name")}</div>
      </div>

      <div className="sidebar__section-label">
        {t("nav.subjectsSection")}
        <button
          type="button"
          className="icon-btn"
          style={{ width: 22, height: 22 }}
          onClick={onNewSubject}
          aria-label={t("nav.newSubjectAria")}
          data-tip={t("nav.newSubjectAria")}
        >
          <PlusIcon size={14} />
        </button>
      </div>

      <nav className="sidebar__scroll" aria-label={t("nav.subjectsSection")}>
        {subjects.map((subject) => (
          <NavLink
            key={subject.id}
            to={`/subjects/${subject.id}`}
            className={({ isActive }) =>
              isActive ? "sidebar__item active" : "sidebar__item"
            }
          >
            <span className="sidebar__item-icon">
              <BookIcon size={15} />
            </span>
            <span className="grow nowrap" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
              {subject.name}
            </span>
            <span className="sidebar__item-count">{subject.noteCount}</span>
          </NavLink>
        ))}

        {!loading && subjects.length === 0 && (
          <p className="small faint" style={{ padding: "2px 20px 8px" }}>
            {t("nav.noSubjects")}
          </p>
        )}

        <button type="button" className="sidebar__add" onClick={onNewSubject}>
          <PlusIcon size={14} />
          {t("nav.addSubject")}
        </button>
      </nav>

      <div className="sidebar__footer" ref={popRef}>
        {switcherOpen && (
          <div className="popover" role="menu" aria-label={t("nav.switchProfile")}>
            <div className="popover__section-label" style={{ padding: "8px 12px 4px" }}>
              {t("modules.toggleLabel", { defaultValue: "Module" })}
            </div>
            <div className="segmented" role="tablist">
              {(["NOTE_SPACE", "AI_CLASSROOM"] as ModuleId[]).map((id) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={dropdownModule === id}
                  className={dropdownModule === id ? "segmented__option active" : "segmented__option"}
                  onClick={() => setDropdownModule(id)}
                >
                  <span className="dot" aria-hidden />
                  {t(`onboarding.module.${id === "NOTE_SPACE" ? "noteSpaceName" : "aiClassroomName"}`)}
                </button>
              ))}
            </div>
            <div className="popover__divider" />
            {dropdownProfiles.map((p) => (
              <button
                key={p.id}
                type="button"
                role="menuitemradio"
                aria-checked={profile?.id === p.id}
                className={
                  profile?.id === p.id
                    ? "popover__item selected"
                    : "popover__item"
                }
                onClick={() => void onProfileClick(p)}
              >
                <span className="avatar">{initials(p.name)}</span>
                <span className="grow nowrap">{p.name}</span>
                <span className="check">
                  <CheckIcon size={14} />
                </span>
              </button>
            ))}
            <div className="popover__divider" />
            <button type="button" className="popover__item" onClick={() => void onAddProfile()}>
              <PlusIcon size={14} />
              {t("common.actions.newProfile")}
            </button>
            <div className="popover__divider" />
            <button type="button" className="popover__item" onClick={() => void onSignOut()}>
              {t("common.actions.signOut")}
            </button>
          </div>
        )}

        <button
          type="button"
          className="profile-button"
          onClick={() => setSwitcherOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={switcherOpen}
        >
          <span className="avatar">{profile ? initials(profile.name) : "?"}</span>
          <span className="profile-button__meta">
            <span className="profile-button__name">{profile?.name ?? "Profile"}</span>
            <span className="profile-button__hint">{t("nav.switchProfile")}</span>
          </span>
          <ChevronDownIcon size={14} className="faint" />
        </button>
      </div>
    </aside>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}