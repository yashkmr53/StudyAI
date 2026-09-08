import { describe, expect, it } from "vitest";
import {
  defaultProfileModuleConfig,
  MODULE_SERVICE_MATRIX,
} from "../src/types/modules";
import { hasService, servicesFor } from "../src/state/moduleConfigStore";

/**
 * The acceptance-criteria matrix (UI prompt §35):
 *
 *                  TRANSCRIPTION WRITE ENRICHMENT TESTS QA CHAT
 *   NoteSpace           ✓         ✓       ✗        ✗   ✗   ✗
 *   AI Classroom        ✓         ✓       ✓        ✓   ✓   ✓
 */
describe("module service matrix", () => {
  it("NoteSpace exposes only transcription + write", () => {
    const ns = MODULE_SERVICE_MATRIX.NOTE_SPACE;
    expect(ns.transcription).toBe(true);
    expect(ns.write).toBe(true);
    expect(ns.enrichment).toBe(false);
    expect(ns.tests).toBe(false);
    expect(ns.qa).toBe(false);
    expect(ns.chat).toBe(false);
  });

  it("AI Classroom exposes every service", () => {
    const ai = MODULE_SERVICE_MATRIX.AI_CLASSROOM;
    for (const enabled of Object.values(ai)) {
      expect(enabled).toBe(true);
    }
  });

  it("selectors answer per-service questions without module branching", () => {
    const ns = MODULE_SERVICE_MATRIX.NOTE_SPACE;
    const ai = MODULE_SERVICE_MATRIX.AI_CLASSROOM;
    expect(hasService(ns, "NOTE_SPACE", "enrichment")).toBe(false);
    expect(hasService(ns, "NOTE_SPACE", "write")).toBe(true);
    expect(hasService(ai, "AI_CLASSROOM", "enrichment")).toBe(true);
    expect(servicesFor(ai, "AI_CLASSROOM").chat).toBe(true);
  });

  it("default config uses NoteSpace unless told otherwise", () => {
    expect(defaultProfileModuleConfig().defaultModule).toBe("NOTE_SPACE");
    expect(defaultProfileModuleConfig("AI_CLASSROOM").defaultModule).toBe("AI_CLASSROOM");
  });
});