/**
 * EnrichmentService client (§17–§19).
 *
 * GET  /documents/{id}/enrichment — latest enrichment snapshot
 * POST /documents/{id}/enrich     — trigger (or no-op when current)
 *
 * The wire format is parsed defensively into the UI's EnrichmentSnapshot so
 * partial backend responses degrade to "not_enriched" instead of crashing.
 */
import { apiRequest } from "./client";
import type { CitationRef, EnrichedBlock, EnrichmentState, EnrichmentSnapshot } from "../../types/domain";

interface WireSourceRef {
  source_type?: string;
  source_title?: string;
  title?: string;
  chunk_id?: string;
  document_id?: string;
  page_number?: number;
  page?: number;
  chapter?: string;
  section?: string;
  content?: string;
  bbox?: unknown;
  retrieval_score?: number | null;
}

interface WireCitation {
  source_refs?: WireSourceRef[];
  verification_status?: string;
  verification_score?: number | null;
  verifier_version?: string;
}

interface WireBlock {
  block_index?: number;
  block_kind?: "heading" | "student" | "addition" | "legacy";
  render_as?: "prose" | "code";
  topic_id?: string;
  block_type?: string;
  title?: string;
  content?: string;
  source_line_ids?: string[];
  support_status?: string;
  addition_kind?: string;
  citation?: WireCitation | null;
}

interface WireEnrichment {
  id?: string;
  status?: "ok" | "needs_attention";
  content_hash?: string;
  force_include_hash?: string;
  settings_version?: string;
  evidence_status_by_topic?: Record<string, string>;
  reference_library_changed?: boolean;
  subject_id?: string;
  subject_name?: string;
  excluded_segments?: Array<{
    segment_type: string;
    start_line_number: number;
    end_line_number: number;
    topic_description: string;
    reason: string;
    lineage_ids: string[];
  }>;
  ai_stale?: boolean;
  superseded?: boolean;
  created_at?: string;
  empty_reason?: string;
  blocks?: WireBlock[];
  job_status?: string;
  latest_job?: {
    id: string;
    status: string;
    outcome?: string;
    error_code?: string;
    message?: string;
    progress?: {
      stages_completed: string[];
      stages_done?: string[];
      current_stage?: string;
      topics_completed: number;
      topics_total: number;
    };
  } | null;
}

function normalizeCitations(block: WireBlock): CitationRef[] {
  const refs = block.citation?.source_refs ?? [];
  const verificationStatus = block.citation?.verification_status;
  const verificationScore = block.citation?.verification_score;

  return refs.map((r) => {
    const pageNum = typeof r.page_number === "number" ? r.page_number : (typeof r.page === "number" ? r.page : 1);
    const isReference = ["reference", "TEXTBOOK", "REFERENCE_PDF", "LECTURE_MATERIAL"].includes(r.source_type ?? "");
    return {
      page: pageNum,
      bbox: Array.isArray(r.bbox) ? r.bbox.map(Number) : null,
      sourceType: isReference ? "reference" : (r.source_type ?? "image"),
      content: r.content ?? "",
      chunkId: r.chunk_id,
      documentId: r.document_id,
      title: r.source_title || r.title,
      chapter: r.chapter,
      section: r.section,
      verificationStatus,
      verificationScore,
    };
  });
}

function snapshotFromWire(wire: WireEnrichment): EnrichmentSnapshot {
  let state: EnrichmentState = "not_enriched";
  const jobStatus = wire.latest_job?.status ?? wire.job_status;
  const outcome = wire.latest_job?.outcome;

  if (jobStatus === "running" || jobStatus === "queued") {
    state = "enriching";
  } else if (wire.ai_stale) {
    state = "out_of_date";
  } else if (Array.isArray(wire.blocks) && wire.blocks.length > 0) {
    state = "enriched";
  } else if (
    outcome === "insufficient_content" ||
    outcome === "no_study_content" ||
    wire.empty_reason === "insufficient_content" ||
    wire.empty_reason === "blank_content" ||
    wire.empty_reason === "unreadable_content" ||
    (jobStatus === "succeeded" && (!wire.blocks || wire.blocks.length === 0))
  ) {
    state = "insufficient_content";
  } else if (
    jobStatus === "failed_retryable" ||
    jobStatus === "failed_dead_letter" ||
    jobStatus === "cancelled" ||
    outcome === "coverage_bug"
  ) {
    state = "failed";
  }

  const blocks: EnrichedBlock[] = (wire.blocks ?? [])
    .map((b, i) => ({
      index: b.block_index ?? i,
      title: b.title ?? "",
      content: b.content ?? "",
      citations: normalizeCitations(b),
      blockKind: b.block_kind ?? "legacy",
      renderAs: b.render_as ?? "prose",
      topicId: b.topic_id,
      additionKind: b.addition_kind,
      supportStatus: b.support_status,
    }))
    .sort((a, b) => a.index - b.index);

  return {
    state,
    blocks,
    generatedAt: wire.created_at ?? null,
    emptyReason: wire.empty_reason ?? (wire.latest_job?.message || null),
    status: wire.status,
    excludedSegments: wire.excluded_segments,
    latestJob: wire.latest_job,
    aiStale: wire.ai_stale,
    evidenceStatusByTopic: wire.evidence_status_by_topic,
    referenceLibraryChanged: wire.reference_library_changed,
    subjectId: wire.subject_id,
    subjectName: wire.subject_name,
  };
}

