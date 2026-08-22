# API Reference — after Phase 7

Base `/api/v1` · Bearer auth · JSON.
Authoritative contract: [`../openapi.yaml`](../openapi.yaml).

Phase 1–6 endpoints unchanged. New in Phase 7 (§60 learning endpoints):

---

## Tags

### GET /documents/{id}/tags
Stable tags linked to the document: `{"results": [{"id","stable_key","display_name","linked_at"}]}`.
Foreign document → 404. Documents without a subject have no tags.

## Tests

### POST /tests — authenticated

`{"subject": "<uuid>"?, "num_questions": 5}` → `201` test instance:

```json
{
  "id": "…", "subject": "…", "type": "practice",
  "questions": [
    { "id": "…", "difficulty": "medium", "prompt": "Which statement…",
      "options": ["…","…","…","…"],
      "answered": false, "selected_index": null, "correct": null }
  ]
}
```

Selection is deterministic (weakness/recency/difficulty priority); same state ⇒ identical set. Empty selection possible if no eligible questions exist.

### GET /tests · GET /tests/{id}
List (summaries) / detail incl. questions and per-question answered state.

### POST /tests/{id}/attempts — authenticated

Request `{"question_id": "<uuid>", "selected_index": 0-3, "confidence": 0..1?}`.

Response `201`:

```json
{
  "attempt": { "id": "…", "correct": true, "answer_index": 1, "answered_at": "…" },
  "mastery": { "tag": "939cd7", "value": 0.38, "status": "weak" }
}
```

Errors: `409 IDEMPOTENCY_CONFLICT` on replay; `422` question not in this test.

Grading is transactional with mastery update via MasteryScoringService (§56).

## Chat

### POST /chat/sessions — authenticated
`{"subject": "<uuid>"?, "title"?: ""}` → `201 session`.

### GET /chat/sessions · GET /chat/sessions/{id} — authenticated
List/retrieve own sessions.

### GET + POST /chat/sessions/{id}/messages — authenticated

POST `{content}` → assistant reply `201`:

```json
{
  "id": "…", "role": "assistant",
  "content": "Based on your materials: Dijkstra's algorithm computes …",
  "citations": [
    { "source_type": "image", "chunk_id": "…", "page_start": 1, "page_end": 1,
      "snippet": "…", "rrf_score": 0.0328 },
    { "verification_status": "supported", "verification_score": 0.83,
      "verifier_version": "sim-v1" }
  ],
  "model": "mock-gpt", "prompt_version": "chat:v1"
}
```

Retrieval scoping guarantees no cross-profile content. Foreign sessions → 404.

## Revision

### GET /revision/overview — authenticated
Per-tag rows `{tag_id, stable_key, display_name, status, mastery, attempt_count, last_assessed_at}` where status ∈ not_assessed/weak/fair/strong; sorted weakest/not-assessed first; plus assessed/not-assessed counts.

### POST /revision/goals — authenticated
`{"target_date": "YYYY-MM-DD", "subject"?: uuid, "hours_per_week"?: float}` → `201 goal`.

### GET /revision/goals
List own goals.

### GET /revision/plans?target_date=YYYY-MM-DD&subject=uuid&hours=N
Computed deterministic plan:

```json
{ "target_date": "2026-09-05", "days_left": 15, "hours_per_week": 6.0,
  "priorities": [{"tag_id":"…","display_name":"…","status":"not_assessed","priority":0.3975}],
  "schedule": [ {"date":"2026-08-22","focus":["TagA","TagB"]} , … ] }
```

Errors: `422` unknown subject/bad date.

---

## Not implemented

Everything else from spec §60 beyond phases 1–7: notebooks; documents tags/questions endpoints are now partially covered (tags ✅) while questions generation endpoint remains internal to enrich/refresh-ai.
