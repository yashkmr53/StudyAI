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
import { getNote, putNote, allFolders, putFolder, closeDb } from "../src/db/indexeddb/db";
import { UNFILED_FOLDER_ID } from "../src/types/domain";

function resetDb(): Promise<void> {
  return new Promise((resolve) => {
    const req = indexedDB.deleteDatabase("studyai");
    req.onsuccess = () => resolve();
    req.onerror = () => resolve();
    req.onblocked = () => resolve();
  });
}

describe("Phase 10B — Frontend CRUD Store & API Integration", () => {
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

  describe("1. documentsApi methods", () => {
    it("rename calls PATCH /documents/{id} with title", async () => {
      const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "doc-1",
            profile: "p-1",
            title: "Updated Title",
            source: "upload",
            source_type: "image",
            schema_version: "1.0",
            created_at: "2026-09-24T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

      const res = await documentsApi.rename("doc-1", "Updated Title");
      expect(res.title).toBe("Updated Title");

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const [url, init] = fetchSpy.mock.calls[0];
      expect(url).toContain("/documents/doc-1");
      expect(init?.method).toBe("PATCH");
      expect(JSON.parse(init?.body as string)).toEqual({ title: "Updated Title" });
    });

    it("move calls PATCH /documents/{id} with notebook id or null", async () => {
      const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "doc-1",
            profile: "p-1",
            notebook: "nb-1",
            source: "upload",
            source_type: "image",
            schema_version: "1.0",
            created_at: "2026-09-24T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

      await documentsApi.move("doc-1", "nb-1");
      const [url, init] = fetchSpy.mock.calls[0];
      expect(url).toContain("/documents/doc-1");
      expect(init?.method).toBe("PATCH");
      expect(JSON.parse(init?.body as string)).toEqual({ notebook: "nb-1" });
    });

    it("remove calls DELETE /documents/{id}", async () => {
      const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(null, { status: 204 }),
      );

      await documentsApi.remove("doc-1");
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const [url, init] = fetchSpy.mock.calls[0];
      expect(url).toContain("/documents/doc-1");
      expect(init?.method).toBe("DELETE");
    });
  });

  describe("2. workspaceStore Note CRUD actions", () => {
    it("renameNote updates backend, IndexedDB, and store", async () => {
      // Seed a note
      const initialNote = {
        id: "doc-100",
        refId: "doc-100",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: UNFILED_FOLDER_ID,
        title: "Old Title",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putNote(initialNote);
      useWorkspaceStore.setState({ notes: [initialNote], profileId: "p-1" });

      const renameSpy = vi.spyOn(documentsApi, "rename").mockResolvedValueOnce({
        id: "doc-100",
        profile: "p-1",
        title: "New Fresh Title",
        source: "upload",
        source_type: "image",
        schema_version: "1.0",
        created_at: "2026-09-24T00:00:00Z",
      });

      await useWorkspaceStore.getState().renameNote("doc-100", "New Fresh Title");

      expect(renameSpy).toHaveBeenCalledWith("doc-100", "New Fresh Title");
      // Check store
      const inStore = useWorkspaceStore.getState().notes.find((n) => n.id === "doc-100");
      expect(inStore?.title).toBe("New Fresh Title");

      // Check IndexedDB
      const inDb = await getNote("doc-100");
      expect(inDb?.title).toBe("New Fresh Title");
    });

    it("renameNote failure bubbles error and leaves local state intact", async () => {
      const initialNote = {
        id: "doc-err",
        refId: "doc-err",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: UNFILED_FOLDER_ID,
        title: "Original Unchanged",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putNote(initialNote);
      useWorkspaceStore.setState({ notes: [initialNote], profileId: "p-1" });

      vi.spyOn(documentsApi, "rename").mockRejectedValueOnce(new Error("500 Internal Server Error"));

      await expect(
        useWorkspaceStore.getState().renameNote("doc-err", "Should Not Apply"),
      ).rejects.toThrow("500 Internal Server Error");

      // State and IDB should be untouched
      expect(useWorkspaceStore.getState().notes[0].title).toBe("Original Unchanged");
      const inDb = await getNote("doc-err");
      expect(inDb?.title).toBe("Original Unchanged");
    });

    it("moveNote updates backend, IndexedDB, and store", async () => {
      const initialNote = {
        id: "doc-200",
        refId: "doc-200",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: UNFILED_FOLDER_ID,
        title: "Moving Note",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putNote(initialNote);
      useWorkspaceStore.setState({ notes: [initialNote], profileId: "p-1" });

      const moveSpy = vi.spyOn(documentsApi, "move").mockResolvedValueOnce({
        id: "doc-200",
        profile: "p-1",
        notebook: "nb-target",
        source: "upload",
        source_type: "image",
        schema_version: "1.0",
        created_at: "2026-09-24T00:00:00Z",
      });

      await useWorkspaceStore.getState().moveNote("doc-200", "nb-target");

      expect(moveSpy).toHaveBeenCalledWith("doc-200", "nb-target");
      expect(useWorkspaceStore.getState().notes[0].folderId).toBe("nb-target");
      const inDb = await getNote("doc-200");
      expect(inDb?.folderId).toBe("nb-target");

      // Moving back to UNFILED_FOLDER_ID passes null to backend
      const unfileSpy = vi.spyOn(documentsApi, "move").mockResolvedValueOnce({
        id: "doc-200",
        profile: "p-1",
        notebook: null,
        source: "upload",
        source_type: "image",
        schema_version: "1.0",
        created_at: "2026-09-24T00:00:00Z",
      });

      await useWorkspaceStore.getState().moveNote("doc-200", UNFILED_FOLDER_ID);
      expect(unfileSpy).toHaveBeenCalledWith("doc-200", null);
      expect(useWorkspaceStore.getState().notes[0].folderId).toBe(UNFILED_FOLDER_ID);
    });

    it("moveNote failure bubbles error and leaves local state intact", async () => {
      const initialNote = {
        id: "doc-fail-move",
        refId: "doc-fail-move",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: UNFILED_FOLDER_ID,
        title: "Immobile Note",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putNote(initialNote);
      useWorkspaceStore.setState({ notes: [initialNote], profileId: "p-1" });

      vi.spyOn(documentsApi, "move").mockRejectedValueOnce(new Error("403 Forbidden"));

      await expect(
        useWorkspaceStore.getState().moveNote("doc-fail-move", "nb-target"),
      ).rejects.toThrow("403 Forbidden");

      expect(useWorkspaceStore.getState().notes[0].folderId).toBe(UNFILED_FOLDER_ID);
      const inDb = await getNote("doc-fail-move");
      expect(inDb?.folderId).toBe(UNFILED_FOLDER_ID);
    });

    it("removeNote removes from backend, deletes from IndexedDB, and updates subject noteCount", async () => {
      const noteA = {
        id: "doc-del-1",
        refId: "doc-del-1",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: UNFILED_FOLDER_ID,
        title: "Note to delete",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putNote(noteA);

      useWorkspaceStore.setState({
        subjects: [{ id: "sub-1", name: "DSA", noteCount: 1, folderCount: 0, lastOpenedAt: null }],
        notes: [noteA],
        profileId: "p-1",
      });

      const removeSpy = vi.spyOn(documentsApi, "remove").mockResolvedValueOnce(undefined);

      await useWorkspaceStore.getState().removeNote("doc-del-1");

      expect(removeSpy).toHaveBeenCalledWith("doc-del-1");
      expect(useWorkspaceStore.getState().notes).toHaveLength(0);
      expect(useWorkspaceStore.getState().subjects[0].noteCount).toBe(0);

      const inDb = await getNote("doc-del-1");
      expect(inDb).toBeUndefined();
    });

    it("removeNote failure preserves local note and IndexedDB record", async () => {
      const noteA = {
        id: "doc-del-err",
        refId: "doc-del-err",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: UNFILED_FOLDER_ID,
        title: "Note to survive error",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putNote(noteA);

      useWorkspaceStore.setState({
        subjects: [{ id: "sub-1", name: "DSA", noteCount: 1, folderCount: 0, lastOpenedAt: null }],
        notes: [noteA],
        profileId: "p-1",
      });

      vi.spyOn(documentsApi, "remove").mockRejectedValueOnce(new Error("Network Error"));

      await expect(useWorkspaceStore.getState().removeNote("doc-del-err")).rejects.toThrow("Network Error");

      expect(useWorkspaceStore.getState().notes).toHaveLength(1);
      const inDb = await getNote("doc-del-err");
      expect(inDb).toBeDefined();
    });
  });

  describe("3. workspaceStore Folder (Notebook) CRUD actions", () => {
    it("renameFolder calls backend, updates IndexedDB and Zustand", async () => {
      const folder = {
        id: "nb-1",
        key: "nb-1",
        subjectId: "sub-1",
        parentId: null,
        name: "Old Folder Name",
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putFolder(folder);
      useWorkspaceStore.setState({ folders: [folder], profileId: "p-1" });

      const renameSpy = vi.spyOn(notebooksApi, "rename").mockResolvedValueOnce(undefined);

      await useWorkspaceStore.getState().renameFolder("nb-1", "New Folder Name");

      expect(renameSpy).toHaveBeenCalledWith("nb-1", "New Folder Name");
      expect(useWorkspaceStore.getState().folders[0].name).toBe("New Folder Name");

      const inDb = (await allFolders()).find((f) => f.id === "nb-1");
      expect(inDb?.name).toBe("New Folder Name");
    });

    it("removeFolder demotes notes to UNFILED_FOLDER_ID and removes folder from IndexedDB", async () => {
      const folder = {
        id: "nb-del",
        key: "nb-del",
        subjectId: "sub-1",
        parentId: null,
        name: "Delete Me Folder",
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      const noteInFolder = {
        id: "doc-in-nb",
        refId: "doc-in-nb",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: "nb-del",
        title: "Inside Folder",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putFolder(folder);
      await putNote(noteInFolder);

      useWorkspaceStore.setState({
        subjects: [{ id: "sub-1", name: "DSA", noteCount: 1, folderCount: 1, lastOpenedAt: null }],
        folders: [folder],
        notes: [noteInFolder],
        profileId: "p-1",
      });

      const removeSpy = vi.spyOn(notebooksApi, "remove").mockResolvedValueOnce(undefined);

      await useWorkspaceStore.getState().removeFolder("nb-del");

      expect(removeSpy).toHaveBeenCalledWith("nb-del");
      expect(useWorkspaceStore.getState().folders).toHaveLength(0);
      expect(useWorkspaceStore.getState().subjects[0].folderCount).toBe(0);

      // Note must NOT be deleted, but demoted to UNFILED_FOLDER_ID
      const notes = useWorkspaceStore.getState().notes;
      expect(notes).toHaveLength(1);
      expect(notes[0].folderId).toBe(UNFILED_FOLDER_ID);

      const inDbNote = await getNote("doc-in-nb");
      expect(inDbNote?.folderId).toBe(UNFILED_FOLDER_ID);

      const inDbFolder = (await allFolders()).find((f) => f.id === "nb-del");
      expect(inDbFolder).toBeUndefined();
    });

    it("removeFolder failure leaves folder and notes intact", async () => {
      const folder = {
        id: "nb-keep",
        key: "nb-keep",
        subjectId: "sub-1",
        parentId: null,
        name: "Keep Folder",
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      const note = {
        id: "doc-keep",
        refId: "doc-keep",
        profileId: "p-1",
        subjectId: "sub-1",
        folderId: "nb-keep",
        title: "Keep Note",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putFolder(folder);
      await putNote(note);

      useWorkspaceStore.setState({
        subjects: [{ id: "sub-1", name: "DSA", noteCount: 1, folderCount: 1, lastOpenedAt: null }],
        folders: [folder],
        notes: [note],
        profileId: "p-1",
      });

      vi.spyOn(notebooksApi, "remove").mockRejectedValueOnce(new Error("Server Error"));

      await expect(useWorkspaceStore.getState().removeFolder("nb-keep")).rejects.toThrow("Server Error");

      expect(useWorkspaceStore.getState().folders).toHaveLength(1);
      expect(useWorkspaceStore.getState().notes[0].folderId).toBe("nb-keep");
    });
  });

  describe("4. workspaceStore Subject CRUD actions", () => {
    it("renameSubject calls backend and updates store", async () => {
      useWorkspaceStore.setState({
        subjects: [{ id: "sub-1", name: "Old Subject", noteCount: 0, folderCount: 0, lastOpenedAt: null }],
        profileId: "p-1",
      });

      const renameSpy = vi.spyOn(subjectsApi, "rename").mockResolvedValueOnce({
        id: "sub-1",
        profile: "p-1",
        name: "New Subject Name",
        created_at: "2026-09-24T00:00:00Z",
      });

      await useWorkspaceStore.getState().renameSubject("sub-1", "New Subject Name");

      expect(renameSpy).toHaveBeenCalledWith("sub-1", "New Subject Name");
      expect(useWorkspaceStore.getState().subjects[0].name).toBe("New Subject Name");
    });

    it("removeSubject deletes subject and folders, preserves notes with subjectId cleared", async () => {
      const folder = {
        id: "nb-sub-1",
        key: "nb-sub-1",
        subjectId: "sub-del",
        parentId: null,
        name: "Subject Folder",
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      const note = {
        id: "doc-sub-note",
        refId: "doc-sub-note",
        profileId: "p-1",
        subjectId: "sub-del",
        folderId: UNFILED_FOLDER_ID,
        title: "Preserved Note",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putFolder(folder);
      await putNote(note);

      useWorkspaceStore.setState({
        subjects: [{ id: "sub-del", name: "Delete Subject", noteCount: 1, folderCount: 1, lastOpenedAt: null }],
        folders: [folder],
        notes: [note],
        profileId: "p-1",
      });

      const removeSpy = vi.spyOn(subjectsApi, "remove").mockResolvedValueOnce(undefined);

      await useWorkspaceStore.getState().removeSubject("sub-del");

      expect(removeSpy).toHaveBeenCalledWith("sub-del");
      expect(useWorkspaceStore.getState().subjects).toHaveLength(0);
      expect(useWorkspaceStore.getState().folders).toHaveLength(0);

      // Note is preserved but unassigned from subject
      const remainingNotes = useWorkspaceStore.getState().notes;
      expect(remainingNotes).toHaveLength(1);
      expect(remainingNotes[0].subjectId).toBe("");

      const inDbNote = await getNote("doc-sub-note");
      expect(inDbNote?.subjectId).toBe("");
    });
  });

  describe("5. authStore Profile CRUD actions", () => {
    it("renameProfile updates profile in authStore", async () => {
      const p1 = {
        id: "prof-1",
        name: "Old Profile",
        module: "AI_CLASSROOM",
        created_at: "2026-09-24T00:00:00Z",
        updated_at: "2026-09-24T00:00:00Z",
      };
      useAuthStore.setState({
        profiles: [p1],
        profile: p1,
      });

      const renameSpy = vi.spyOn(profilesApi, "rename").mockResolvedValueOnce({
        ...p1,
        name: "New Profile Name",
      });

      await useAuthStore.getState().renameProfile("prof-1", "New Profile Name");

      expect(renameSpy).toHaveBeenCalledWith("prof-1", "New Profile Name");
      expect(useAuthStore.getState().profile?.name).toBe("New Profile Name");
      expect(useAuthStore.getState().profiles[0].name).toBe("New Profile Name");
    });

    it("deleteProfile removes non-active profile without resetting workspace", async () => {
      const active = {
        id: "prof-active",
        name: "Active Prof",
        module: "AI_CLASSROOM",
        created_at: "2026-09-24T00:00:00Z",
        updated_at: "2026-09-24T00:00:00Z",
      };
      const other = {
        id: "prof-other",
        name: "Other Prof",
        module: "AI_CLASSROOM",
        created_at: "2026-09-24T00:00:00Z",
        updated_at: "2026-09-24T00:00:00Z",
      };
      useAuthStore.setState({
        profiles: [active, other],
        profile: active,
      });

      const removeSpy = vi.spyOn(profilesApi, "remove").mockResolvedValueOnce(undefined);

      await useAuthStore.getState().deleteProfile("prof-other");

      expect(removeSpy).toHaveBeenCalledWith("prof-other");
      expect(useAuthStore.getState().profiles).toHaveLength(1);
      expect(useAuthStore.getState().profile?.id).toBe("prof-active");
    });

    it("deleteProfile on active profile resets workspace and switches to remaining profile", async () => {
      const active = {
        id: "prof-to-del",
        name: "Deleting Prof",
        module: "AI_CLASSROOM",
        created_at: "2026-09-24T00:00:00Z",
        updated_at: "2026-09-24T00:00:00Z",
      };
      const remaining = {
        id: "prof-remain",
        name: "Remaining Prof",
        module: "AI_CLASSROOM",
        created_at: "2026-09-24T00:00:00Z",
        updated_at: "2026-09-24T00:00:00Z",
      };

      localStorage.setItem("studyai.profile", "prof-to-del");
      localStorage.setItem("studyai.profile.AI_CLASSROOM", "prof-to-del");

      useAuthStore.setState({
        profiles: [active, remaining],
        profile: active,
        module: "AI_CLASSROOM",
      });

      useWorkspaceStore.setState({
        loaded: true,
        profileId: "prof-to-del",
        notes: [{ id: "n1", refId: "n1", profileId: "prof-to-del", subjectId: "s1", folderId: UNFILED_FOLDER_ID, title: "N", source: "upload", createdAt: "", updatedAt: "" }],
      });

      vi.spyOn(profilesApi, "remove").mockResolvedValueOnce(undefined);
      vi.spyOn(profilesApi, "list").mockResolvedValueOnce([remaining]);

      await useAuthStore.getState().deleteProfile("prof-to-del");

      // Verify active profile was switched to remaining
      expect(useAuthStore.getState().profile?.id).toBe("prof-remain");
      expect(localStorage.getItem("studyai.profile")).toBe("prof-remain");

      // Workspace store was reset
      expect(useWorkspaceStore.getState().profileId).toBeNull();
      expect(useWorkspaceStore.getState().notes).toHaveLength(0);
    });
  });

  describe("6. loadWorkspace Remote Precedence Reconciliation", () => {
    it("remote document title and notebook take precedence over local cache", async () => {
      const localCached = {
        id: "doc-cached-1",
        refId: "doc-cached-1",
        profileId: "prof-1",
        subjectId: "sub-1",
        folderId: "nb-old-local",
        title: "Old Local Title",
        source: "upload" as const,
        createdAt: "2026-09-24T00:00:00Z",
        updatedAt: "2026-09-24T00:00:00Z",
      };
      await putNote(localCached);

      // Backend returns updated title and new notebook association
      vi.spyOn(subjectsApi, "list").mockResolvedValueOnce([
        { id: "sub-1", profile: "prof-1", name: "DSA", created_at: "2026-09-24T00:00:00Z" },
      ]);
      vi.spyOn(notebooksApi, "list").mockResolvedValueOnce([
        { id: "nb-new-remote", profile: "prof-1", subject: "sub-1", title: "New Remote Folder", created_at: "2026-09-24T00:00:00Z", updated_at: "2026-09-24T00:00:00Z" },
      ]);
      vi.spyOn(documentsApi, "list").mockResolvedValueOnce({
        count: 1,
        results: [
          {
            id: "doc-cached-1",
            profile: "prof-1",
            subject: "sub-1",
            notebook: "nb-new-remote",
            title: "Remote Authoritative Title",
            source: "upload",
            source_type: "image",
            schema_version: "1.0",
            created_at: "2026-09-24T00:00:00Z",
          },
        ],
      });

      await useWorkspaceStore.getState().loadWorkspace("prof-1");

      const note = useWorkspaceStore.getState().notes.find((n) => n.id === "doc-cached-1");
      expect(note?.title).toBe("Remote Authoritative Title");
      expect(note?.folderId).toBe("nb-new-remote");

      // Verify that IndexedDB was updated with the authoritative values
      const updatedInDb = await getNote("doc-cached-1");
      expect(updatedInDb?.title).toBe("Remote Authoritative Title");
      expect(updatedInDb?.folderId).toBe("nb-new-remote");
    });
  });
});
