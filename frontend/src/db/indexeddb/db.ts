import { openDB, type IDBPDatabase } from "idb";
import type { FolderNode, NoteMeta } from "../../types/domain";

/**
 * Local-first storage (architecture §2, §4):
 * - strokes are written to IndexedDB immediately
 * - the sync outbox queues operations for the backend
 *
 * v2 adds the workspace domain stores (folders / notes / kv). Folder
 * hierarchy and note placement are persisted here behind the workspace
 * repository seam until the backend grows `Notebook.parent` and
 * `Document.folder` fields (see docs/frontend/phase_11 assumptions).
 */
const DB_NAME = "studyai";
const DB_VERSION = 2;

export interface SyncOperation {
  id?: number;
  device_id: string;
  session_id: string;
  operation_type: string;
  client_sequence: number;
  payload: unknown;
  idempotency_key: string;
  status: "pending" | "sending" | "acknowledged" | "failed" | "retrying";
  created_at: string;
  acknowledged_at?: string;
}

export interface StrokeRecord {
  id: string;
  page_id: string;
  sequence_order: number;
  points: number[];
  /** Per-point pressure (same count as coordinate pairs) when available. */
  pressures?: number[];
  tool?: "pen" | "highlighter";
  color?: string;
  /** Base width in canvas px before pressure modulation. */
  width?: number;
  /** Local tombstone for undo; deleted strokes are skipped when rendering. */
  deleted_at?: string;
  updated_at: string;
}

export interface FolderRecord extends FolderNode {
  key: string;
}

export type NoteRecord = NoteMeta;

let dbPromise: Promise<IDBPDatabase> | null = null;

/** Close and forget the cached connection (tests, sign-out cleanup). */
export async function closeDb(): Promise<void> {
  if (!dbPromise) return;
  const pending = dbPromise;
  dbPromise = null;
  try {
    const db = await pending;
    db.close();
  } catch {
    /* never opened successfully */
  }
}

function getDb(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db, _oldVersion, _newVersion, _tx) {
        if (!db.objectStoreNames.contains("strokes")) {
          const strokes = db.createObjectStore("strokes", { keyPath: "id" });
          strokes.createIndex("by_page", "page_id");
        }
        if (!db.objectStoreNames.contains("outbox")) {
          const outbox = db.createObjectStore("outbox", { keyPath: "id", autoIncrement: true });
          outbox.createIndex("by_status", "status");
        }
        if (!db.objectStoreNames.contains("folders")) {
          const folders = db.createObjectStore("folders", { keyPath: "id" });
          folders.createIndex("by_subject", "subjectId");
        }
        if (!db.objectStoreNames.contains("notes")) {
          const notes = db.createObjectStore("notes", { keyPath: "id" });
          notes.createIndex("by_subject", "subjectId");
          notes.createIndex("by_folder", "folderId");
        }
        if (!db.objectStoreNames.contains("kv")) {
          db.createObjectStore("kv");
        }
      },
    });
  }
  return dbPromise;
}

/* ---- strokes ---- */

export async function putStroke(stroke: StrokeRecord): Promise<void> {
  const db = await getDb();
  await db.put("strokes", stroke);
}

export async function getStrokesForPage(pageId: string): Promise<StrokeRecord[]> {
  const db = await getDb();
  return db.getAllFromIndex("strokes", "by_page", pageId);
}

export async function getStrokesForSession(pageIds: string[]): Promise<StrokeRecord[]> {
  const perPage = await Promise.all(pageIds.map((p) => getStrokesForPage(p)));
  return perPage.flat();
}

/* ---- outbox ---- */

export async function enqueueOperation(op: Omit<SyncOperation, "id">): Promise<number> {
  const db = await getDb();
  const id = (await db.add("outbox", op)) as number;
  // client_sequence becomes the monotonic outbox id (per-device ordering)
  await db.put("outbox", { ...op, id, client_sequence: id });
  return id;
}

export async function pendingOperations(): Promise<SyncOperation[]> {
  const db = await getDb();
  return db.getAllFromIndex("outbox", "by_status", "pending");
}

export async function markAcknowledged(id: number): Promise<void> {
  const db = await getDb();
  await db.put("outbox", {
    ...(await db.get("outbox", id)),
    status: "acknowledged",
    acknowledged_at: new Date().toISOString(),
  });
}

export async function updateOperationStatus(id: number, status: SyncOperation["status"]): Promise<void> {
  const db = await getDb();
  const op = await db.get("outbox", id);
  if (op) {
    await db.put("outbox", { ...op, status });
  }
}

export async function getOperationsByStatus(status: SyncOperation["status"]): Promise<SyncOperation[]> {
  const db = await getDb();
  return db.getAllFromIndex("outbox", "by_status", status);
}

/* ---- folders (workspace domain, v2) ---- */

export async function allFolders(): Promise<FolderRecord[]> {
  const db = await getDb();
  return db.getAll("folders");
}

export async function putFolder(folder: FolderRecord): Promise<void> {
  const db = await getDb();
  await db.put("folders", folder);
}

export async function deleteFolderTree(folder: FolderRecord): Promise<void> {
  const db = await getDb();
  const all = await db.getAllFromIndex("folders", "by_subject", folder.subjectId);
  const doomed = new Set<string>([folder.id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const f of all) {
      if (f.parentId && doomed.has(f.parentId) && !doomed.has(f.id)) {
        doomed.add(f.id);
        grew = true;
      }
    }
  }
  const tx = db.transaction(["folders", "notes"], "readwrite");
  const folderStore = tx.objectStore("folders");
  const noteStore = tx.objectStore("notes");
  for (const id of doomed) {
    void folderStore.delete(id);
  }
  const notes = await noteStore.index("by_subject").getAll(folder.subjectId);
  for (const note of notes as NoteRecord[]) {
    if (note.folderId && doomed.has(note.folderId)) {
      await noteStore.put({ ...note, folderId: null }); // demote to Unfiled
    }
  }
  await tx.done;
}

/* ---- notes (workspace domain, v2) ---- */

export async function allNotes(): Promise<NoteRecord[]> {
  const db = await getDb();
  return db.getAll("notes");
}

export async function putNote(note: NoteRecord): Promise<void> {
  const db = await getDb();
  await db.put("notes", note);
}

export async function getNote(id: string): Promise<NoteRecord | undefined> {
  const db = await getDb();
  return db.get("notes", id);
}

export async function deleteNote(id: string): Promise<void> {
  const db = await getDb();
  await db.delete("notes", id);
}

/* ---- kv (subject metadata like lastOpenedAt) ---- */

export async function kvGet<T>(key: string): Promise<T | undefined> {
  const db = await getDb();
  return db.get("kv", key) as Promise<T | undefined>;
}

export async function kvSet(key: string, value: unknown): Promise<void> {
  const db = await getDb();
  await db.put("kv", value, key);
}
