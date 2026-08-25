import { apiRequest } from "./client";

export interface DocumentInfo {
  id: string;
  profile: string;
  subject?: string | null;
  source: string;
  source_type: string;
  schema_version: string;
  created_at: string;
}

export interface PageStatus {
  id: string;
  document: string;
  page_number: number;
  ocr_status: string;
  needs_review: boolean;
  current_revision_id: string | null;
  image_ref?: string | null;
}

export interface LinePayload {
  line_index: number;
  text: string;
  bbox?: number[] | null;
  confidence_score?: number | null;
  is_heading?: boolean;
}

export interface RevisionInfo {
  id: string;
  page: string;
  revision_number: number;
  content_hash: string;
  ocr_status: string;
  ocr_provider?: string | null;
  edited_by?: string | null;
  line_count: number;
  lines: LinePayload[];
}

export interface JobInfo {
  id: string;
  job_type: string;
  status: string;
  attempt_count: number;
  last_error?: string;
}

export interface DigitizedInfo {
  id: string;
  document: string;
  revision_ids?: { revision_id: string; page_number: number }[];
  renderer_version: string;
  file_size: number | null;
  created_at: string;
}

export const documentsApi = {
  create(profileId: string, filename: string, sourceType = "image") {
    return apiRequest<{ document: DocumentInfo; page: PageStatus; upload: { url: string; key: string } }>(
      "/documents",
      { method: "POST", body: { profile: profileId, source_type: sourceType, filename } },
    );
  },

  uploadToSignedUrl(url: string, data: ArrayBuffer | Blob, contentType: string) {
    return fetch(url, { method: "PUT", headers: { "Content-Type": contentType }, body: data }).then(
      async (r) => {
        if (!r.ok) throw new Error(`Upload failed (${r.status})`);
        if (r.status === 204) return undefined;
        return r.json().catch(() => undefined);
      },
    );
  },

  finalizeUpload(documentId: string, pageId: string) {
    return apiRequest<{ revision: RevisionInfo; job: JobInfo }>(`/documents/${documentId}/revisions`, {
      method: "POST",
      body: { page_id: pageId },
    });
  },

  list() {
    return apiRequest<{ count: number; results: DocumentInfo[] }>("/documents");
  },

  get(id: string) {
    return apiRequest<DocumentInfo>(`/documents/${id}`);
  },

  pages(documentId: string) {
    return apiRequest<PageStatus[]>(`/documents/${documentId}/pages`);
  },

  revisions(documentId: string, pageId?: string) {
    const q = pageId ? `?page=${pageId}` : "";
    return apiRequest<RevisionInfo[]>(`/documents/${documentId}/revisions${q}`);
  },

  submitEdit(documentId: string, pageId: string, lines: { line_index: number; text: string; is_heading?: boolean }[]) {
    return apiRequest<{ revision: RevisionInfo; job: null }>(`/documents/${documentId}/revisions`, {
      method: "POST",
      body: { page_id: pageId, lines },
    });
  },

  requestPdf(documentId: string) {
    return apiRequest<{ digitized_document: DigitizedInfo | null; job: JobInfo | null }>(
      `/documents/${documentId}/pdf`,
      { method: "POST" },
    );
  },

  listDigitized(documentId: string) {
    return apiRequest<{ count: number; results: DigitizedInfo[] }>(
      `/digitized-documents?document=${documentId}`,
    );
  },

  getDownloadUrl(digitizedId: string) {
    return apiRequest<{ url: string; expires_in: number; file_size: number | null }>(
      `/digitized-documents/${digitizedId}/download`,
    );
  },

  getPageDownloadUrl(pageId: string) {
    return apiRequest<{ url: string; expires_in: number; file_size: number | null }>(
      `/documents/pages/${pageId}/download`,
    );
  },
};
