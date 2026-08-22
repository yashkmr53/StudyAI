# API Reference — after Phase 6

Base `/api/v1` · Bearer auth · JSON.
Authoritative contract: [`../openapi.yaml`](../openapi.yaml).

Phase 1–5 endpoints unchanged. New in Phase 6 (§60 AI Classroom section):

---

## POST /documents/{id}/enrich — authenticated

| Scenario | Response |
|---|---|
| Active enrichment exists for current content | `200 {"enriched_note": {…}, "job": null}` |
| New/changed content | `202 {"enriched_note": null, "job": {…}}` — async A–F pipeline |
| Foreign/unknown document | `404` |
| No completed revisions / platform reference doc | `422 VALIDATION_ERROR` |

Side effects: at most one enrich job per descriptor hash; on success supersedes prior active note (retained with `superseded=true`).

## GET /documents/{id}/enrichment — authenticated

Latest active enriched note, nested:

```json
{
  "id": "…", "document": "…", "revision_ids": ["…"],
  "provider": "mock", "model": "mock-gpt",
  "prompt_version": "enrichment_draft:v1;gap_detection:v1;gap_filling:v1",
  "schema_version": "v1",
  "ai_stale": false,
  "blocks": [
    {
      "block_index": 0, "block_type": "overview", "title": "Overview",
      "content": "…", "generation_method": "llm",
      "source_chunk_ids": ["…"],
      "citation": {
        "source_refs": [{"source_type": "image", "chunk_id": "…", "document_id": "…",
                          "page_number": 1, "revision_id": "…", "retrieval_score": null}],
        "verification_status": "unsupported",
        "verification_score": 0.0,
        "verifier_version": "sim-v1"
      }
    }
  ],
  "created_at": "…"
}
```

Errors: `404` foreign/unknown or no enrichment yet.

## POST /documents/{id}/refresh-ai — authenticated

Forces regeneration regardless of existing artifact: supersedes the active note and enqueues a fresh enrich job → `202 {"enriched_note": null, "job": {…}}`. Old notes retained (`superseded=true`).

## Enrichment job semantics

- Job type `enrich`; idempotency key binds document + current revisions + prompt versions + model (+ refresh counter when forced).
- Failure ⇒ retryable → dead-letter per §19; canonical data untouched (§52).

---

## Not implemented

Everything else from spec §60: notebooks, documents tags/questions endpoints, tests, chat, revision planner.
