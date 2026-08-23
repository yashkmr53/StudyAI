import { create } from "zustand";
import type { ModuleId } from "../types/modules";

/**
 * Ephemeral UI state. The active module is deliberately *not* part of the
 * router: switching modules is local, instantaneous client-side state
 * within the subject workspace (§8, §28).
 */
interface UiState {
  /** subjectId -> currently displayed module (defaults from profile config). */
  activeModuleBySubject: Record<string, ModuleId>;
  setActiveModule: (subjectId: string, moduleId: ModuleId) => void;
}

export const useUiStore = create<UiState>((set) => ({
  activeModuleBySubject: {},
  setActiveModule(subjectId, moduleId) {
    set((s) => ({
      activeModuleBySubject: { ...s.activeModuleBySubject, [subjectId]: moduleId },
    }));
  },
}));
