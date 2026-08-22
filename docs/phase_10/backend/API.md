# Backend API — Phase 10

**Status:** Extended with Notebooks, Document Questions, Tag Rename, Budget Throttle

---

## New Endpoints

### Notebooks (B1)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/notebooks` | Create notebook |
| GET | `/api/v1/notebooks` | List user's notebooks |
| GET | `/api/v1/notebooks/{id}` | Retrieve notebook |
| PATCH | `/api/v1/notebooks/{id}` | Update notebook |
| DELETE | `/api/v1/notebooks/{id}` | Delete notebook |
| POST | `/api/v1/notebooks/{id}/pages` | Add page |
| GET | `/api/v1/notebooks/{id}/pages` | List pages |
| PATCH | `/api/v1/notebooks/{id}/pages/{page_id}` | Update page canvas_state |
| DELETE | `/api/v1/notebooks/{id}/pages/{page_id}` | Delete page |
| POST | `/api/v1/notebooks/{id}/pages/{page_id}/lines` | Append strokes |
| GET | `/api/v1/notebooks/{id}/pages/{page_id}/lines` | List strokes |

**Auth:** Bearer token (JWT)  
**Scope:** Owner-only via profile → user  
**Throttle:** `ai` scope (120/min) + budget enforcement

#### Notebook Create
```json
POST /api/v1/notebooks
{
  "profile": "uuid",
  "subject": "uuid",  // optional
  "title": "string",
  "description": "string"  // optional
}
```

#### Page Create
```json
POST /api/v1/notebooks/{notebook_id}/pages
{
  "notebook": "uuid",
  "page_number": 1,
  "canvas_state": {}  // optional
}
```

#### Strokes Append
```json
POST /api/v1/notebooks/{notebook_id}/pages/{page_id}/lines
[
  {
    "line_index": 0,
    "points": [10, 10, 20, 20, 30, 30],
    "color": "#FF0000",
    "width": 3.0,
    "tool": "pen"
  }
]
```

---

### Document Questions (B2)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/documents/{document_id}/questions` | List questions for document |

**Response:**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "document": "uuid",
      "source_revision_id": "uuid",
      "source_chunk_id": "uuid",
      "difficulty": "medium",
      "prompt": "What is...?",
      "options": ["A", "B", "C", "D"],
      "answer_index": 1,
      "answer_text": "B",
      "content_hash": "sha256...",
      "question_key": "md5...",
      "generation_model": "mock-gpt",
      "prompt_version": "question_generation:v1",
      "stale": false,
      "created_at": "2026-08-23T..."
    }
  ]
}
```

---

### Tag Rename (B4)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/tags/{id}/rename/` | Rename tag display name |

**Request:**
```json
{
  "name": "New Display Name"
}
```

**Response:**
```json
{
  "id": "uuid",
  "subject": "uuid",
  "stable_key": "calculus",
  "display_name": "New Display Name",
  "created_at": "2026-08-23T..."
}
```

**Validation:**
- `name` required, non-empty
- `name` ≤ 120 characters
- `stable_key` unchanged

---

## Modified Endpoints

### Document Enrichment
```
POST /api/v1/documents/{id}/enrich
POST /api/v1/documents/{id}/refresh-ai
```
**Throttle:** `AIBudgetThrottle` (was `LiveScopedRateThrottle`)
- Enforces monthly token/cost budget
- Returns 429 with budget details if exceeded

### Chat Messages
```
POST /api/v1/chat/sessions/{id}/messages
```
**Throttle:** `AIBudgetThrottle` (added)
- Enforces monthly budget on assistant messages

---

## Error Responses

### Budget Exceeded (429)
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests.",
    "request_id": "req_...",
    "details": {
      "budget_type": "token",  // or "cost"
      "limit": "100000",
      "current": "100050",
      "reset_date": "2026-09-01T00:00:00Z"
    }
  }
}
```

### Provider Error (502)
```json
{
  "error": {
    "code": "PROVIDER_ERROR",
    "message": "Upstream provider failed.",
    "request_id": "req_...",
    "details": {
      "attempted": ["mock", "mock"],
      "last_error": "Connection timeout"
    }
  }
}
```

### Validation Error (422)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed.",
    "request_id": "req_...",
    "details": {
      "name": ["Tag name cannot exceed 120 characters."]
    }
  }
}
```

---

## Throttle Scopes

| Scope | Rate | Applied To |
|-------|------|------------|
| `auth` | 30/min | Auth endpoints |
| `ai` | 120/min | Enrichment, chat, notebooks |
| `user` | 600/min | General API |

**Budget Throttle:** Applied on top of `ai` scope for enrichment/chat endpoints.

---

## RLS Enforcement

All new endpoints enforce Row-Level Security via:
- Profile ownership: `profile__user=request.user`
- Subject access: `ProfileAuthorizationService.ensure_subject_access()`
- Nested resources: scoped to parent notebook/document

---

## OpenAPI Documentation

- Available at `/api/docs/` (Swagger UI)
- Schema at `/api/schema/`
- Committed snapshot: `docs/openapi/schema.yml`

---

## Related Documentation

- `docs/phase_10/modules/NOTE_SPACE.md` — Notebooks API details
- `docs/phase_10/modules/AI_CLASSROOM.md` — Tag rename, enrichment
- `docs/phase_10/architecture/SYSTEM_FLOWS.md` — API flow diagrams