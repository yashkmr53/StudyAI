import { apiRequest } from "./client";
import type { FolderNode } from "../../types/domain";
import { listAll } from "./pagination";

interface NotebookDto {
  id: string;
  profile: string;
  subject: string | null;
  title: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

function toFolder(dto: NotebookDto): FolderNode {
  return {
    id: dto.id,
    subjectId: dto.subject ?? "",
    parentId: null, // hierarchy metadata lives in the folder-tree store until
    // the backend exposes a parent field on Notebook.
    name: dto.title,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

export const notebooksApi = {
  async list(): Promise<NotebookDto[]> {
    return listAll<NotebookDto>("/notebooks");
  },

  create(
    profileId: string,
    subjectId: string,
    title: string,
  ): Promise<FolderNode> {
    return apiRequest<NotebookDto>("/notebooks", {
      method: "POST",
      body: { profile: profileId, subject: subjectId, title },
    }).then(toFolder);
  },

  rename(id: string, title: string): Promise<void> {
    return apiRequest<void>(`/notebooks/${id}`, {
      method: "PATCH",
      body: { title },
    });
  },

  remove(id: string): Promise<void> {
    return apiRequest<void>(`/notebooks/${id}`, { method: "DELETE" });
  },
};
