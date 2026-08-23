import { create } from "zustand";
import { appI18n } from "../i18n";
import {
  allFolders,
  allNotes,
  getNote,
  kvGet,
  kvSet,
  putFolder,
  putNote,
} from "../db/indexeddb/db";
import { notebooksApi } from "../services/api/notebooks";
import { subjectsApi } from "../services/api/subjects";
import type { FolderNode, NoteMeta, SubjectSummary } from "../types/domain";
import { UNFILED_FOLDER_ID } from "../types/domain";
import { childrenOf } from "../utils/folderTree";

/**
 * Workspace state: subjects, folders (Notebook entities), notes and their
 * placement. UI components read via selectors and never touch HTTP or
 * IndexedDB directly.
 *
 * Remote/local split: subjects & notebooks are real backend records;
 * hierarchy metadata + note placement persist locally until the backend
 * exposes `Notebook.parent` / `Document.folder` (documented seam).
 */

interface WorkspaceState {
  loaded: boolean;
  loading: boolean;
  error: string | null;
  /** Profile the workspace was loaded for (used for per-profile kv keys). */
  profileId: string | null;

  subjects: SubjectSummary[];
  folders: FolderNode[];
  notes: NoteMeta[];

  loadWorkspace: (profileId: string) => Promise<void>;
  resetWorkspace: () => void;

  createSubject: (profileId: string, name: string) => Promise<SubjectSummary>;
  renameSubject: (id: string, name: string) => Promise<void>;
  removeSubject: (id: string) => Promise<void>;
  touchSubject: (id: string) => Promise<void>;

  createFolder: (
    profileId: string,
    subjectId: string,
    name: string,
    parentId: string | null,
  ) => Promise<FolderNode>;

  placeNote: (noteId: string, folderId: string | null) => Promise<void>;
  registerCanvasNote: (input: {
    sessionId: string;
    profileId: string;
    subjectId: string;
    folderId: string | null;
    title?: string;
  }) => Promise<NoteMeta>;
  registerUploadNote: (input: {
    documentId: string;
    profileId: string;
    subjectId: string;
    folderId: string | null;
    title: string;
  }) => Promise<NoteMeta>;
  renameNote: (noteId: string, title: string) => Promise<void>;
  noteById: (noteId: string) => NoteMeta | undefined;
}

