import { describe, expect, it } from "vitest";
import { parseEnrichment } from "../src/services/api/enrichment";

describe("Enrichment parsing & insufficient content state", () => {
  it("maps empty_reason='insufficient_content' to insufficient_content state", async () => {
    const payload = {
      id: "test-note-1",
      ai_stale: false,
      empty_reason: "insufficient_content",
      blocks: [],
      job_status: "succeeded",
      created_at: "2026-10-18T12:00:00Z",
    };

    const snapshot = await parseEnrichment(payload);
    expect(snapshot.state).toBe("insufficient_content");
    expect(snapshot.blocks).toHaveLength(0);
    expect(snapshot.emptyReason).toBe("insufficient_content");
  });

  it("maps empty successful job with 0 blocks to insufficient_content state", async () => {
    const payload = {
      enriched_note: {
        id: "test-note-2",
        ai_stale: false,
        blocks: [],
        job_status: "succeeded",
        created_at: "2026-10-18T12:00:00Z",
      },
    };

    const snapshot = await parseEnrichment(payload);
    expect(snapshot.state).toBe("insufficient_content");
    expect(snapshot.blocks).toHaveLength(0);
  });

  it("maps blank_content and unreadable_content to insufficient_content state", async () => {
    const payloadBlank = {
      id: "test-note-blank",
      ai_stale: false,
      empty_reason: "blank_content",
      blocks: [],
      job_status: "succeeded",
    };
    const snapBlank = await parseEnrichment(payloadBlank);
    expect(snapBlank.state).toBe("insufficient_content");

    const payloadUnreadable = {
      id: "test-note-unreadable",
      ai_stale: false,
      empty_reason: "unreadable_content",
      blocks: [],
      job_status: "succeeded",
    };
    const snapUnreadable = await parseEnrichment(payloadUnreadable);
    expect(snapUnreadable.state).toBe("insufficient_content");
  });

  it("preserves out_of_date state when ai_stale is true", async () => {
    const payload = {
      id: "test-note-3",
      ai_stale: true,
      blocks: [{ block_index: 0, title: "Old concept", content: "old content" }],
      job_status: "succeeded",
    };

    const snapshot = await parseEnrichment(payload);
    expect(snapshot.state).toBe("out_of_date");
    expect(snapshot.blocks).toHaveLength(1);
  });

  it("preserves enriched state when valid blocks exist and note is not stale", async () => {
    const payload = {
      id: "test-note-4",
      ai_stale: false,
      blocks: [
        {
          block_index: 0,
          title: "Pointer Basics",
          content: "Pointers store memory addresses in C.",
          citation: {
            source_refs: [
              {
                source_type: "TEXTBOOK",
                title: "Let us C",
                page_number: 142,
                content: "A pointer is a variable that contains the address of another variable.",
                retrieval_score: 0.85,
              },
            ],
            verification_status: "supported",
            verification_score: 0.92,
          },
        },
      ],
      job_status: "succeeded",
    };

    const snapshot = await parseEnrichment(payload);
    expect(snapshot.state).toBe("enriched");
    expect(snapshot.blocks).toHaveLength(1);
    expect(snapshot.blocks[0].citations).toHaveLength(1);
    expect(snapshot.blocks[0].citations[0].sourceType).toBe("reference");
  });

  it("maps failed job statuses to failed state", async () => {
    const payload = {
      id: "test-note-5",
      ai_stale: false,
      blocks: [],
      job_status: "failed_dead_letter",
    };

    const snapshot = await parseEnrichment(payload);
    expect(snapshot.state).toBe("failed");
  });
});
