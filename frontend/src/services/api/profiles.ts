import { apiRequest } from "./client";
import type { Profile } from "../../types/api";
import { toList } from "./pagination";

export const profilesApi = {
  /** All profiles owned by the authenticated user. */
  async list(): Promise<Profile[]> {
    return toList<Profile>(await apiRequest<unknown>("/profiles"));
  },

  create(name: string): Promise<Profile> {
    return apiRequest<Profile>("/profiles", { method: "POST", body: { name } });
  },

  rename(id: string, name: string): Promise<Profile> {
    return apiRequest<Profile>(`/profiles/${id}`, {
      method: "PATCH",
      body: { name },
    });
  },
};
