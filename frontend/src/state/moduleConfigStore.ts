import { create } from "zustand";
import { MODULE_SERVICE_MATRIX, type ModuleId, type ModuleServiceConfig } from "../types/modules";

/**
 * Module/service configuration for the active profile session (§26).
 *
 * The active module is derived from the profile's backend `module` field —
 * no client-side persistence, no per-profile cache.
 */

interface ModuleConfigState {
  /** Profile whose config is active this session (null until hydrated). */
  activeProfileId: string | null;

  /** Called once when a profile becomes active. Idempotent per session. */
  hydrateFor: (profileId: string) => void;

  /** Return the service matrix for a given module id. */
  servicesForModule: (moduleId: ModuleId) => ModuleServiceConfig;
}

export const useModuleConfigStore = create<ModuleConfigState>((set, get) => ({
  activeProfileId: null,

  hydrateFor(profileId) {
    if (get().activeProfileId === profileId) return;
    set({ activeProfileId: profileId });
  },

  servicesForModule(moduleId) {
    return MODULE_SERVICE_MATRIX[moduleId] ?? MODULE_SERVICE_MATRIX.NOTE_SPACE;
  },
}));

/** Convenience selector: services enabled for a module id. */
export function servicesFor(config: ModuleServiceConfig, _moduleId: ModuleId): ModuleServiceConfig {
  return config;
}

/** Convenience selector: is a single service enabled? */
export function hasService(
  config: ModuleServiceConfig,
  _moduleId: ModuleId,
  service: string,
): boolean {
  return !!config?.[service as keyof ModuleServiceConfig];
}