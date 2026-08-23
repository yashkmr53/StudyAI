import "fake-indexeddb/auto";
import { describe, expect, it } from "vitest";

const DB_NAME = "studyai";

/**
 * Regression test for the Phase 11 v2 schema: the `kv` store must be created
 * before it is ever referenced. An earlier revision called
 * `tx.objectStore("kv")` before `createObjectStore("kv")`, which threw
 * NotFoundError inside the versionchange transaction and permanently rejected
 * the DB open — blanking the subjects screen for every user upgrading from a
 * pre-existing v1 database.
 */

function openV1(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("strokes")) {
        const strokes = db.createObjectStore("strokes", { keyPath: "id" });
        strokes.createIndex("by_page", "page_id");
      }
      if (!db.objectStoreNames.contains("outbox")) {
        const outbox = db.createObjectStore("outbox", { keyPath: "id", autoIncrement: true });
        outbox.createIndex("by_status", "status");
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function resetDb(): Promise<void> {
  return new Promise((resolve) => {
    const req = indexedDB.deleteDatabase(DB_NAME);
    req.onsuccess = () => resolve();
    req.onerror = () => resolve();
    req.onblocked = () => resolve();
  });
}

const sampleFolder = (id: string) => ({
  key: id,
  id,
  subjectId: "s1",
  parentId: null,
  name: "Trees",
});

describe("indexeddb v2 schema", () => {
  it("upgrades existing v1 databases and initializes fresh installs", async () => {
    await resetDb();

    /* ---- phase 1: upgrade over an existing v1 database ---- */
    const v1 = await openV1();
    expect(v1.objectStoreNames.contains("folders")).toBe(false);
    v1.close();

    const db = await import("../src/db/indexeddb/db"); // opens at version 2

    await db.putFolder(sampleFolder("f1"));
    expect((await db.allFolders()).map((f) => f.id)).toEqual(["f1"]);

    await db.kvSet("probe", { ok: true });
    expect(await db.kvGet("probe")).toEqual({ ok: true });

    /* ---- phase 2: brand-new install from scratch ---- */
    await db.closeDb(); // release the connection before deleting
    await resetDb();

    await db.putFolder(sampleFolder("f2")); // getDb() reopens cleanly
    expect((await db.allFolders()).some((f) => f.id === "f2")).toBe(true);

    await db.putNote({
      id: "n1",
      refId: "n1",
      profileId: "p1",
      subjectId: "s1",
      folderId: null,
      title: "Notes",
      source: "canvas",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    expect((await db.allNotes()).map((n) => n.id)).toEqual(["n1"]);
  });
});
