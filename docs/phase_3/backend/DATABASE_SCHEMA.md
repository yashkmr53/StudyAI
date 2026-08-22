# Database Schema — after Phase 3

PostgreSQL 18, UUID PKs throughout. Migrations per app.

## ER diagram (actual)

```mermaid
erDiagram
    accounts_user ||--o{ profiles_profile : "user_id"
    profiles_profile ||--o{ subjects_subject : "profile_id"
    profiles_profile ||--o{ canvas_canvassession : "profile_id"
    profiles_profile ||--o{ documents_document : "profile_id"
    subjects_subject ||--o{ canvas_canvassession : "subject_id (SET_NULL)"
    subjects_subject ||--o{ documents_document : "subject_id (SET_NULL)"
    canvas_canvassession ||--o| documents_document : "document (SET_NULL)"
    canvas_canvassession ||--o{ canvas_canvaspage : "session_id"
    canvas_canvaspage ||--o{ canvas_canvasstroke : "page_id"
    documents_document ||--o{ documents_documentpage : "document_id"
    documents_documentpage ||--o{ documents_documentpagerevision : "page_id"
    documents_documentpagerevision ||--o{ documents_documentline : "page_revision_id"

    documents_document {
        uuid id PK
        uuid profile_id FK
        uuid subject_id FK "nullable SET_NULL"
        varchar source "upload|canvas|reference"
        varchar source_type "image|pdf|canvas_page"
        varchar schema_version "default '1'"
        uuid reference_book_id "plain UUID, nullable (C-007)"
        timestamptz created_at
    }
    documents_documentpage {
        uuid id PK
        uuid document_id FK
        int page_number
        varchar image_ref "storage key, nullable"
        uuid current_revision_id "plain UUID (C-006)"
        boolean needs_review
        varchar ocr_status
        timestamptz created_at
    }
    documents_documentpagerevision {
        uuid id PK
        uuid page_id FK
        int revision_number
        varchar content_hash "sha256 hex"
        jsonb content_snapshot
        uuid edited_by "FK user, nullable"
        varchar ocr_status
        varchar ocr_provider "nullable"
        text error_message
        timestamptz created_at
    }
    documents_documentline {
        uuid id PK
        uuid page_revision_id FK
        int line_index
        text text
        jsonb bbox "[x,y,w,h] nullable"
        float confidence_score "nullable"
        timestamptz created_at
    }
```

`jobs_job` gained `next_retry_at timestamptz NULL` (Phase 3) — see [`../phase_2/backend/DATABASE_SCHEMA.md`](../../phase_2/backend/DATABASE_SCHEMA.md) for its full definition. CanvasSession gained `document_id uuid FK → documents_document NULL ON DELETE SET NULL`.

## §66 constraints implemented (cumulative)

| Constraint | Migration |
|---|---|
| unique(user,name) Profile | profiles 0001 |
| unique(profile,name) Subject | subjects 0001 |
| unique(session,page_number) CanvasPage | canvas 0001 |
| unique(document,page_number) DocumentPage | documents 0001 |
| unique(page,revision_number) DocumentPageRevision | documents 0001 |
| unique(revision,line_index) DocumentLine | documents 0001 |
| unique(idempotency_key) Job | jobs 0001 |
| unique(client_idempotency_key) CanvasStroke | canvas 0001 |

## RLS policies (cumulative)

Direct `profile_id::text = GUC`: profiles_profile · subjects_subject · canvas_canvassession · documents_document.
EXISTS chains: canvas pages/strokes (→session), document pages/revisions/lines (→document). GUC = `current_setting('app.current_profile_id', true)`; unset ⇒ fail-closed. Superuser-bypass caveat unchanged.

## Migrations added in Phase 3

```text
documents  0001_initial · 0002_enable_rls
canvas     0003_canvassession_document
jobs       0002_job_next_retry_at
```

## Enums / vectors

OCR status enums are Django TextChoices on both page and revision (`pending/processing/completed/needs_review/failed`). Still no DB-level enums, check constraints, triggers, or vector/FTS columns.
