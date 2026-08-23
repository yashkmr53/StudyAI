import type { ModuleId } from "../../types/modules";

/**
 * Minimal onboarding progress tracking (§6). Survives refreshes mid-flow;
 * completion is remembered per profile so returning users land in Subjects.
 */

const PROGRESS_KEY = "studyai.onboarding.progress";
const DONE_PREFIX = "studyai.onboarded.";

export type OnboardingStep = "profile" | "module" | "subjects";

interface Progress {
  lastStep: OnboardingStep;
  moduleChoice?: ModuleId;
}

export function loadProgress(): Progress | null {
  try {
    const raw = localStorage.getItem(PROGRESS_KEY);
    return raw ? (JSON.parse(raw) as Progress) : null;
  } catch {
    return null;
  }
}

export function saveProgress(update: Partial<Progress>): void {
  const current = loadProgress() ?? { lastStep: "profile" as OnboardingStep };
  localStorage.setItem(PROGRESS_KEY, JSON.stringify({ ...current, ...update }));
}

export function clearProgress(): void {
  localStorage.removeItem(PROGRESS_KEY);
}

export function isOnboarded(profileId: string): boolean {
  return localStorage.getItem(DONE_PREFIX + profileId) === "1";
}

export function markOnboarded(profileId: string): void {
  localStorage.setItem(DONE_PREFIX + profileId, "1");
  clearProgress();
}