let lastOpenedCache: Record<string, string> = {};

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  loaded: false,
  loading: false,
  error: null,
  profileId: null,

  subjects: [],
  folders: [],
  notes: [],

  async loadWorkspace(profileId) {
    // Allow a different profile's load to supersede an in-flight one.
    if (get().loading && get().profileId === profileId) return;
    set({ loading: true, error: null, profileId });
    try {
      // Local cache is best-effort: IndexedDB failures must never blank
      // remotely-served data.
      const [remoteSubjects, remoteNotebooks, localFolders, localNotes] =
        await Promise.all([
          subjectsApi.list(profileId),
          notebooksApi.list().catch(() => []),
          allFolders().catch(() => []),
          allNotes().catch(() => []),
        ]);

      const subjects = remoteSubjects.filter((s) => s.profile === profileId);
      const subjectIds = new Set(subjects.map((s) => s.id));

      // Reconcile notebook records with locally-known hierarchy.
      const notebookIds = new Set(remoteNotebooks.map((nb) => nb.id));
      const reconciled = new Map<string, FolderNode>();
      for (const nb of remoteNotebooks) {
        const prior = localFolders.find((f) => f.id === nb.id);
        reconciled.set(nb.id, {
          id: nb.id,
          subjectId: nb.subject ?? "",
          parentId: prior?.parentId ?? null,
          name: nb.title,
          createdAt: nb.created_at,
          updatedAt: nb.updated_at,
        });
      }
      for (const lf of localFolders) {
        if (!notebookIds.has(lf.id)) {
          reconciled.set(lf.id, lf); // offline-created; kept until backend sync exists
        }
      }
      const folders = [...reconciled.values()].filter((f) =>
        subjectIds.has(f.subjectId),
      );

      try {
        lastOpenedCache =
          (await kvGet<Record<string, string>>(`lastOpened:${profileId}`)) ?? {};
      } catch {
        lastOpenedCache = {};
      }

      set({
        subjects: subjects.map((s) => summarize(s, folders, localNotes, lastOpenedCache[s.id])),
        folders,
        notes: localNotes.filter((n) => n.profileId === profileId && subjectIds.has(n.subjectId)),
        loaded: true,
        loading: false,
      });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : appI18n.t("errors.loadWorkspace"),
        loading: false,
        loaded: true,
      });
    }
  },

  resetWorkspace() {
    set({
      loaded: false,
      loading: false,
      error: null,
      profileId: null,
      subjects: [],
      folders: [],
      notes: [],
    });
  },

  async createSubject(profileId, name) {
    const created = await subjectsApi.create(profileId, name);
    const summary = summarize(created, get().folders, get().notes, undefined);
    set((s) => ({ subjects: [...s.subjects, summary] }));
    return summary;
  },

  async renameSubject(id, name) {
    await subjectsApi.rename(id, name);
    set((s) => ({
      subjects: s.subjects.map((x) => (x.id === id ? { ...x, name } : x)),
    }));
  },

  async removeSubject(id) {
    await subjectsApi.remove(id);
    set((s) => ({
      subjects: s.subjects.filter((x) => x.id !== id),
      folders: s.folders.filter((f) => f.subjectId !== id),
      notes: s.notes.filter((n) => n.subjectId !== id),
    }));
  },

  async touchSubject(id) {
    const at = new Date().toISOString();
    lastOpenedCache[id] = at;
    set((s) => ({
      subjects: s.subjects.map((x) => (x.id === id ? { ...x, lastOpenedAt: at } : x)),
    }));
    const pid = get().profileId ?? "default";
    try {
      await kvSet(`lastOpened:${pid}`, lastOpenedCache);
    } catch {
      /* non-fatal */
    }
  },

  async createFolder(profileId, subjectId, name, parentId) {
    // Real Notebook record server-side; hierarchy kept locally (seam).
    let created: FolderNode;
    try {
      created = await notebooksApi.create(profileId, subjectId, name);
    } catch {
      created = {
        id: `local-${crypto.randomUUID()}`,
        subjectId,
        parentId,
        name,
        updatedAt: new Date().toISOString(),
      };
    }
    const record = { ...created, parentId };
    await putFolder({ ...record, key: record.id });
    set((s) => ({ folders: [...s.folders, record] }));
    bumpSubjectCounters(set, subjectId);
    return record;
  },

  async placeNote(noteId, folderId) {
    const existing = get().notes.find((n) => n.id === noteId);
    if (!existing) return;
    const updated = { ...existing, folderId, updatedAt: new Date().toISOString() };
    await putNote(updated);
    set((s) => ({
      notes: s.notes.map((n) => (n.id === noteId ? updated : n)),
    }));
  },

  async registerCanvasNote(input) {
    const now = new Date().toISOString();
    const note: NoteMeta = {
      id: input.sessionId,
      refId: input.sessionId,
      profileId: input.profileId,
      subjectId: input.subjectId,
      folderId: input.folderId,
      title: input.title ?? defaultNoteTitle(now),
      source: "canvas",
      createdAt: now,
      updatedAt: now,
    };
    await putNote(note);
    set((s) => ({ notes: [...s.notes, note] }));
    bumpSubjectCounters(set, input.subjectId);
    return note;
  },

  async registerUploadNote(input) {
    const now = new Date().toISOString();
    const note: NoteMeta = {
      id: input.documentId,
      refId: input.documentId,
      profileId: input.profileId,
      subjectId: input.subjectId,
      folderId: input.folderId,
      title: input.title || defaultNoteTitle(now),
      source: "upload",
      createdAt: now,
      updatedAt: now,
    };
    await putNote(note);
    set((s) => ({ notes: [...s.notes, note] }));
    bumpSubjectCounters(set, input.subjectId);
    return note;
  },

  async renameNote(noteId, title) {
    const existing = await getNote(noteId);
    if (!existing) return;
    const updated = { ...existing, title, updatedAt: new Date().toISOString() };
    await putNote(updated);
    set((s) => ({ notes: s.notes.map((n) => (n.id === noteId ? updated : n)) }));
  },

  noteById(noteId) {
    return get().notes.find((n) => n.id === noteId);
  },
}));

/* ---- selectors (pure, take state slices) ---- */

type SetFn = (fn: (state: WorkspaceState) => Partial<WorkspaceState>) => void;

function bumpSubjectCounters(set: SetFn, subjectId: string) {
  set((s) => ({
    subjects: s.subjects.map((sub) => {
      if (sub.id !== subjectId) return sub;
      const subjectFolders = s.folders.filter((f) => f.subjectId === subjectId);
      return {
        ...sub,
        noteCount: s.notes.filter((n) => n.subjectId === subjectId).length,
        folderCount: subjectFolders.length,
      };
    }),
  }));
}

function summarize(
  subject: { id: string; name: string; created_at?: string },
  folders: FolderNode[],
  notes: NoteMeta[],
  lastOpenedAt: string | undefined,
): SubjectSummary {
  return {
    id: subject.id,
    name: subject.name,
    createdAt: subject.created_at,
    noteCount: notes.filter((n) => n.subjectId === subject.id).length,
    folderCount: folders.filter((f) => f.subjectId === subject.id).length,
    lastOpenedAt: lastOpenedAt ?? null,
  };
}

function defaultNoteTitle(iso: string): string {
  const d = new Date(iso);
  return appI18n.t("notes.defaults.title", {
    date: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  });
}

/* ---- derived helpers used by pages ---- */

export function selectFoldersForSubject(state: WorkspaceState, subjectId: string): FolderNode[] {
  return state.folders.filter((f) => f.subjectId === subjectId);
}

export function selectRootFolders(state: WorkspaceState, subjectId: string): FolderNode[] {
  return childrenOf(selectFoldersForSubject(state, subjectId), null);
}

export function selectNotesInFolder(state: WorkspaceState, subjectId: string, folderId: string): NoteMeta[] {
  return state.notes
    .filter((n) => n.subjectId === subjectId && n.folderId === folderId)
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function selectUnfiledNotes(state: WorkspaceState, subjectId: string): NoteMeta[] {
  return selectNotesInFolder(state, subjectId, UNFILED_FOLDER_ID);
}
