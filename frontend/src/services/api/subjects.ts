import { apiRequest } from "./client";
import type { Subject } from "../../types/api";
import { listAll, toList } from "./pagination";

export const subjectsApi = {
  /**
   * Subjects for one profile (server-side gating): ?profile={id}.
   * Ownership is enforced by the backend; foreign ids yield 404.
   */
  async list(profileId?: string): Promise<Subject[]> {
    const path = profileId
      ? `/subjects?profile=${encodeURIComponent(profileId)}`
      : "/subjects";
    return listAll<Subject>(path);
  },

  create(profileId: string, name: string): Promise<Subject> {
    return apiRequest<Subject>("/subjects", {
      method: "POST",
      body: { profile: profileId, name },
    });
  },

  rename(id: string, name: string): Promise<Subject> {
    return apiRequest<Subject>(`/subjects/${id}`, {
      method: "PATCH",
      body: { name },
    });
  },

  remove(id: string): Promise<void> {
    return apiRequest<void>(`/subjects/${id}`, { method: "DELETE" });
  },
};

export type { Subject };

export function normalizeSubjects(payload: unknown): Subject[] {
  return toList<Subject>(payload);
}
