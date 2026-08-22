# Database Schema — after Phase 4

Delta from Phase 3 ([`../phase_3/backend/DATABASE_SCHEMA.md`](../../phase_3/backend/DATABASE_SCHEMA.md), which holds the full ER diagram and cumulative constraint table):

## New: `documents_digitizeddocument` — `apps/documents/models.py`

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| document_id | uuid FK → documents_document | CASCADE |
| content_hash | varchar(64) | sha256 of canonical descriptor {renderer_version, per-page revision ids + hashes + verbatim lines}; **unique(document, content_hash)** |
| revision_ids | JSONB | list of `{revision_id, page_number}` — generalizes spec §7's singular `revision_id` (D-002) |
| pdf_ref | varchar(512) | private object storage key `{profile}/{document}/{hash24}.pdf` |
| renderer_version | varchar(64) | e.g. `notespace-pdf-v1`; part of the identity hash (§13-adjacent versioning) |
| file_size | integer nullable | convenience for UI |
| created_at | timestamptz | |

RLS: enabled; policy `profile_isolation_documents_digitized` EXISTS-chains to the document's profile. Same superuser-bypass caveat as all phases.

## Modified: `documents_documentline`

Added `is_heading boolean NULL` — headings are styled in PDFs only when explicitly flagged by provider metadata or user edit (D-005). Never inferred.

## Migrations added in Phase 4

```text
documents  0003_documentline_is_heading_digitizeddocument
documents  0004_enable_rls_digitized
```

## Cumulative RLS coverage

profiles_profile · subjects_subject · canvas_canvassession · canvas_canvaspage · canvas_canvasstroke · documents_document · documents_documentpage · documents_documentpagerevision · documents_documentline · documents_digitizeddocument — direct or EXISTS-chain to the owning profile; fail-closed on unset GUC.
