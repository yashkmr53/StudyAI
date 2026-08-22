import { create } from "zustand";
import { authApi } from "../../services/api/auth";
import { loadPersistedTokens, setSessionExpiredHandler, setTokens } from "../../services/api/client";
import type { Profile } from "../../types/api";

loadPersistedTokens();

interface AuthState {
  email: string | null;
  profile: Profile | null;
  initialized: boolean;
  init: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => {
  setSessionExpiredHandler(() => set({ email: null, profile: null }));
  return {
    email: localStorage.getItem("studyai.email"),
    profile: null,
    initialized: false,

    async init() {
      if (!localStorage.getItem("studyai.access")) {
        set({ initialized: true });
        return;
      }
      try {
        const profiles = await authApi.me();
        set({ profile: profiles[0] ?? null, initialized: true });
      } catch {
        setTokens(null, null);
        localStorage.removeItem("studyai.email");
        set({ email: null, profile: null, initialized: true });
      }
    },

    async login(email, password) {
      await authApi.login(email, password);
      persistSession(email);
      const profiles = await authApi.me();
      set({ email, profile: profiles[0] ?? null });
    },

    async register(email, password) {
      const data = await authApi.register(email, password);
      persistSession(email);
      set({ email, profile: data.profile });
    },

    async logout() {
      await authApi.logout();
      localStorage.removeItem("studyai.email");
      set({ email: null, profile: null });
    },
  };
});

function persistSession(email: string): void {
  // tokens live in the api client; remember the session marker for reloads
  localStorage.setItem("studyai.email", email);
}
