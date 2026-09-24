import "fake-indexeddb/auto";

// In-memory localStorage mock for node environment
const store: Record<string, string> = {};
const localStorageMock = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => {
    store[key] = String(value);
  },
  removeItem: (key: string) => {
    delete store[key];
  },
  clear: () => {
    for (const key of Object.keys(store)) delete store[key];
  },
  key: (i: number) => Object.keys(store)[i] ?? null,
  get length() {
    return Object.keys(store).length;
  },
};
Object.defineProperty(globalThis, "localStorage", {
  value: localStorageMock,
  writable: true,
  configurable: true,
});

import { describe, expect, it, vi, beforeEach } from "vitest";
import { useAuthStore } from "../src/features/auth/authStore";
import { useWorkspaceStore } from "../src/state/workspaceStore";
import { documentsApi } from "../src/services/api/documents";
import { profilesApi } from "../src/services/api/profiles";
import { closeDb } from "../src/db/indexeddb/db";
import { UNFILED_FOLDER_ID, type NoteMeta } from "../src/types/domain";

function resetDb(): Promise<void> {
  return new Promise((resolve) => {
    const req = indexedDB.deleteDatabase("studyai");
    req.onsuccess = () => resolve();
    req.onerror = () => resolve();
    req.onblocked = () => resolve();
  });
}

describe("Frontend Duplicate Name Prevention", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    localStorage.clear();
    await closeDb();
    await resetDb();
    useAuthStore.setState({
      email: "test@studyai.internal",
      profiles: [],
      profile: null,
      module: "AI_CLASSROOM",
      selectedProfileIds: { NOTE_SPACE: null, AI_CLASSROOM: null },
      initialized: true,
    });
    useWorkspaceStore.getState().resetWorkspace();
  });

  describe("Profiles Duplicate Name Prevention", () => {
    it("disallows adding a duplicate profile name in the same module (case-insensitive)", async () => {
      useAuthStore.setState({
        module: "AI_CLASSROOM",
        profiles: [
          {
            id: "p1",
            name: "Semester 1",
            module: "AI_CLASSROOM",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
      });

      const spyCreate = vi.spyOn(profilesApi, "create");

      await expect(
        useAuthStore.getState().addProfile("  semester 1  ", "AI_CLASSROOM"),
      ).rejects.toThrow("already exists in this module");

      expect(spyCreate).not.toHaveBeenCalled();
    });

    it("disallows renaming a profile to an existing profile name in the same module", async () => {
      useAuthStore.setState({
        module: "AI_CLASSROOM",
        profiles: [
          {
            id: "p1",
            name: "Semester 1",
            module: "AI_CLASSROOM",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
          {
            id: "p2",
            name: "Semester 2",
            module: "AI_CLASSROOM",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
      });

      const spyRename = vi.spyOn(profilesApi, "rename");

      await expect(
        useAuthStore.getState().renameProfile("p2", "SEMESTER 1"),
      ).rejects.toThrow("already exists in this module");

      expect(spyRename).not.toHaveBeenCalled();
    });

    it("allows renaming a profile to its own name", async () => {
      useAuthStore.setState({
        module: "AI_CLASSROOM",
        profiles: [
          {
            id: "p1",
            name: "Semester 1",
            module: "AI_CLASSROOM",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
      });

      vi.spyOn(profilesApi, "rename").mockResolvedValue({
        id: "p1",
        name: "Semester 1",
        module: "AI_CLASSROOM",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      });

      await expect(
        useAuthStore.getState().renameProfile("p1", "Semester 1"),
      ).resolves.toBeDefined();
    });
  });

  describe("Notes Duplicate Name Prevention", () => {
    it("disallows renaming a note to another note title in the same folder", async () => {
      const note1: NoteMeta = {
        id: "n1",
        refId: "doc-1",
        profileId: "p1",
        subjectId: "s1",
        folderId: "f1",
        title: "Lecture 1",
        source: "upload",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      const note2: NoteMeta = {
        id: "n2",
        refId: "doc-2",
        profileId: "p1",
        subjectId: "s1",
        folderId: "f1",
        title: "Lecture 2",
        source: "upload",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      useWorkspaceStore.setState({ notes: [note1, note2] });

      const spyRename = vi.spyOn(documentsApi, "rename");

      await expect(
        useWorkspaceStore.getState().renameNote("n2", "  lecture 1  "),
      ).rejects.toThrow("already exists in this folder");

      expect(spyRename).not.toHaveBeenCalled();
    });

    it("disallows renaming an unfiled note to another unfiled note title in the same subject", async () => {
      const note1: NoteMeta = {
        id: "n1",
        refId: "doc-1",
        profileId: "p1",
        subjectId: "s1",
        folderId: UNFILED_FOLDER_ID,
        title: "Homework 1",
        source: "upload",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      const note2: NoteMeta = {
        id: "n2",
        refId: "doc-2",
        profileId: "p1",
        subjectId: "s1",
        folderId: UNFILED_FOLDER_ID,
        title: "Homework 2",
        source: "upload",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      useWorkspaceStore.setState({ notes: [note1, note2] });

      const spyRename = vi.spyOn(documentsApi, "rename");

      await expect(
        useWorkspaceStore.getState().renameNote("n2", "homework 1"),
      ).rejects.toThrow("already exists in this subject");

      expect(spyRename).not.toHaveBeenCalled();
    });

    it("allows same note title in different folders under the same subject", async () => {
      const note1: NoteMeta = {
        id: "n1",
        refId: "doc-1",
        profileId: "p1",
        subjectId: "s1",
        folderId: "f1",
        title: "Lecture 1",
        source: "upload",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      const note2: NoteMeta = {
        id: "n2",
        refId: "doc-2",
        profileId: "p1",
        subjectId: "s1",
        folderId: "f2",
        title: "Different Title",
        source: "upload",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      useWorkspaceStore.setState({ notes: [note1, note2] });

      vi.spyOn(documentsApi, "rename").mockResolvedValue({
        id: "doc-2",
        profile: "p1",
        subject: "s1",
        notebook: "f2",
        title: "Lecture 1",
        source: "upload",
        source_type: "image",
        schema_version: "1",
        created_at: "2026-01-01T00:00:00Z",
      });

      await expect(
        useWorkspaceStore.getState().renameNote("n2", "Lecture 1"),
      ).resolves.not.toThrow();
    });

    it("disallows moving a note into a folder where a note with that title already exists", async () => {
      const note1: NoteMeta = {
        id: "n1",
        refId: "doc-1",
        profileId: "p1",
        subjectId: "s1",
        folderId: "f1",
        title: "Overview",
        source: "upload",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      const note2: NoteMeta = {
        id: "n2",
        refId: "doc-2",
        profileId: "p1",
        subjectId: "s1",
        folderId: "f2",
        title: "Overview",
        source: "upload",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      useWorkspaceStore.setState({ notes: [note1, note2] });

      const spyMove = vi.spyOn(documentsApi, "move");

      await expect(
        useWorkspaceStore.getState().moveNote("n1", "f2"),
      ).rejects.toThrow("already exists in the target folder");

      expect(spyMove).not.toHaveBeenCalled();
    });
  });
});
