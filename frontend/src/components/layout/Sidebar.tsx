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
  EditIcon,
  PanelLeftCloseIcon,
  PlusIcon,
  TrashIcon,
} from "../ui/icons";
import { ActionMenu } from "../ui/ActionMenu";
import { RenameDialog } from "../ui/RenameDialog";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { useToast } from "../ui/Toast";
import { useUiStore } from "../../state/uiStore";
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
export function Sidebar({
  onNewSubject,
  collapsed = false,
  onToggleCollapse,
}: {
  onNewSubject: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const subjects = useWorkspaceStore((s) => s.subjects);
  const loading = useWorkspaceStore((s) => s.loading);

  const profile = useAuthStore((s) => s.profile);
  const switchToProfile = useAuthStore((s) => s.switchToProfile);
  const addProfile = useAuthStore((s) => s.addProfile);
  const refreshProfiles = useAuthStore((s) => s.refreshProfiles);
  const renameProfile = useAuthStore((s) => s.renameProfile);
  const deleteProfile = useAuthStore((s) => s.deleteProfile);
  const logout = useAuthStore((s) => s.logout);
  const module = useAuthStore((s) => s.module);
  const toast = useToast();

  const [switcherOpen, setSwitcherOpen] = useState(false);
  const popRef = useRef<HTMLDivElement | null>(null);
  const [dropdownModule, setDropdownModule] = useState<ModuleId>(module);
  const [dropdownProfiles, setDropdownProfiles] = useState<Profile[]>([]);

  const [profileToRename, setProfileToRename] = useState<Profile | null>(null);
  const [renameProfileOpen, setRenameProfileOpen] = useState(false);
  const [profileToDelete, setProfileToDelete] = useState<Profile | null>(null);
  const [deleteProfileOpen, setDeleteProfileOpen] = useState(false);
  const [deletingProfile, setDeletingProfile] = useState(false);

  async function handleRenameProfile(newName: string) {
    if (!profileToRename) return;
    try {
      const updated = await renameProfile(profileToRename.id, newName);
      setDropdownProfiles((prev) =>
        prev.map((p) => (p.id === updated.id ? { ...p, name: updated.name } : p)),
      );
      toast.success(t("crud.success.profileRenamed", "Profile renamed"));
      setRenameProfileOpen(false);
      setProfileToRename(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("crud.errors.renameProfile", "Failed to rename profile"));
      throw err;
    }
  }

  async function handleDeleteProfile() {
    if (!profileToDelete) return;
    setDeletingProfile(true);
    try {
      const all = await profilesApi.list();
      if (all.length <= 1) {
        toast.error(t("crud.cannotDeleteOnlyProfile", "You cannot delete your only profile. Create or select another profile first."));
        setDeleteProfileOpen(false);
        setProfileToDelete(null);
        return;
      }
      const targetId = profileToDelete.id;
      const wasActive = profile?.id === targetId;
      await deleteProfile(targetId);
      setDropdownProfiles((prev) => prev.filter((p) => p.id !== targetId));
      toast.success(t("crud.success.profileDeleted", "Profile deleted"));
      setDeleteProfileOpen(false);
      setProfileToDelete(null);
      if (wasActive) {
        setSwitcherOpen(false);
        navigate("/subjects");
      }
    } catch (err) {
      toast.error(t("crud.errors.deleteProfile", "Failed to delete profile"));
    } finally {
      setDeletingProfile(false);
    }
  }

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
    const clean = name.trim();
    if (dropdownProfiles.some((p) => p.name.trim().toLowerCase() === clean.toLowerCase())) {
      toast.error(t("crud.errors.duplicateProfile", "A profile with this name already exists in this module"));
      return;
    }
    try {
      await addProfile(clean, dropdownModule);
      setSwitcherOpen(false);
      navigate("/subjects");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("crud.errors.createProfile", "Failed to create profile"));
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
    <aside
      className={`sidebar ${collapsed ? "sidebar--collapsed" : ""}`}
      aria-hidden={collapsed}
    >
      <div className="sidebar__brand">
        <div className="sidebar__brand-mark">S</div>
        <div className="sidebar__brand-name">{t("app.name")}</div>
        {onToggleCollapse && (
          <button
            type="button"
            className="icon-btn sidebar-collapse-btn"
            onClick={onToggleCollapse}
            aria-label={t("nav.collapseSidebar", "Collapse sidebar")}
            data-tip={t("nav.collapseSidebarTooltip", "Collapse Sidebar (⌘/)")}
          >
            <PanelLeftCloseIcon size={16} />
          </button>
        )}
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
            onClick={() => useUiStore.getState().closeMobileSidebar()}
            className={({ isActive }) =>
              isActive ? "sidebar__item active" : "sidebar__item"
            }
          >
            <span className="sidebar__item-icon">
              <BookIcon size={15} />
            </span>
            <span
              className="grow nowrap"
              style={{ overflow: "hidden", textOverflow: "ellipsis" }}
              title={subject.name}
            >
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
              <div
                key={p.id}
                className={
                  profile?.id === p.id
                    ? "popover__item selected"
                    : "popover__item"
                }
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "4px 8px",
                  cursor: "default",
                }}
              >
                <div
                  role="menuitemradio"
                  aria-checked={profile?.id === p.id}
                  tabIndex={0}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                    flex: 1,
                    minWidth: 0,
                    cursor: "pointer",
                  }}
                  onClick={() => void onProfileClick(p)}
                >
                  <span className="avatar">{initials(p.name)}</span>
                  <span
                    className="grow nowrap"
                    style={{ overflow: "hidden", textOverflow: "ellipsis" }}
                    title={p.name}
                  >
                    {p.name}
                  </span>
                  {profile?.id === p.id && (
                    <span className="check" style={{ visibility: "visible", marginRight: 4 }}>
                      <CheckIcon size={14} />
                    </span>
                  )}
                </div>
                <ActionMenu
                  ariaLabel={t("crud.profileActions", { defaultValue: "Profile actions" })}
                  size={13}
                  items={[
                    {
                      key: "rename",
                      label: t("crud.renameProfile", "Rename Profile"),
                      icon: <EditIcon size={14} />,
                      onClick: () => {
                        setProfileToRename(p);
                        setRenameProfileOpen(true);
                        setSwitcherOpen(false);
                      },
                    },
                    {
                      key: "delete",
                      label: t("crud.deleteProfile", "Delete Profile"),
                      icon: <TrashIcon size={14} />,
                      danger: true,
                      onClick: () => {
                        setProfileToDelete(p);
                        setDeleteProfileOpen(true);
                        setSwitcherOpen(false);
                      },
                    },
                  ]}
                />
              </div>
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
          title={`${profile?.name ?? "Profile"} (${t("nav.switchProfile")})`}
        >
          <span className="avatar">{profile ? initials(profile.name) : "?"}</span>
          <span className="profile-button__meta">
            <span className="profile-button__name" title={profile?.name ?? "Profile"}>
              {profile?.name ?? "Profile"}
            </span>
            <span className="profile-button__hint">{t("nav.switchProfile")}</span>
          </span>
          <ChevronDownIcon size={14} className="faint" />
        </button>
      </div>

      {profileToRename && (
        <RenameDialog
          open={renameProfileOpen}
          title={t("crud.renameProfile", "Rename Profile")}
          initialValue={profileToRename.name}
          label={t("crud.nameLabel", "Name")}
          existingNames={dropdownProfiles.filter((p) => p.id !== profileToRename.id).map((p) => p.name)}
          duplicateErrorMessage={t("crud.errors.duplicateProfile", "A profile with this name already exists in this module")}
          onSave={handleRenameProfile}
          onClose={() => {
            setRenameProfileOpen(false);
            setProfileToRename(null);
          }}
        />
      )}

      {profileToDelete && (
        <ConfirmDialog
          open={deleteProfileOpen}
          title={t("crud.deleteProfile", "Delete Profile")}
          message={
            <>
              <p style={{ fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
                {t("crud.deleteProfileConfirm", { name: profileToDelete.name })}
              </p>
              <p>{t("crud.deleteProfileWarning")}</p>
            </>
          }
          confirmLabel={t("common.actions.delete", "Delete Profile")}
          busy={deletingProfile}
          onConfirm={() => void handleDeleteProfile()}
          onClose={() => {
            setDeleteProfileOpen(false);
            setProfileToDelete(null);
          }}
        />
      )}
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