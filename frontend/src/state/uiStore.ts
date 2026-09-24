import { create } from "zustand";

interface UiState {
  sidebarCollapsed: boolean;
  mobileSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  closeMobileSidebar: () => void;
}

const STORAGE_KEY = "studyai.sidebar_collapsed";

export const useUiStore = create<UiState>((set, get) => ({
  sidebarCollapsed:
    typeof localStorage !== "undefined"
      ? localStorage.getItem(STORAGE_KEY) === "true"
      : false,
  mobileSidebarOpen: false,

  toggleSidebar: () => {
    // If on mobile screen (<= 640px), toggle mobile drawer
    if (typeof window !== "undefined" && window.innerWidth <= 640) {
      set((s) => ({ mobileSidebarOpen: !s.mobileSidebarOpen }));
      return;
    }
    const next = !get().sidebarCollapsed;
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(STORAGE_KEY, String(next));
    }
    set({ sidebarCollapsed: next });
  },

  setSidebarCollapsed: (collapsed: boolean) => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(STORAGE_KEY, String(collapsed));
    }
    set({ sidebarCollapsed: collapsed });
  },

  setMobileSidebarOpen: (open: boolean) => {
    set({ mobileSidebarOpen: open });
  },

  closeMobileSidebar: () => {
    set({ mobileSidebarOpen: false });
  },
}));
