import { apiRequest, type RequestOptions } from "./client";
import type { ModuleId } from "../../types/modules";
import type { Profile } from "../../types/api";
import { toList } from "./pagination";

export const profilesApi = {
  /** All profiles owned by the authenticated user. */
  async list(module?: ModuleId): Promise<Profile[]> {
    const opts: RequestOptions = {};
    if (module) opts.module = module;
    return toList<Profile>(await apiRequest<unknown>("/profiles", opts));
  },

  create(name: string, module?: ModuleId): Promise<Profile> {
    return apiRequest<Profile>("/profiles", { method: "POST", body: { name }, module });
  },

  rename(id: string, name: string): Promise<Profile> {
    return apiRequest<Profile>(`/profiles/${id}`, {
      method: "PATCH",
      body: { name },
    });
  },

  setModule(id: string, module: ModuleId): Promise<Profile> {
    return apiRequest<Profile>(`/profiles/${id}`, {
      method: "PATCH",
      body: { module },
    });
  },
};
