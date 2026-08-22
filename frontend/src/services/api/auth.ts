import { apiRequest, getRefreshToken, setTokens } from "./client";
import type { AuthTokens, Profile, RegisterResponse, User } from "../../types/api";

export const authApi = {
  async register(email: string, password: string): Promise<RegisterResponse> {
    const data = await apiRequest<RegisterResponse>("/auth/register", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    setTokens(data.access, data.refresh);
    return data;
  },

  async login(email: string, password: string): Promise<AuthTokens & { user?: User }> {
    const data = await apiRequest<AuthTokens>("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    setTokens(data.access, data.refresh);
    return data;
  },

  async logout(): Promise<void> {
    const refresh = getRefreshToken();
    try {
      if (refresh) {
        await apiRequest<void>("/auth/logout", { method: "POST", body: { refresh } });
      }
    } finally {
      setTokens(null, null);
    }
  },

  async requestPasswordReset(email: string): Promise<void> {
    await apiRequest<{ detail: string }>("/auth/password-reset", {
      method: "POST",
      body: { email },
      auth: false,
    });
  },

  async me(): Promise<Profile[]> {
    return apiRequest<Profile[]>("/profiles");
  },
};
