/**
 * Module & service configuration (UI prompt §2, §26).
 *
 * The two product modules own fixed sets of capabilities. The UI never
 * branches on "which module am I in" — it asks "is this service enabled".
 * The matrix below is the single source of truth for that mapping:
 *
 *                 TRANSCRIPTION  WRITE  ENRICHMENT  TESTS  QA  CHAT
 *   NoteSpace          ✓           ✓        ✗         ✗     ✗    ✗
 *   AI Classroom       ✓           ✓        ✓         ✓     ✓    ✓
 */

export type ModuleId = "NOTE_SPACE" | "AI_CLASSROOM";

export type ServiceId =
  | "transcription"
  | "write"
  | "enrichment"
  | "tests"
  | "qa"
  | "chat";

export type ModuleServiceConfig = Record<ServiceId, boolean>;

export const MODULE_SERVICE_MATRIX: Record<ModuleId, ModuleServiceConfig> = {
  NOTE_SPACE: {
    transcription: true,
    write: true,
    enrichment: false,
    tests: false,
    qa: false,
    chat: false,
  },
  AI_CLASSROOM: {
    transcription: true,
    write: true,
    enrichment: true,
    tests: true,
    qa: true,
    chat: true,
  },
};

export interface ProfileModuleConfig {
  defaultModule: ModuleId;
  modules: Record<ModuleId, ModuleServiceConfig>;
}

/** Config used until onboarding establishes a profile default (§6 step 3). */
export function defaultProfileModuleConfig(defaultModule: ModuleId = "NOTE_SPACE"): ProfileModuleConfig {
  return {
    defaultModule,
    modules: {
      NOTE_SPACE: { ...MODULE_SERVICE_MATRIX.NOTE_SPACE },
      AI_CLASSROOM: { ...MODULE_SERVICE_MATRIX.AI_CLASSROOM },
    },
  };
}
