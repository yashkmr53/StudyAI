import { apiRequest } from "./client";

export interface TagInfo {
  id: string;
  stable_key: string;
  display_name: string;
  linked_at?: string;
}

export const tagsApi = {
  async listForDocument(documentId: string): Promise<TagInfo[]> {
    const payload = await apiRequest<{ results: TagInfo[] }>(`/documents/${documentId}/tags`);
    return payload.results ?? [];
  },
};
