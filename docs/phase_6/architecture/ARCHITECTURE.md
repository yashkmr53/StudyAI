# Architecture — after Phase 6

Delta documentation: Phases 1–5 architecture remains valid ([`../phase_5/architecture/ARCHITECTURE.md`](../architecture/ARCHITECTURE.md)).

## Module status board

| Module / Layer | Status |
|---|---|
| Security foundation | ✅ |
| Canvas + offline sync | ✅ |
| Shared ingestion | ✅ (OCR 🔧 mock) |
| NoteSpace (Module 1) | ✅ |
| AI Classroom foundation (retrieval) | ✅ (embeddings 🟡 hashing) |
| **AI Classroom intelligence** | ✅ mechanics 🔧 LLM text — new |
| Learning features (tags/mastery/questions/tests/chat/planner) | ❌ Phase 7 |
| Ops hardening | ❌ Phase 8 |

## New backend components (Phase 6)

```text
apps/ai_classroom/
├── models.py        # EnrichedNote · EnrichedNoteBlock · CitationBlock · PromptVersion
├── prompts.py       # stage JSON schemas + registry seeding + validate_stage_output
├── services.py      # run_enrichment_job (A–F) · EvidenceVerifier rules-v1
│                    # EnrichmentService.enqueue_enrichment/latest_note
├── views_serializers.py
└── migrations/      # 0001_initial · 0002_enable_rls

apps/evaluation/
├── models.py        # EvalRun
├── runner.py        # retrieval + citation metric runners
└── management/commands/run_ai_evaluation.py

providers/llm/mock.py  # MockLLMProvider — deterministic, evidence-bounded
```

## Enrichment data flow (implemented)

```text
POST /enrich → descriptor hash → active-note short-circuit OR enrich job
job → A retrieve user(≤8)+reference(≤6) chunks
    → B draft blocks [jsonschema ✓]
    → C gaps [jsonschema ✓] → D fill from reference chunks [jsonschema ✓]
    → E stitch §12 source_refs per block
    → F verify: lexical support → supported/partially/unsupported (+score)
    → supersede old note → persist note+blocks+citations atomically
GET /enrichment → nested blocks+citations with ai_stale flag
POST /refresh-ai → forced regeneration, history retained
```

## Invariants honored (new this phase)

| Invariant | How it holds |
|---|---|
| Generated content stored separately from source (§32 #6) | ai_classroom tables vs documents/retrieval tables |
| Every derived artifact references exact source revisions (§32 #7) | revision_ids + per-citation source_refs |
| Provenance independent of verification (§32 #9) | generation_method untouched by verifier verdicts |
| AI failures never destroy source (§28) | job-only failure path; tested structurally |

## Component inventory status

| Area | Status |
|---|---|
| Foundation / canvas / ingestion / NoteSpace / retrieval | ✅ |
| Intelligence pipeline (enrich+verify+eval harness) | ✅ mechanics 🔧 mock LLM |
| Learning features (Phase 7) | ❌ |
| Ops hardening | ❌ |
