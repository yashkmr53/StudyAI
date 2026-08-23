import { createContext, useContext, type ReactNode } from "react";
import { useAuthStore } from "../../features/auth/authStore";
import { servicesFor, useModuleConfigStore } from "../../state/moduleConfigStore";
import { useUiStore } from "../../state/uiStore";
import type { ModuleId, ServiceId } from "../../types/modules";
import { MODULE_SERVICE_MATRIX } from "../../types/modules";

/**
 * The services contract consumed by UI components (§2). Components never
 * branch on "which module" — they ask whether a capability is enabled.
 */

export interface Services {
  transcription: boolean;
  write: boolean;
  enrichment: boolean;
  tests: boolean;
  qa: boolean;
  chat: boolean;
}

interface ModuleContextValue {
  moduleId: string;
  services: Services;
}

const ModuleContext = createContext<ModuleContextValue>({
  moduleId: "NOTE_SPACE",
  services: MODULE_SERVICE_MATRIX.NOTE_SPACE,
});

export function ModuleProvider({
  value,
  children,
}: {
  value: ModuleContextValue;
  children: ReactNode;
}) {
  return <ModuleContext.Provider value={value}>{children}</ModuleContext.Provider>;
}

/** Ask what the active session exposes instead of who owns it. */
export function useServices(): Services {
  return useContext(ModuleContext).services;
}

/**
 * Module state for a subject outside the workspace component tree
 * (note detail, tests, practice, chat routes). Same client-side model:
 * defaults come from profile config, overrides live in uiStore.
 */
export function useSubjectModule(subjectId: string | undefined): {
  moduleId: ModuleId;
  services: Services;
  setModule: (moduleId: ModuleId) => void;
} {
  const profile = useAuthStore((s) => s.profile);
  const config = useModuleConfigStore((s) => s.configFor(profile?.id));
  const override = useUiStore((s) => (subjectId ? s.activeModuleBySubject[subjectId] : undefined));
  const setActiveModule = useUiStore((s) => s.setActiveModule);
  const moduleId: ModuleId = override ?? config.defaultModule;
  return {
    moduleId,
    services: servicesFor(config, moduleId),
    setModule: (m) => {
      if (subjectId) setActiveModule(subjectId, m);
    },
  };
}

/**
 * Renders children only when the capability is enabled in the active
 * module's configuration. Optional fallback for explicit "locked" states.
 */
export function ServiceGate({
  service,
  children,
  fallback = null,
}: {
  service: ServiceId;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const services = useServices();
  return <>{services[service] ? children : fallback}</>;
}
