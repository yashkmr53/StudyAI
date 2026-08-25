import { create } from "zustand";
import { profilesApi } from "../../services/api/profiles";
import { authApi } from "../../services/api/auth";
import { loadPersistedTokens, setActiveProfileId, setSessionExpiredHandler, setTokens } from "../../services/api/client";
import type { Profile } from "../../types/api";

loadPersistedTokens();

interface AuthState {
  email: string | null;
  /** All profiles owned by the account (profile switcher, §5). */
  profiles: Profile[];
  /** Currently active study context (§27 Current profile). */
  profile: Profile | null;
  initialized: boolean;
  init: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfiles: () => Promise<void>;
  switchProfile: (id: string) => void;
  addProfile: (name: string) => Promise<Profile>;
}

function pickActive(profiles: Profile[]): Profile | null {
  if (profiles.length === 0) return null;
  const remembered = localStorage.getItem("studyai.profile");
  return profiles.find((p) => p.id === remembered) ?? profiles[0];
}

export const useAuthStore = create<AuthState>((set, get) => {
  setSessionExpiredHandler(() =>
    set({ email: null, profiles: [], profile: null }),
  );
  return {
    email: localStorage.getItem("studyai.email"),
    profiles: [],
    profile: null,
    initialized: false,

    async init() {
      if (!localStorage.getItem("studyai.access")) {
        set({ initialized: true });
        return;
      }
      try {
        const profiles = await profilesApi.list();
      const profile = pickActive(profiles);
      if (profile) localStorage.setItem("studyai.profile", profile.id);
      setActiveProfileId(profile?.id ?? null);
      set({
        profiles,
        profile,
        email: get().email ?? localStorage.getItem("studyai.email"),
        initialized: true,
      });
      } catch {
        setTokens(null, null);
        localStorage.removeItem("studyai.email");
        set({ email: null, profiles: [], profile: null, initialized: true });
      }
    },

    async login(email, password) {
      await authApi.login(email, password);
      persistSession(email);
      const profiles = await profilesApi.list();
      const profile = pickActive(profiles);
      if (profile) localStorage.setItem("studyai.profile", profile.id);
      setActiveProfileId(profile?.id ?? null);
      set({ email, profiles, profile });
    },

    async register(email, password) {
      const data = await authApi.register(email, password);
      persistSession(email);
      // A fresh registration starts with its first profile already active.
      let profiles: Profile[] = [];
      try {
        profiles = await profilesApi.list();
      } catch {
        profiles = [data.profile];
      }
      const profile =
        profiles.find((p) => p.id === data.profile.id) ?? data.profile;
      localStorage.setItem("studyai.profile", profile.id);
      setActiveProfileId(profile.id);
      set({ email, profiles: profiles.length ? profiles : [profile], profile });
    },

    async logout() {
      await authApi.logout();
      setActiveProfileId(null);
      localStorage.removeItem("studyai.email");
      set({ email: null, profiles: [], profile: null });
    },

    async refreshProfiles() {
      const profiles = await profilesApi.list();
      const active = get().profile && profiles.some((p) => p.id === get().profile?.id)
        ? get().profile
        : pickActive(profiles);
      setActiveProfileId(active?.id ?? null);
      set({ profiles, profile: active });
    },

    switchProfile(id) {
      const profile = get().profiles.find((p) => p.id === id);
      if (!profile) return;
      localStorage.setItem("studyai.profile", id);
      setActiveProfileId(id);
      set({ profile });
    },

    async addProfile(name) {
      const created = await profilesApi.create(name);
      const profiles = [...get().profiles, created];
      localStorage.setItem("studyai.profile", created.id);
      setActiveProfileId(created.id);
      set({ profiles, profile: created });
      return created;
    },
  };
});

function persistSession(email: string): void {
  // tokens live in the api client; remember the session marker for reloads
  localStorage.setItem("studyai.email", email);
}
