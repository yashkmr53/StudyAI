import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  defaultProfileModuleConfig,
  MODULE_SERVICE_MATRIX,
  type ModuleId,
  type ModuleServiceConfig,
  type ProfileModuleConfig,
  type ServiceId,
} from "../types/modules";

/**
 * Module/service configuration for the active profile session (§26).
 *
 * The config is loaded exactly once per profile session and cached in
 * memory; switching modules or re-rendering never re-reads it. Today it
 * persists locally per profile; swapping in a backend endpoint later only
 * touches `hydrateFor` (see docs/frontend/phase_11 assumptions).
 */

interface ModuleConfigState {
  byProfile: Record<string, ProfileModuleConfig>;
  /** Profile whose config is active this session (null until hydrated). */
  activeProfileId: string | null;

  /** Called once when a profile becomes active. Idempotent per session. */
  hydrateFor: (profileId: string, onboardingChoice?: ModuleId) => void;
  setDefaultModule: (profileId: string, moduleId: ModuleId) => void;
  configFor: (profileId: string | null | undefined) => ProfileModuleConfig;
}

export const useModuleConfigStore = create<ModuleConfigState>()(
  persist(
    (set, get) => ({
      byProfile: {},
      activeProfileId: null,

      hydrateFor(profileId, onboardingChoice) {
        if (get().activeProfileId === profileId) return; // once per session
        set((s) => ({
          activeProfileId: profileId,
          byProfile: s.byProfile[profileId]
            ? s.byProfile
            : {
                ...s.byProfile,
                [profileId]: defaultProfileModuleConfig(onboardingChoice ?? "NOTE_SPACE"),
              },
        }));
      },

      setDefaultModule(profileId, moduleId) {
        set((s) => {
          const existing = s.byProfile[profileId] ?? defaultProfileModuleConfig(moduleId);
          return {
            byProfile: { ...s.byProfile, [profileId]: { ...existing, defaultModule: moduleId } },
          };
        });
      },

      configFor(profileId) {
        if (!profileId) return defaultProfileModuleConfig();
        return (
          get().byProfile[profileId] ??
          defaultProfileModuleConfig()
        );
      },
    }),
    {
      name: "studyai.moduleconfig.v1",
      partialize: (s) => ({ byProfile: s.byProfile }),
    },
  ),
);

/** Convenience selector: services enabled for a module id. */
export function servicesFor(config: ProfileModuleConfig, moduleId: ModuleId): ModuleServiceConfig {
  return config.modules[moduleId] ?? MODULE_SERVICE_MATRIX[moduleId];
}

/** Convenience selector: is a single service enabled? */
export function hasService(
  config: ProfileModuleConfig,
  moduleId: ModuleId,
  service: ServiceId,
): boolean {
  return servicesFor(config, moduleId)[service];
}
