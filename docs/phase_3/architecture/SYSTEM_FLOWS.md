# System Flows — after Phase 3

Phase 1/2 flows remain valid: [`../phase_1/architecture/SYSTEM_FLOWS.md`](../../phase_1/architecture/SYSTEM_FLOWS.md), [`../phase_2/architecture/SYSTEM_FLOWS.md`](../architecture/SYSTEM_FLOWS.md). This page adds the ingestion flows.

## 1. Photo upload → canonical revision (§45–46)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Client
    participant API as Django API
    participant ST as Storage (signed)
    participant DB as PostgreSQL

    U->>FE: choose photo
    FE->>API: POST /api/v1/documents {profile, source_type, filename}
    API->>DB: INSERT document + page (image_ref = key)
    API-->>FE: 201 {document, page, upload: {url, key}}
    FE->>ST: PUT bytes to signed URL
    ST->>ST: verify token · content-type · size
    ST-->>FE: 200 {key, size}
    FE->>API: POST /documents/{id}/revisions {page_id}
    API->>API: sha256(bytes) → content_hash
    API->>DB: INSERT revision(n+1) · page.current_revision · Job(QUEUED, ocr:{page}:{hash}:{pipeline})
    API-->>FE: 202 {revision, job}
```

## 2. OCR job execution (§47 worker flow)

```mermaid
flowchart TD
    A[Job QUEUED] --> B{claim: atomic UPDATE<br/>queued→running}
    B -- lost --> X[exit — another worker won]
    B -- won --> C[BEGIN + SET LOCAL app.current_profile_id]
    C --> D{idempotent? lines exist<br/>and completed}
    D -- yes --> S[succeeded no-op]
    D -- no --> E[load image bytes]
    E --> F[primary OCR attempt]
    F -- ok --> H
    F -- fail --> G[fallback OCR attempt]
    G -- ok --> H[persist: DELETE+INSERT lines<br/>snapshot + provider + status<br/>COMPLETED or NEEDS_REVIEW if avg conf < 0.80]
    G -- fail --> I[attempts < max?<br/>yes: FAILED_RETRYABLE + next_retry_at backoff<br/>no: FAILED_DEAD_LETTER]
    H --> Z[COMMIT → job SUCCEEDED]
```

## 3. Review & edit flow (§48)

```mermaid
sequenceDiagram
    participant P as Page (needs_review)
    actor U as User
    participant API as POST /documents/{id}/revisions

    P->>U: low-confidence transcription surfaced
    U->>API: {page_id, lines: [corrected text]}
    API->>API: hash canonical JSON of lines
    API->>DB: INSERT revision n+1 (completed, edited_by=user) + lines
    Note over DB: revision n−1 and its lines untouched forever
    API-->>U: 200 {revision, job: null}
```

## 4. Canvas finalize → full §67 transaction

```mermaid
sequenceDiagram
    participant ED as Editor (finalize button)
    participant CS as CanvasSyncService.finalize_page
    participant R as raster.py
    participant ST as Storage
    participant DB as PostgreSQL

    ED->>CS: POST /canvas/pages/{id}/finalize {device_id, lock_generation}
    CS->>DB: lock session row → ensure_lock (fencing)
    CS->>DB: mark canvas page finalized
    CS->>R: render strokes → PNG (stdlib)
    CS->>ST: store_bytes(profile/page.png)
    CS->>DB: get-or-create Document(canvas) · INSERT DocumentPage · INSERT Revision(hash) · get-or-create OCR Job
    CS-->>ED: 200 {document_id, revision_id, job_id}
    Note over DB: all DB writes in ONE transaction; storage write precedes commit<br/>(rollback ⇒ orphaned object only)
```

## 5. Failure → retry → dead-letter (§19–20, §28)

```mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING: claim()
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED_RETRYABLE: error, attempts < max
    FAILED_RETRYABLE --> QUEUED: next_retry_at due (backoff 5s·2^n+jitter)
    RUNNING --> FAILED_DEAD_LETTER: attempts ≥ max
    QUEUED --> CANCELLED: cancel
    RUNNING --> CANCELLING: cancel (cooperative)
```

Retry-processing endpoint resets failed jobs for the current revision to QUEUED and re-dispatches; succeeded jobs return `422`.

## Not yet implemented flows (❌)

Chunking/embedding/retrieval/enrichment downstream of OCR completion (extension point exists in `run_ocr_job`); NoteSpace PDF rendering; reference books; AI Classroom features.
