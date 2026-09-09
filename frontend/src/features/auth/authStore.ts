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
}

function loadSelectedProfileIds(): Record<ModuleId, string | null> {
  return {
    NOTE_SPACE: localStorage.getItem("studyai.profile.NOTE_SPACE"),
    AI_CLASSROOM: localStorage.getItem("studyai.profile.AI_CLASSROOM"),
  };
}

function saveSelectedProfileId(module: ModuleId, profileId: string | null) {
  if (profileId) {
    localStorage.setItem(`studyai.profile.${module}`, profileId);
  } else {
    localStorage.removeItem(`studyai.profile.${module}`);
  }
}

function persistModule(module: ModuleId) {
  localStorage.setItem("studyai.module", module);
}

function pickActiveForModule(profiles: Profile[], module: ModuleId, selectedIds: Record<ModuleId, string | null>): Profile | null {
  if (profiles.length === 0) return null;
  const remembered = selectedIds[module];
  if (remembered) {
    const found = profiles.find((p) => p.id === remembered);
    if (found) return found;
  }
  return profiles[0];
}

export const useAuthStore = create<AuthState>((set, get) => {
  const initialSelected = loadSelectedProfileIds();
  const initialModule = (localStorage.getItem("studyai.module") as ModuleId) ?? "NOTE_SPACE";
  setActiveModule(initialModule);
  
  setSessionExpiredHandler(() =>
    set({ email: null, profiles: [], profile: null, module: "NOTE_SPACE", selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null } }),
  );
  
  return {
    email: localStorage.getItem("studyai.email"),
    profiles: [],
    profile: null,
    module: initialModule,
    selectedProfileIds: initialSelected,
    initialized: false,

    async init() {
      if (!localStorage.getItem("studyai.access")) {
        set({ initialized: true });
        return;
      }
      try {
        const profiles = await profilesApi.list();
        const module = get().module;
        const selectedIds = get().selectedProfileIds;
        const profile = pickActiveForModule(profiles, module, selectedIds);
        if (profile) {
          saveSelectedProfileId(module, profile.id);
          localStorage.setItem("studyai.profile", profile.id);
          persistModule(module);
          setActiveModule(module);
          setActiveProfileId(profile.id);
        } else {
          setActiveModule(null);
          setActiveProfileId(null);
        }
        set({
          profiles,
          profile,
          module,
          selectedProfileIds: { ...selectedIds, [module]: profile?.id ?? null },
          email: get().email ?? localStorage.getItem("studyai.email"),
          initialized: true,
        });
      } catch {
        setTokens(null, null);
        localStorage.removeItem("studyai.email");
        set({ email: null, profiles: [], profile: null, module: "NOTE_SPACE", selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null }, initialized: true });
      }
    },

    async login(email, password) {
      await authApi.login(email, password);
      persistSession(email);
      const profiles = await profilesApi.list();
      const module = get().module;
      const selectedIds = get().selectedProfileIds;
      const profile = pickActiveForModule(profiles, module, selectedIds);
      if (profile) {
        saveSelectedProfileId(module, profile.id);
        localStorage.setItem("studyai.profile", profile.id);
        persistModule(module);
        setActiveModule(module);
        setActiveProfileId(profile.id);
      } else {
        setActiveModule(null);
        setActiveProfileId(null);
      }
      set({
        email,
        profiles,
        profile,
        module,
        selectedProfileIds: { ...selectedIds, [module]: profile?.id ?? null },
      });
    },

    async register(email, password) {
      const data = await authApi.register(email, password);
      persistSession(email);
      let profiles: Profile[] = [];
      try {
        profiles = await profilesApi.list();
      } catch {
        profiles = [data.profile];
      }
      const module = (data.profile.module as ModuleId) ?? "NOTE_SPACE";
      const profile = profiles.find((p) => p.id === data.profile.id) ?? data.profile;
      saveSelectedProfileId(module, profile.id);
      localStorage.setItem("studyai.profile", profile.id);
      persistModule(module);
      setActiveModule(module);
      setActiveProfileId(profile.id);
      set({
        email,
        profiles,
        profile,
        module,
        selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null, [module]: profile.id },
      });
    },

    async logout() {
      await authApi.logout();
      setActiveProfileId(null);
      setActiveModule(null);
      localStorage.removeItem("studyai.email");
      localStorage.removeItem("studyai.module");
      localStorage.removeItem("studyai.profile.NOTE_SPACE");
      localStorage.removeItem("studyai.profile.AI_CLASSROOM");
      localStorage.removeItem("studyai.profile");
      set({ email: null, profiles: [], profile: null, module: "NOTE_SPACE", selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null } });
    },

    async refreshProfiles() {
      const profiles = await profilesApi.list();
      const module = get().module;
      const selectedIds = get().selectedProfileIds;
      const profile = pickActiveForModule(profiles, module, selectedIds);
      if (profile) {
        saveSelectedProfileId(module, profile.id);
        localStorage.setItem("studyai.profile", profile.id);
        persistModule(module);
        setActiveModule(module);
        setActiveProfileId(profile.id);
      } else {
        setActiveModule(null);
        setActiveProfileId(null);
      }
      set({
        profiles,
        profile,
        module,
        selectedProfileIds: { ...selectedIds, [module]: profile?.id ?? null },
      });
    },

    switchProfile(id) {
      const profile = get().profiles.find((p) => p.id === id);
      if (!profile) return;
      const module = get().module;
      saveSelectedProfileId(module, id);
      localStorage.setItem("studyai.profile", id);
      persistModule(module);
      setActiveModule(module);
      setActiveProfileId(id);
      set({ profile, module, selectedProfileIds: { ...get().selectedProfileIds, [module]: id } });
    },

    switchToProfile(profile) {
      const module = profile.module as ModuleId;
      saveSelectedProfileId(module, profile.id);
      localStorage.setItem("studyai.profile", profile.id);
      localStorage.setItem("studyai.module", module);
      setActiveModule(module);
      setActiveProfileId(profile.id);
      set({
        profile,
        module,
        selectedProfileIds: { ...get().selectedProfileIds, [module]: profile.id },
      });
    },

    async addProfile(name, module?: ModuleId) {
      const created = await profilesApi.create(name, module);
      const profiles = [...get().profiles, created];
      const newModule = (created.module as ModuleId) ?? module ?? get().module;
      saveSelectedProfileId(newModule, created.id);
      localStorage.setItem("studyai.profile", created.id);
      persistModule(newModule);
      setActiveModule(newModule);
      setActiveProfileId(created.id);
      set({
        profiles,
        profile: created,
        module: newModule,
        selectedProfileIds: { ...get().selectedProfileIds, [newModule]: created.id },
      });
      return created;
    },
  };
});

function persistSession(email: string): void {
  localStorage.setItem("studyai.email", email);
}