export async function parseEnrichment(payload: unknown): Promise<EnrichmentSnapshot> {
  // The endpoint may answer with the enriched note object or {note, latest_job}.
  if (!payload || typeof payload !== "object") {
    return { state: "not_enriched", blocks: [], generatedAt: null };
  }
  const record = payload as Record<string, unknown>;
  const rawNote = (record.note ?? record.enriched_note ?? record) as WireEnrichment;
  const wire: WireEnrichment = {
    ...rawNote,
    reference_library_changed:
      typeof record.reference_library_changed === "boolean"
        ? record.reference_library_changed
        : rawNote.reference_library_changed,
    subject_id: (record.subject_id as string) ?? rawNote.subject_id,
    subject_name: (record.subject_name as string) ?? rawNote.subject_name,
    latest_job: (record.latest_job as WireEnrichment["latest_job"]) ?? rawNote.latest_job,
  };
  return snapshotFromWire(wire);
}

export const enrichmentApi = {
  /** Latest enrichment for a note; never throws for "missing". */
  async get(documentId: string): Promise<EnrichmentSnapshot> {
    try {
      return await parseEnrichment(
        await apiRequest<unknown>(`/documents/${documentId}/enrichment`),
      );
    } catch (err) {
      if (err instanceof Error && "status" in err && (err as { status: number }).status === 404) {
        return { state: "not_enriched", blocks: [], generatedAt: null };
      }
      throw err;
    }
  },

  /** Kick off generation. Returns the job id when one was queued. */
  async generate(
    documentId: string,
  ): Promise<{ queued: boolean; jobId: string | null; enrichedNote?: unknown }> {
    const payload = await apiRequest<Record<string, unknown>>(
      `/documents/${documentId}/enrich`,
      { method: "POST", body: {} },
    );
    const job = payload?.job as { id?: string } | null | undefined;
    return {
      queued: payload !== null,
      jobId: job?.id ?? null,
      enrichedNote: payload?.enriched_note,
    };
  },

  /** Check job status by ID. */
  async getJob(jobId: string): Promise<{ id: string; status: string; last_error?: string } | null> {
    try {
      return await apiRequest<{ id: string; status: string; last_error?: string }>(`/jobs/${jobId}`);
    } catch {
      return null;
    }
  },

  /** Dispatches an enrichment regeneration job with run nonce (§3.9). */
  async regenerate(
    documentId: string,
    forceRerun: boolean = true,
  ): Promise<{ queued: boolean; jobId: string | null }> {
    const payload = await apiRequest<Record<string, unknown>>(
      `/documents/${documentId}/enrichment/regenerate`,
      { method: "POST", body: { force_rerun: forceRerun } },
    );
    const job = payload?.job as { id?: string } | null | undefined;
    return {
      queued: payload !== null,
      jobId: job?.id ?? null,
    };
  },

  /** Forces segment inclusion and automatically dispatches a regeneration job (§3.9). */
  async forceInclude(
    documentId: string,
    lineIds: string[],
  ): Promise<{ queued: boolean; jobId: string | null }> {
    const payload = await apiRequest<Record<string, unknown>>(
      `/documents/${documentId}/enrichment/force-include`,
      { method: "POST", body: { force_include_line_ids: lineIds } },
    );
    const job = payload?.job as { id?: string } | null | undefined;
    return {
      queued: payload !== null,
      jobId: job?.id ?? null,
    };
  },
};
