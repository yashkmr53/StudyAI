import { createContext, useContext, type ReactNode } from "react";
import { useAuthStore } from "../../features/auth/authStore";
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
 * (note detail, tests, practice, chat routes). Module is derived from
 * the active profile's backend module — no client-side overrides (§27).
 */
export function useSubjectModule(_subjectId: string | undefined): {
  moduleId: ModuleId;
  services: Services;
} {
  const profile = useAuthStore((s) => s.profile);
  const moduleId: ModuleId = (profile?.module as ModuleId) ?? "NOTE_SPACE";
  const services: Services = MODULE_SERVICE_MATRIX[moduleId] ?? MODULE_SERVICE_MATRIX.NOTE_SPACE;
  return { moduleId, services };
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