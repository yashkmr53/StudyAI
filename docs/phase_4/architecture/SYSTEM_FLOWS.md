# System Flows — after Phase 4

Phase 1–3 flows remain valid: [`../phase_1/architecture/SYSTEM_FLOWS.md`](../../phase_1/architecture/SYSTEM_FLOWS.md), [`../phase_2/…`](../architecture/SYSTEM_FLOWS.md), [`../phase_3/…`](../architecture/SYSTEM_FLOWS.md). New: the NoteSpace render flow.

## NoteSpace: transcription → typed PDF (§49)

```mermaid
sequenceDiagram
    actor U as User (NotespacePage)
    participant API as Django API
    participant ST as Storage (signed)
    participant EX as Job executor

    U->>API: POST /documents/{id}/pdf
    API->>API: build layout from CURRENT revisions<br/>hash descriptor (+renderer_version)
    alt artifact exists for hash
        API-->>U: 200 {digitized_document}
    else new/changed content
        API->>DB: Job(pdf_render, QUEUED, key pdf:{doc}:{hash32})
        API-->>U: 202 {job}
        EX->>EX: claim → RLS context → render via fpdf2<br/>verbatim lines · flagged headings · page numbers
        EX->>ST: store PDF at {profile}/{doc}/{hash24}.pdf
        EX->>DB: INSERT DigitizedDocument (immutable)
    end
    U->>API: GET /digitized-documents?document={id}
    API-->>U: artifacts
    U->>API: GET /digitized-documents/{id}/download
    API->>API: ownership check → mint HMAC URL (300 s)
    API-->>U: {url, expires_in, file_size}
    U->>ST: GET signed URL → %PDF bytes
```

## Edit → regeneration lifecycle (§48 + §27)

```mermaid
flowchart TD
    A[Artifact v1<br/>revisions r1] --> B[User edits lines]
    B --> C[New immutable revision r2]
    C --> D[POST /pdf again]
    D --> E[hash differs ⇒ NEW artifact v2]
    A -.retained.-> F[(old artifact stays<br/>downloadable forever)]
```

## Faithfulness boundary (by construction)

```text
render_pdf input:  [{page_number, lines:[{text, is_heading}]}]
render_pdf output: every text verbatim, same order; heading styling only
                   when flagged; footer page numbers; document metadata
NO code path in the renderer can summarize, correct, or add content.
```

Not yet implemented flows (❌): everything downstream of OCR — chunking/embedding/retrieval/enrichment/AI Classroom features; reference books.
