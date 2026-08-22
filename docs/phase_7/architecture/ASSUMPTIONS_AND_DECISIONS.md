# Assumptions and Decisions — Phase 7

Prior decisions remain in force (A- through F-series in [`../phase_6/architecture/ASSUMPTIONS_AND_DECISIONS.md`](../architecture/ASSUMPTIONS_AND_DECISIONS.md)). Phase 7 decisions (G-series):

| ID | Decision |
|---|---|
| G-001 | Tags live in `ai_classroom` (not subjects) — they are AI-managed academic metadata; hierarchy anchor via `parent` FK ready for Subject→Unit→Topic→Subtopic depth. |
| G-002 | Tag extraction is lexical (frequent significant tokens → find-or-create stable tags) until the LLM swap produces semantic tags. |
| G-003 | Documents without a subject skip tagging — §18 anchors tags to a subject and NULL-subject tags would break the uniqueness model. |
| G-004 | Questions link to at most one concept tag (QuestionTagLink OneToOne) = first DocumentTag of the source document; mastery keys off this tag. |
| G-005 | Mastery EMA: correct ⇒ m += (1−m)·0.4·(0.5+conf/2); wrong ⇒ m −= m·0.4·(0.5+(1−conf)/2); confidence defaults to 0.75 when unreported. |
| G-006 | Adaptive selection score = 0.6·(1−mastery) + 0.25·recency-bonus + 0.15·difficulty-match, stable pk tie-break; unattempted questions get full recency bonus; not_assessed tags use neutral 0.5 mastery inside scoring only. |
| G-007 | One attempt per (test, question); replay returns 409 IDEMPOTENCY_CONFLICT rather than allowing answer shopping. |
| G-008 | Test detail hides `answer_index` until the question is attempted within that test instance. |
| G-009 | Chat answers are extractive from top-ranked evidence with all citations verified by rules-v1 before persistence; no uncited general-knowledge mode exists yet. |
| G-010 | Planner computes on read (no persisted plan rows); horizon capped at 14 days, 2 sessions/day; insufficiently-assessed tags get mid priority per §58 ordering. |
| G-011 | Question staleness triggers when the source chunk is superseded during indexing; page-level approximation documented. |

---

## Details

### G-001/G-003 — Tag anchoring
- **Why:** §18 defines Tag(subject_id, …) and unique(subject, stable_key). A document without a subject has no anchor for stable identity.
- **Consequences:** subject-less documents are indexed/searchable but produce no tags until assigned to a subject.

### G-005 — Mastery formula
- **Why:** bounded EMA keeps scores in [0,1], responds faster to confident-correct answers and penalizes confident-wrong more heavily; deterministic and testable.
- **Alternatives:** Elo-style pairing, Bayesian Knowledge Tracing (better calibration, more state).
- **Next step:** tune constants once real attempt data accumulates (§26 evaluation).

### G-007 — Attempt replay protection
- **Why:** prevents answer-shopping within a test instance while keeping refresh-safe clients simple.
- **Semantics:** second POST for the same question returns `409 IDEMPOTENCY_CONFLICT` envelope.

### G-010 — Compute-on-read planner
- **Why:** plans depend on volatile mastery/attempts; persisting them would immediately go stale. Goals ARE persisted (user intent), plans are derived views.
