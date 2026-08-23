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
  page_number?: number;
  bbox?: unknown;
}

interface WireCitation {
  source_refs?: WireSourceRef[];
}

interface WireBlock {
  block_index?: number;
  title?: string;
  content?: string;
  citation?: WireCitation | null;
}

interface WireEnrichment {
  id?: string;
  ai_stale?: boolean;
  superseded?: boolean;
  created_at?: string;
  blocks?: WireBlock[];
  job_status?: string;
}

function normalizeCitations(block: WireBlock): CitationRef[] {
  const refs = block.citation?.source_refs ?? [];
  return refs
    .filter((r) => typeof r.page_number === "number")
    .map((r) => ({
      page: r.page_number as number,
      bbox: Array.isArray(r.bbox) ? r.bbox.map(Number) : null,
    }));
}

function snapshotFromWire(wire: WireEnrichment): EnrichmentSnapshot {
  let state: EnrichmentState = "not_enriched";
  if (wire.job_status === "running" || wire.job_status === "queued") {
    state = "enriching";
  } else if (wire.ai_stale) {
    state = "out_of_date";
  } else if (Array.isArray(wire.blocks) && wire.blocks.length > 0) {
    state = "enriched";
  }

  const blocks: EnrichedBlock[] = (wire.blocks ?? [])
    .map((b, i) => ({
      index: b.block_index ?? i,
      title: b.title ?? "",
      content: b.content ?? "",
      citations: normalizeCitations(b),
    }))
    .sort((a, b) => a.index - b.index);

  return {
    state,
    blocks,
    generatedAt: wire.created_at ?? null,
  };
}

export async function parseEnrichment(payload: unknown): Promise<EnrichmentSnapshot> {
  // The endpoint may answer with the enriched note object or a bare status.
  if (!payload || typeof payload !== "object") {
    return { state: "not_enriched", blocks: [], generatedAt: null };
  }
  const record = payload as Record<string, unknown>;
  const wire: WireEnrichment =
    "ai_stale" in record || "blocks" in record
      ? (record as WireEnrichment)
      : ((record.enriched_note as WireEnrichment | undefined) ?? {});
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
  ): Promise<{ queued: boolean; jobId: string | null }> {
    const payload = await apiRequest<Record<string, unknown>>(
      `/documents/${documentId}/enrich`,
      { method: "POST", body: {} },
    );
    const job = payload.job as { id?: string } | null | undefined;
    return { queued: payload !== null, jobId: job?.id ?? null };
  },
};
