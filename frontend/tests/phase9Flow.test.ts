import "fake-indexeddb/auto";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { parseEnrichment, enrichmentApi } from "../src/services/api/enrichment";
import { documentsApi } from "../src/services/api/documents";
import { useWorkspaceStore } from "../src/state/workspaceStore";
import { subjectsApi } from "../src/services/api/subjects";
import { notebooksApi } from "../src/services/api/notebooks";
import { UNFILED_FOLDER_ID } from "../src/types/domain";

describe("Phase 9 Frontend Flow Fixes", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("Citation Representation & Normalization", () => {
    it("preserves reference textbook citations with full metadata and quote content", async () => {
      const wirePayload = {
        id: "enrich-001",
        blocks: [
          {
            block_index: 0,
            block_type: "overview",
            title: "Cellular Respiration",
            content: "Glycolysis takes place in the cytoplasm.",
            citation: {
              source_refs: [
                {
                  source_type: "image",
                  page_number: 1,
                  document_id: "doc-student-1",
                  content: "Student scan snippet",
                },
              ],
              verification_status: "supported",
              verification_score: 0.92,
            },
          },
          {
            block_index: 1,
            block_type: "gap_fill",
            title: "Oxidative Phosphorylation",
            content: "ATP synthase generates ATP via chemiosmosis.",
            citation: {
              source_refs: [
                {
                  source_type: "reference",
                  chunk_id: "chunk-ref-164",
                  document_id: "doc-textbook-campbell",
                  title: "Campbell Biology 11th Ed.",
                  page_number: 164,
                  content:
                    "Oxidative Phosphorylation and the Electron Transport Chain: Complexes transfer electrons driving proton pumping across the inner membrane...",
                },
              ],
              verification_status: "supported",
              verification_score: 1.0,
            },
          },
        ],
      };

      const snap = await parseEnrichment(wirePayload);
      expect(snap.state).toBe("enriched");
      expect(snap.blocks).toHaveLength(2);

      // Student scan citation
      const studentBlock = snap.blocks[0];
      expect(studentBlock.citations[0].sourceType).toBe("image");
      expect(studentBlock.citations[0].page).toBe(1);

      // Reference textbook citation
      const refBlock = snap.blocks[1];
      const refCitation = refBlock.citations[0];
      expect(refCitation.sourceType).toBe("reference");
      expect(refCitation.title).toBe("Campbell Biology 11th Ed.");
      expect(refCitation.page).toBe(164);
      expect(refCitation.content).toContain("Oxidative Phosphorylation and the Electron Transport Chain");
      expect(refCitation.verificationStatus).toBe("supported");
      expect(refCitation.verificationScore).toBe(1.0);
    });
  });

  describe("Document Upload with Subject Association", () => {
    it("includes subject in documentsApi.create payload", async () => {
      const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            document: { id: "doc-1", profile: "prof-1", subject: "subj-bio-1" },
            page: { id: "page-1", document: "doc-1", page_number: 1, ocr_status: "pending" },
            upload: { url: "/storage/upload/key", method: "PUT", key: "key" },
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      );

      const res = await documentsApi.create("prof-1", "notes.png", "image", "subj-bio-1");
      expect(res.document.subject).toBe("subj-bio-1");

      const callArgs = fetchSpy.mock.calls[0];
      const body = JSON.parse(callArgs[1]?.body as string);
      expect(body.subject).toBe("subj-bio-1");
      expect(body.profile).toBe("prof-1");
      expect(body.filename).toBe("notes.png");
    });
  });

  describe("Workspace Store Remote Notes Loading & Merging", () => {
    it("loads remote documents and maps unfiled notes to UNFILED_FOLDER_ID", async () => {
      vi.spyOn(subjectsApi, "list").mockResolvedValueOnce([
        { id: "subj-1", profile: "prof-1", name: "Biology" },
      ]);
      vi.spyOn(notebooksApi, "list").mockResolvedValueOnce([]);
      vi.spyOn(documentsApi, "list").mockResolvedValueOnce({
        count: 2,
        results: [
          {
            id: "doc-remote-1",
            profile: "prof-1",
            subject: "subj-1",
            source: "upload",
            source_type: "image",
            schema_version: "1",
            created_at: "2026-09-22T00:00:00Z",
            title: "Remote Cell Lecture",
          },
          {
            id: "doc-remote-2",
            profile: "prof-1",
            subject: "subj-1",
            source: "upload",
            source_type: "image",
            schema_version: "1",
            created_at: "2026-09-22T01:00:00Z",
            title: "Remote Genetics",
          },
        ],
      });

      await useWorkspaceStore.getState().loadWorkspace("prof-1");

      const state = useWorkspaceStore.getState();
      expect(state.loaded).toBe(true);
      expect(state.notes.length).toBeGreaterThanOrEqual(2);

      const cellNote = state.notes.find((n) => n.id === "doc-remote-1");
      expect(cellNote).toBeDefined();
      expect(cellNote?.title).toBe("Remote Cell Lecture");
      expect(cellNote?.folderId).toBe(UNFILED_FOLDER_ID);
      expect(cellNote?.subjectId).toBe("subj-1");
    });

    it("registerUploadNote defaults to UNFILED_FOLDER_ID", async () => {
      const note = await useWorkspaceStore.getState().registerUploadNote({
        documentId: "doc-upload-new",
        profileId: "prof-1",
        subjectId: "subj-1",
        folderId: null as any,
        title: "New Note",
      });

      expect(note.folderId).toBe(UNFILED_FOLDER_ID);
      const stored = useWorkspaceStore.getState().notes.find((n) => n.id === "doc-upload-new");
      expect(stored?.folderId).toBe(UNFILED_FOLDER_ID);
    });
  });

  describe("Enrichment Polling State Machine", () => {
    it("enrichmentApi.get returns not_enriched on 404 without crashing", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(
          JSON.stringify({ error: { code: "NOT_FOUND", message: "No enrichment exists" } }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      );

      const snap = await enrichmentApi.get("doc-in-progress");
      expect(snap.state).toBe("not_enriched");
      expect(snap.blocks).toEqual([]);
    });

    it("enrichmentApi.generate returns job ID on 202 Accepted", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            enriched_note: null,
            job: { id: "job-12345", status: "queued" },
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      );

      const res = await enrichmentApi.generate("doc-1");
      expect(res.queued).toBe(true);
      expect(res.jobId).toBe("job-12345");
    });
  });
});
