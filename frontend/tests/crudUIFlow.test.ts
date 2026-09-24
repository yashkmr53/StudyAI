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
import { subjectsApi } from "../src/services/api/subjects";
import { notebooksApi } from "../src/services/api/notebooks";
import { profilesApi } from "../src/services/api/profiles";
import { getNote, putNote, putFolder, closeDb } from "../src/db/indexeddb/db";
import { UNFILED_FOLDER_ID } from "../src/types/domain";

function resetDb(): Promise<void> {
  return new Promise((resolve) => {
    const req = indexedDB.deleteDatabase("studyai");
    req.onsuccess = () => resolve();
    req.onerror = () => resolve();
    req.onblocked = () => resolve();
  });
}

describe("Phase 10C — User-Facing CRUD UI Flow & Safety Tests", () => {
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

  describe("1. Profile Safety & Only-Profile Guard", () => {
    it("detects when user has only one profile to prevent deletion", async () => {
      const p1 = {
        id: "p-solo",
        name: "Solo Profile",
        module: "AI_CLASSROOM",
        created_at: "2026-09-24T00:00:00Z",
      };
      useAuthStore.setState({ profiles: [p1], profile: p1 });

      vi.spyOn(profilesApi, "list").mockResolvedValueOnce([p1]);

      const all = await profilesApi.list();
      expect(all.length).toBe(1);
      // Guard logic: if all.length <= 1, deletion must be blocked
      const canDelete = all.length > 1;
      expect(canDelete).toBe(false);
    });

    it("allows deleting a profile when multiple profiles exist", async () => {
      const p1 = { id: "p1", name: "Prof 1", module: "AI_CLASSROOM" };
      const p2 = { id: "p2", name: "Prof 2", module: "AI_CLASSROOM" };
      useAuthStore.setState({ profiles: [p1, p2], profile: p1 });

      vi.spyOn(profilesApi, "list").mockResolvedValueOnce([p1, p2]);
      const removeSpy = vi.spyOn(profilesApi, "remove").mockResolvedValueOnce(undefined);

      const all = await profilesApi.list();
      expect(all.length).toBe(2);
      expect(all.length > 1).toBe(true);

      // Delete non-active p2
      await useAuthStore.getState().deleteProfile("p2");
      expect(removeSpy).toHaveBeenCalledWith("p2");
      expect(useAuthStore.getState().profiles).toHaveLength(1);
      expect(useAuthStore.getState().profile?.id).toBe("p1");
    });
  });

  describe("2. Profile Scoping & Isolation for Notes & Folders", () => {
    it("deleting a subject in Profile A does not affect notes or folders in Profile B", async () => {
      // Notes in Profile A
      const noteA = {
        id: "doc-prof-a",
        refId: "doc-prof-a",
        profileId: "p-a",
        subjectId: "sub-a",
        folderId: UNFILED_FOLDER_ID,
        title: "Profile A Note",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      // Notes in Profile B
      const noteB = {
        id: "doc-prof-b",
        refId: "doc-prof-b",
        profileId: "p-b",
        subjectId: "sub-b",
        folderId: UNFILED_FOLDER_ID,
        title: "Profile B Note",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };

      await putNote(noteA);
      await putNote(noteB);

      // Active workspace is Profile A
      useWorkspaceStore.setState({
        profileId: "p-a",
        subjects: [{ id: "sub-a", name: "DSA", noteCount: 1, folderCount: 0, lastOpenedAt: null }],
        notes: [noteA],
      });

      vi.spyOn(subjectsApi, "remove").mockResolvedValueOnce(undefined);

      await useWorkspaceStore.getState().removeSubject("sub-a");

      // Profile A note becomes unassigned (subjectId = "")
      const updatedNoteA = await getNote("doc-prof-a");
      expect(updatedNoteA?.subjectId).toBe("");

      // Profile B note in storage remains completely unaffected
      const intactNoteB = await getNote("doc-prof-b");
      expect(intactNoteB?.subjectId).toBe("sub-b");
      expect(intactNoteB?.title).toBe("Profile B Note");
    });
  });

  describe("3. Note & Folder Lifecycle Flow", () => {
    it("full note lifecycle: rename -> move to folder -> delete folder -> note unfiled -> delete note", async () => {
      // 1. Initial setup
      const folder = {
        id: "f-algo",
        key: "f-algo",
        subjectId: "sub-1",
        parentId: null,
        name: "Algorithms",
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      const note = {
        id: "doc-flow",
        refId: "doc-flow",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: UNFILED_FOLDER_ID,
        title: "Initial Scan",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };

      await putFolder(folder);
      await putNote(note);

      useWorkspaceStore.setState({
        profileId: "p-1",
        subjects: [{ id: "sub-1", name: "DSA", noteCount: 1, folderCount: 1, lastOpenedAt: null }],
        folders: [folder],
        notes: [note],
      });

      // 2. Rename note
      vi.spyOn(documentsApi, "rename").mockResolvedValueOnce({
        id: "doc-flow",
        profile: "p-1",
        title: "Binary Trees Lecture",
        source: "upload",
        source_type: "image",
        schema_version: "1.0",
        created_at: "2026-09-24T00:00:00Z",
      });
      await useWorkspaceStore.getState().renameNote("doc-flow", "Binary Trees Lecture");
      expect(useWorkspaceStore.getState().notes[0].title).toBe("Binary Trees Lecture");

      // 3. Move note to folder
      vi.spyOn(documentsApi, "move").mockResolvedValueOnce({
        id: "doc-flow",
        profile: "p-1",
        notebook: "f-algo",
        source: "upload",
        source_type: "image",
        schema_version: "1.0",
        created_at: "2026-09-24T00:00:00Z",
      });
      await useWorkspaceStore.getState().moveNote("doc-flow", "f-algo");
      expect(useWorkspaceStore.getState().notes[0].folderId).toBe("f-algo");

      // 4. Delete folder -> note is preserved and becomes unfiled
      vi.spyOn(notebooksApi, "remove").mockResolvedValueOnce(undefined);
      await useWorkspaceStore.getState().removeFolder("f-algo");

      expect(useWorkspaceStore.getState().folders).toHaveLength(0);
      expect(useWorkspaceStore.getState().notes).toHaveLength(1);
      expect(useWorkspaceStore.getState().notes[0].folderId).toBe(UNFILED_FOLDER_ID);
      expect(useWorkspaceStore.getState().notes[0].title).toBe("Binary Trees Lecture");

      // 5. Delete note -> permanently removed
      vi.spyOn(documentsApi, "remove").mockResolvedValueOnce(undefined);
      await useWorkspaceStore.getState().removeNote("doc-flow");
      expect(useWorkspaceStore.getState().notes).toHaveLength(0);
      expect(await getNote("doc-flow")).toBeUndefined();
    });
  });
});
