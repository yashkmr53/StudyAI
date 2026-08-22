# System Flows — after Phase 5

Prior flows remain valid: [`../phase_1/…`](../../phase_1/architecture/SYSTEM_FLOWS.md), [`../phase_2/…`](../../phase_2/architecture/SYSTEM_FLOWS.md), [`../phase_3/…`](../architecture/SYSTEM_FLOWS.md), [`../phase_4/…`](../architecture/SYSTEM_FLOWS.md). New: indexing and retrieval flows.

## 1. Indexing — OCR completion → chunks + embeddings (§10, §47)

```mermaid
sequenceDiagram
    participant OJ as OCR job (succeeding)
    participant IS as index_document
    participant DB as PostgreSQL
    participant EP as HashingEmbeddingProvider

    OJ->>IS: enqueue_index_job(document)
    Note over DB: key = index:{doc}:{combined-revision-hash}:{chunker}:{model}
    IS->>DB: build_chunks from CURRENT revisions<br/>(word-bounded, overlap carried across pages)
    IS->>DB: diff content hashes vs active chunks
    DB-->>IS: keep set (unchanged) / stale-out list (superseded)
    IS->>DB: UPDATE stale=true on superseded (retained, §27)
    IS->>DB: INSERT new chunks
    IS->>EP: embed(new contents) — local, deterministic
    IS->>DB: save embedding + model + version
    IS->>DB: populate tsvector_content (+GIN)
```

## 2. Hybrid retrieval with RRF (§14)

```mermaid
flowchart TD
    Q[User query] --> F[scope filters:<br/>profile ownership OR platform-reference · subject? · stale=false]
    F --> D[Dense: pgvector cosine via HNSW<br/>top-50 by distance]
    F --> K[Keyword: SearchRank on tsvector GIN<br/>top-50 by rank]
    D --> R[Reciprocal Rank Fusion k=60]
    K --> R
    R --> T[top-k evidence w/ dense+keyword+rrf scores]
    T --> G{reference chunk?<br/>book READY?}
    G -- not ready --> X[dropped defensively]
    G -- ok --> Y[evidence to caller]
```

## 3. Edit → invalidation lifecycle (§10)

```mermaid
sequenceDiagram
    actor U as User
    participant API as POST /documents/{id}/revisions (edit mode)
    participant DB as PostgreSQL

    U->>API: corrected lines for page P
    API->>DB: INSERT revision n+1 (immutable)
    API->>API: enqueue_index_job(document)
    Note over DB: hash-diff: old page-P chunks stale=true;<br/>new content chunk inserted + embedded;<br/>untouched pages keep their embeddings
```

## 4. Reference-book ingestion (§15)

```mermaid
sequenceDiagram
    participant A as Admin (command)
    participant DB as PostgreSQL
    participant EX as Executor (eager/broker)

    A->>A: read book.json
    A->>DB: INSERT Document(source=reference, profile=NULL) + pages/revisions/lines per chapter
    A->>DB: INSERT ReferenceBook(processing) + chapters
    A->>EX: enqueue_index_job(book.document)
    EX->>DB: chunk + embed + tsvector
    alt eager mode
        EX-->>A: job succeeded → book READY
    else broker mode
        Note over A: book stays PROCESSING until a worker finishes; READY gating keeps it out of retrieval meanwhile
    end
```

Not yet implemented flows (❌): enrichment/citations/questions/chat consumption of evidence; evaluation harness.
