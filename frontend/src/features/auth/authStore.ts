import { create } from "zustand";
import { profilesApi } from "../../services/api/profiles";
import { authApi } from "../../services/api/auth";
import {
  loadPersistedTokens,
  setActiveModule,
  setActiveProfileId,
  setSessionExpiredHandler,
  setTokens,
} from "../../services/api/client";
import { useWorkspaceStore } from "../../state/workspaceStore";
import type { ModuleId } from "../../types/modules";
import type { Profile } from "../../types/api";

loadPersistedTokens();

interface AuthState {
  email: string | null;
  /** All profiles for the active module (from backend filter). */
  profiles: Profile[];
  /** Currently active study context. */
  profile: Profile | null;
  /** Active module (NOTE_SPACE or AI_CLASSROOM). */
  module: ModuleId;
  /** Per-module remembered profile IDs. */
  selectedProfileIds: Record<ModuleId, string | null>;
  initialized: boolean;
  init: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfiles: () => Promise<void>;
  switchProfile: (id: string) => void;
  switchToProfile: (profile: Profile) => void;
  addProfile: (name: string, module?: ModuleId) => Promise<Profile>;
  renameProfile: (id: string, name: string) => Promise<Profile>;
  deleteProfile: (id: string) => Promise<void>;
}

function loadSelectedProfileIds(): Record<ModuleId, string | null> {
  if (typeof localStorage === "undefined") {
    return { NOTE_SPACE: null, AI_CLASSROOM: null };
  }
  return {
    NOTE_SPACE: localStorage.getItem("studyai.profile.NOTE_SPACE"),
    AI_CLASSROOM: localStorage.getItem("studyai.profile.AI_CLASSROOM"),
  };
}

function saveSelectedProfileId(module: ModuleId, profileId: string | null) {
  if (typeof localStorage === "undefined") return;
  if (profileId) {
    localStorage.setItem(`studyai.profile.${module}`, profileId);
  } else {
    localStorage.removeItem(`studyai.profile.${module}`);
  }
}

function persistModule(module: ModuleId) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem("studyai.module", module);
}

function resolveActiveProfile(
  profiles: Profile[],
  selectedIds: Record<ModuleId, string | null>,
  lastActiveProfileId: string | null,
  lastActiveModule: ModuleId | null,
): Profile | null {
  if (profiles.length === 0) return null;

  // 1. If there is a last active profile ID, prefer it
  if (lastActiveProfileId) {
    const match = profiles.find((p) => p.id === lastActiveProfileId);
    if (match) return match;
  }

  // 2. If there is a remembered profile ID for the last active module, check it
  if (lastActiveModule && selectedIds[lastActiveModule]) {
    const match = profiles.find((p) => p.id === selectedIds[lastActiveModule]);
    if (match) return match;
  }

  // 3. If there is any profile matching the last active module, pick the first
  if (lastActiveModule) {
    const match = profiles.find((p) => p.module === lastActiveModule);
    if (match) return match;
  }

  // 4. Otherwise pick the first available profile regardless of module
  return profiles[0];
}

