# API Reference — after Phase 5

Base `/api/v1` · Bearer auth · JSON.
Authoritative contract: [`../openapi.yaml`](../openapi.yaml).

Phase 1–4 endpoints unchanged (auth, profiles, subjects, canvas, documents incl. PDF endpoints, jobs). New in Phase 5:

---

## POST /search — authenticated *(extension beyond §60 blueprint — decision F-004)*

Hybrid retrieval over the caller's notes plus READY reference books.

Request:

```json
{
  "query": "dijkstra shortest paths",
  "subject": "<uuid>",            // optional scope
  "top_k": 8,                      // optional, 1–50 (default 8)
  "include_reference": true       // optional
}
```

Response `200`:

```json
{
  "query": "dijkstra shortest paths",
  "count": 2,
  "results": [
    {
      "chunk_id": "…",
      "document_id": "…",
      "source_type": "image",
      "page_start": 1,
      "page_end": 1,
      "snippet": "Dijkstra computes shortest paths in weighted graphs. …",
      "scores": { "dense": 0.0164, "keyword": 0.0164, "rrf": 0.032787 }
    },
    {
      "chunk_id": "…",
      "source_type": "reference",
      "scores": { "dense": null, "keyword": 0.0164, "rrf": 0.016129 }
    }
  ]
}
```

Errors: `401` unauthenticated; `422` validation / unknown subject for this user.

Semantics:
- Scoping enforced server-side: results come only from the caller's profiles plus platform reference chunks whose book is READY.
- Stale chunks are never returned.
- Scores: per-channel RRF contributions (`1/(60+rank)`); `dense: null` when the dense leg is unavailable (non-PostgreSQL runs).
- Idempotent read-only operation.

---

## Not implemented

Everything else from spec §60 beyond phases 1–4 + the above: notebooks, enrich/tags/questions/refresh-ai, tests, chat, revision planner.
