# System Flows — after Phase 6

Prior flows remain valid: [`../phase_5/architecture/SYSTEM_FLOWS.md`](../architecture/SYSTEM_FLOWS.md) and earlier phases. New: the enrichment pipeline.

## Enrichment A–F (§11, §51) — implemented flow

```mermaid
sequenceDiagram
    actor U as User
    participant API as POST /documents/{id}/enrich
    participant EX as Executor (eager/broker)
    participant RS as Retrieval (Phase 5)
    participant LLM as MockLLMProvider
    participant V as EvidenceVerifier rules-v1
    participant DB as PostgreSQL

    U->>API: enrich
    API->>API: descriptor hash = f(doc, revisions, prompts, model)
    alt active note exists for hash
        API-->>U: 200 {enriched_note}
    else
        API->>DB: Job(enrich, QUEUED, key enrichment:{doc}:{hash32})
        API-->>U: 202 {job}
        EX->>RS: user chunks (≤8) + READY reference chunks (≤6)
        EX->>LLM: generate_structured(enrichment_draft:v1 + EVIDENCE_JSON)
        LLM-->>EX: blocks[] — jsonschema validated
        EX->>LLM: generate_structured(gap_detection:v1)
        LLM-->>EX: gaps[] — topics in references missing from notes
        EX->>LLM: generate_structured(gap_filling:v1 + gaps)
        LLM-->>EX: gap_fill blocks citing reference chunk ids
        EX->>V: per block: lexical support vs cited chunks
        V-->>EX: supported / partially_supported / unsupported (+score)
        EX->>DB: supersede old note · INSERT note+blocks+citations
    end
```

## Provenance ⊥ verification (§12)

```text
block.generation_method = llm            ← how it was produced (never rewritten)
citation.verification_status = supported | partially_supported | unsupported
                              ← whether cited chunks actually support it
Example observed in E2E:
  overview block  → method llm, status unsupported (meta-text, score 0.0)
  key_concept     → method llm, status supported   (score 1.0, verbatim source)
  gap_fill        → method llm, status supported   (score 0.83, reference book)
```

## ai-stale propagation (§21/§27)

```mermaid
flowchart TD
    A[user edit revision] --> B[index job: stale-out old chunks, embed new]
    B --> C[EnrichedNote.ai_stale = true for this document]
    C --> D[GET /enrichment shows stale flag]
    D --> E[POST /refresh-ai → supersede old note → new generation]
```

## Failure isolation (§28/§52)

Enrichment failure ⇒ job FAILED_RETRYABLE/DEAD_LETTER only. Canonical documents, revisions, PDFs and NoteSpace remain fully available; `refresh-ai` or a retry re-attempts.

## Not yet implemented flows (❌)

Question generation → adaptive tests → mastery updates; chatbot consumption of evidence; tags hierarchy; revision planner; coalescing/quota budgets.
