# System Flows — after Phase 7

Prior flows remain valid: [`../phase_6/architecture/SYSTEM_FLOWS.md`](../architecture/SYSTEM_FLOWS.md) and earlier phases. New: the learning loop.

## 1. Enrichment tail → tags + questions (§53/§54)

```mermaid
flowchart TD
    A[Enrich job persists note] --> B[TaggingService.extract_for_document]
    B --> C{document.subject?}
    C -- none --> D[skip tagging]
    C -- subject --> E[top tokens → find-or-create Tag<br/>ADDED + LINKED changelog entries]
    E --> F[QuestionGenerationService<br/>MCQ per active chunk, deterministic shuffle]
    F --> DB[(questions_question rows<br/>unique revision+hash+key)]
```

## 2. Adaptive test assembly (§55) — deterministic

```text
eligible = non-stale questions in profile (+ optional subject)
priority(q) = 0.6·(1−mastery_or_0.5)
            + 0.25·recency_bonus      (1.0 never attempted; decays over 7 days)
            + 0.15·difficulty_match   (medium = 1.0)
sort desc by (priority, pk) → take N
```

Same mastery/attempt state ⇒ identical selection (asserted by test).

## 3. Attempt grading + mastery update (§56) — single transaction

```mermaid
sequenceDiagram
    actor U as User
    participant API as POST /tests/{id}/attempts
    participant MS as MasteryScoringService
    participant DB as PostgreSQL

    U->>API: {question_id, selected_index, confidence}
    API->>DB: BEGIN · INSERT attempt · grade correct?
    API->>MS: record_attempt(profile, question, correct, confidence)
    Note over MS: correct: m += (1−m)·0.4·(0.5+conf/2)<br/>wrong: m −= m·0.4·(0.5+(1−conf)/2)
    MS->>DB: upsert mastery_score (EMA, counters, last_assessed)
    API-->>U: 201 {attempt(correct, answer), mastery(tag, value, status)}
```

Replay of the same question ⇒ `409 IDEMPOTENCY_CONFLICT` (G-007).

## 4. Chat with verified citations (§16/§57)

```mermaid
sequenceDiagram
    actor U as User
    participant CS as ChatService.ask
    participant RS as RetrievalService.search (scoped)
    participant LLM as MockLLM chat:v1
    participant V as EvidenceVerifier rules-v1
    participant DB as PostgreSQL

    U->>CS: POST messages {content}
    CS->>DB: persist user message
    CS->>RS: search(profile scope, session.subject?, top_k=4)
    RS-->>CS: evidence[]
    CS->>LLM: chat:v1 + evidence JSON
    LLM-->>CS: extractive answer + cited chunk ids
    CS->>V: classify(answer vs cited contents)
    V-->>CS: supported/partially/unsupported + score
    CS->>DB: persist assistant message (citations+verdicts+model+prompt version)
    CS-->>U: 201 message
```

Cross-profile isolation: retrieval scoping makes foreign chunks unreachable; session access is owner-filtered (foreign → 404).

## 5. Revision planning (§58) — no LLM

```text
GET /revision/plans?target_date=…&hours=…
  candidates = subject∩profile-linked tags
  priority = weakness·0.45 + urgency·0.25 + recent-failures·0.20 + insufficient·0.10
  schedule: round-robin top tags across ≤14 days, 2 sessions/day
```

## Not yet implemented flows (❌)

Verifier/embedding calibration datasets; coalescing window and quota budgets; reranking stage.
