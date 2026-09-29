import { apiRequest } from "./client";
import { listAll } from "./pagination";

export interface ReferenceDocumentItem {
  id: string;
  title: string;
  source_type: "TEXTBOOK" | "REFERENCE_PDF" | "LECTURE_MATERIAL";
  subject: string | null;
  subject_name: string | null;
  profile: string | null;
  scope: "global" | "profile";
  status: "PENDING" | "PROCESSING" | "READY" | "FAILED";
  page_count: number;
  chunk_count: number;
  error_message: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ReferenceStatusItem {
  id: string;
  title: string;
  status: "PENDING" | "PROCESSING" | "READY" | "FAILED";
  page_count: number;
  chunk_count: number;
  error_message: string;
  updated_at: string;
}
export const referencesApi = {
  list(params?: { subject?: string; profile?: string }): Promise<ReferenceDocumentItem[]> {
    const q = new URLSearchParams();
    if (params?.subject) q.set("subject", params.subject);
    if (params?.profile) q.set("profile", params.profile);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return listAll<ReferenceDocumentItem>(`/references/${qs}`);
  },

  get(id: string): Promise<ReferenceDocumentItem> {
    return apiRequest<ReferenceDocumentItem>(`/references/${id}/`);
  },

  getStatus(id: string): Promise<ReferenceStatusItem> {
    return apiRequest<ReferenceStatusItem>(`/references/${id}/status/`);
  },

  async upload(formData: FormData): Promise<ReferenceDocumentItem> {
    const token = typeof localStorage !== "undefined" ? localStorage.getItem("studyai.access") : null;
    let profileId: string | null = null;
    if (typeof localStorage !== "undefined") {
      try {
        const authData = JSON.parse(localStorage.getItem("studyai.auth") || "{}");
        profileId = authData?.state?.profile?.id || authData?.profileId || localStorage.getItem("studyai.profile");
      } catch {
        profileId = localStorage.getItem("studyai.profile");
      }
    }

    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (profileId) headers["X-Active-Profile"] = profileId;

    const res = await fetch("/api/v1/references/", {
      method: "POST",
      headers,
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg = err.detail || err.error?.message || err.message || `Upload failed (${res.status})`;
      throw new Error(msg);
    }

    return res.json();
  },

  remove(id: string): Promise<void> {
    return apiRequest<void>(`/references/${id}/`, {
      method: "DELETE",
    });
  },
};