export const useAuthStore = create<AuthState>((set, get) => {
  const initialSelected = loadSelectedProfileIds();
  const initialModule =
    typeof localStorage !== "undefined"
      ? ((localStorage.getItem("studyai.module") as ModuleId) ?? "NOTE_SPACE")
      : "NOTE_SPACE";
  const initialProfileId =
    typeof localStorage !== "undefined" ? localStorage.getItem("studyai.profile") : null;
  setActiveModule(initialModule);
  if (initialProfileId) {
    setActiveProfileId(initialProfileId);
  }
  
  setSessionExpiredHandler(() => {
    setActiveModule(null);
    setActiveProfileId(null);
    useWorkspaceStore.getState().resetWorkspace();
    set({
      email: null,
      profiles: [],
      profile: null,
      module: "NOTE_SPACE",
      selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null },
    });
  });
  
  return {
    email: typeof localStorage !== "undefined" ? localStorage.getItem("studyai.email") : null,
    profiles: [],
    profile: null,
    module: initialModule,
    selectedProfileIds: initialSelected,
    initialized: false,

    async init() {
      if (typeof localStorage === "undefined" || !localStorage.getItem("studyai.access")) {
        set({ initialized: true });
        return;
      }
      try {
        const allProfiles = await profilesApi.list();
        const lastProfileId = localStorage.getItem("studyai.profile");
        const lastModule =
          (localStorage.getItem("studyai.module") as ModuleId | null) ?? get().module;
        const selectedIds = loadSelectedProfileIds();

        const profile = resolveActiveProfile(allProfiles, selectedIds, lastProfileId, lastModule);
        if (profile) {
          const activeModule = (profile.module as ModuleId) ?? "NOTE_SPACE";
          saveSelectedProfileId(activeModule, profile.id);
          localStorage.setItem("studyai.profile", profile.id);
          persistModule(activeModule);
          setActiveModule(activeModule);
          setActiveProfileId(profile.id);

          set({
            profiles: allProfiles.filter((p) => p.module === activeModule),
            profile,
            module: activeModule,
            selectedProfileIds: { ...selectedIds, [activeModule]: profile.id },
            email: get().email ?? localStorage.getItem("studyai.email"),
            initialized: true,
          });
        } else {
          setActiveModule(null);
          setActiveProfileId(null);
          set({
            profiles: [],
            profile: null,
            module: "NOTE_SPACE",
            selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null },
            email: get().email ?? localStorage.getItem("studyai.email"),
            initialized: true,
          });
        }
      } catch {
        setTokens(null, null);
        localStorage.removeItem("studyai.email");
        setActiveModule(null);
        setActiveProfileId(null);
        useWorkspaceStore.getState().resetWorkspace();
        set({
          email: null,
          profiles: [],
          profile: null,
          module: "NOTE_SPACE",
          selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null },
          initialized: true,
        });
      }
    },

    async login(email, password) {
      await authApi.login(email, password);
      persistSession(email);

      const allProfiles = await profilesApi.list();
      const lastProfileId = localStorage.getItem("studyai.profile");
      const lastModule = localStorage.getItem("studyai.module") as ModuleId | null;
      const selectedIds = loadSelectedProfileIds();

      const profile = resolveActiveProfile(allProfiles, selectedIds, lastProfileId, lastModule);
      if (profile) {
        const activeModule = (profile.module as ModuleId) ?? "NOTE_SPACE";
        saveSelectedProfileId(activeModule, profile.id);
        localStorage.setItem("studyai.profile", profile.id);
        persistModule(activeModule);
        setActiveModule(activeModule);
        setActiveProfileId(profile.id);

        set({
          email,
          profiles: allProfiles.filter((p) => p.module === activeModule),
          profile,
          module: activeModule,
          selectedProfileIds: { ...selectedIds, [activeModule]: profile.id },
        });
      } else {
        setActiveModule(null);
        setActiveProfileId(null);
        set({
          email,
          profiles: [],
          profile: null,
          module: "NOTE_SPACE",
          selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null },
        });
      }
    },

    async register(email, password) {
      const data = await authApi.register(email, password);
      persistSession(email);
      let allProfiles: Profile[] = [];
      try {
        allProfiles = await profilesApi.list();
      } catch {
        allProfiles = [data.profile];
      }
      const profile = allProfiles.find((p) => p.id === data.profile.id) ?? data.profile;
      const activeModule = (profile.module as ModuleId) ?? "NOTE_SPACE";
      saveSelectedProfileId(activeModule, profile.id);
      localStorage.setItem("studyai.profile", profile.id);
      persistModule(activeModule);
      setActiveModule(activeModule);
      setActiveProfileId(profile.id);

      set({
        email,
        profiles: allProfiles.filter((p) => p.module === activeModule),
        profile,
        module: activeModule,
        selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null, [activeModule]: profile.id },
      });
    },

    async logout() {
      await authApi.logout();
      setActiveProfileId(null);
      setActiveModule(null);
      localStorage.removeItem("studyai.email");
      useWorkspaceStore.getState().resetWorkspace();
      set({
        email: null,
        profiles: [],
        profile: null,
      });
    },

    async refreshProfiles() {
      const allProfiles = await profilesApi.list();
      const currentProfile = get().profile;
      const currentModule = get().module;
      const selectedIds = get().selectedProfileIds;

      const profile = resolveActiveProfile(
        allProfiles,
        selectedIds,
        currentProfile?.id ?? localStorage.getItem("studyai.profile"),
        currentModule,
      );

      if (profile) {
        const activeModule = (profile.module as ModuleId) ?? "NOTE_SPACE";
        saveSelectedProfileId(activeModule, profile.id);
        localStorage.setItem("studyai.profile", profile.id);
        persistModule(activeModule);
        setActiveModule(activeModule);
        setActiveProfileId(profile.id);

        set({
          profiles: allProfiles.filter((p) => p.module === activeModule),
          profile,
          module: activeModule,
          selectedProfileIds: { ...selectedIds, [activeModule]: profile.id },
        });
      } else {
        setActiveModule(null);
        setActiveProfileId(null);
        set({
          profiles: [],
          profile: null,
          module: "NOTE_SPACE",
          selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null },
        });
      }
    },

    switchProfile(id) {
      const allKnown = get().profiles;
      const profile = allKnown.find((p) => p.id === id);
      if (!profile) return;
      get().switchToProfile(profile);
    },

    switchToProfile(profile) {
      const activeModule = (profile.module as ModuleId) ?? "NOTE_SPACE";
      saveSelectedProfileId(activeModule, profile.id);
      localStorage.setItem("studyai.profile", profile.id);
      persistModule(activeModule);
      setActiveModule(activeModule);
      setActiveProfileId(profile.id);

      const currentWs = useWorkspaceStore.getState();
      if (currentWs.profileId !== profile.id) {
        currentWs.resetWorkspace();
      }

      set((state) => ({
        profile,
        module: activeModule,
        profiles: state.profiles.some((p) => p.id === profile.id)
          ? state.profiles.map((p) => (p.id === profile.id ? profile : p))
          : [...state.profiles, profile],
        selectedProfileIds: { ...state.selectedProfileIds, [activeModule]: profile.id },
      }));
    },

    async addProfile(name, module?: ModuleId) {
      const targetModule = module ?? get().module;
      const clean = name.trim();
      if (!clean) throw new Error("Profile name cannot be blank.");
      const isDuplicate = get().profiles.some(
        (p) => p.module === targetModule && p.name.trim().toLowerCase() === clean.toLowerCase()
      );
      if (isDuplicate) {
        throw new Error("A profile with this name already exists in this module.");
      }
      const created = await profilesApi.create(clean, targetModule);
      const activeModule = (created.module as ModuleId) ?? targetModule;
      saveSelectedProfileId(activeModule, created.id);
      localStorage.setItem("studyai.profile", created.id);
      persistModule(activeModule);
      setActiveModule(activeModule);
      setActiveProfileId(created.id);

      const currentWs = useWorkspaceStore.getState();
      if (currentWs.profileId !== created.id) {
        currentWs.resetWorkspace();
      }

      set((state) => ({
        profiles: [...state.profiles.filter((p) => p.module === activeModule), created],
        profile: created,
        module: activeModule,
        selectedProfileIds: { ...state.selectedProfileIds, [activeModule]: created.id },
      }));
      return created;
    },

    async renameProfile(id, name) {
      const clean = name.trim();
      if (!clean) throw new Error("Profile name cannot be blank.");
      const current = get().profiles.find((p) => p.id === id);
      const targetModule = current?.module ?? get().module;
      const isDuplicate = get().profiles.some(
        (p) => p.id !== id && p.module === targetModule && p.name.trim().toLowerCase() === clean.toLowerCase()
      );
      if (isDuplicate) {
        throw new Error("A profile with this name already exists in this module.");
      }
      const updated = await profilesApi.rename(id, clean);
      set((state) => ({
        profiles: state.profiles.map((p) => (p.id === id ? updated : p)),
        profile: state.profile?.id === id ? updated : state.profile,
      }));
      return updated;
    },

    async deleteProfile(id) {
      await profilesApi.remove(id);
      const wasActive = get().profile?.id === id;
      if (typeof localStorage !== "undefined") {
        if (wasActive) {
          localStorage.removeItem("studyai.profile");
        }
        if (localStorage.getItem("studyai.profile.NOTE_SPACE") === id) {
          saveSelectedProfileId("NOTE_SPACE", null);
        }
        if (localStorage.getItem("studyai.profile.AI_CLASSROOM") === id) {
          saveSelectedProfileId("AI_CLASSROOM", null);
        }
      }
      if (wasActive) {
        useWorkspaceStore.getState().resetWorkspace();
        await get().refreshProfiles();
      } else {
        set((state) => ({
          profiles: state.profiles.filter((p) => p.id !== id),
          selectedProfileIds: {
            NOTE_SPACE: state.selectedProfileIds.NOTE_SPACE === id ? null : state.selectedProfileIds.NOTE_SPACE,
            AI_CLASSROOM: state.selectedProfileIds.AI_CLASSROOM === id ? null : state.selectedProfileIds.AI_CLASSROOM,
          },
        }));
      }
    },
  };
});

function persistSession(email: string): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem("studyai.email", email);
  }
}