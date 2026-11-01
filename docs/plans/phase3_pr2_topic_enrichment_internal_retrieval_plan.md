# StudyAI: PR 2 End-to-End Implementation Plan — Topic-Based Enrichment (Internal Retrieval Only)

**Phase:** PR 2 of 3  
**Branch:** `feature/topic-based-enrichment-corrective-rag`  
**Base:** PR 1 commit (`dfb6c1b`)  
**Status:** Planned / Awaiting Implementation  

---

## 0. Pre-Implementation Audit & Baseline Inspection

Before modifying or adding code in PR 2, the agent must inspect the live system baseline and report findings:

1. **`run_enrichment_job` Execution Flow Today:**
   - Location: `backend/apps/ai_classroom/services.py:300`
   - Flow: Gated by `ready_for_enrichment` and PR 1 `start_hash`. Loads `Document` and `Job`, constructs `EnrichmentState`, calls `ai.langgraph.graphs.enrichment_graph.invoke_enrichment_graph`, and persists `EnrichedNote`, `EnrichedNoteBlock`, and `CitationBlock`.
   - Baseline Invariant: Retain Celery task idempotency, atomic persistence, and locked descriptor recomputation (`start_hash != current_descriptor -> ai_stale = True`).
2. **`retrieve_reference_context` Contract & Score Calibration:**
   - Location: `backend/apps/references/services.py:31`
   - Current Signature: `retrieve_reference_context(query, *, profile=None, subject=None, subject_id=None, top_k=5, min_score=0.0, reference_document_ids=None) -> list[dict]`
   - Current Return Keys: `chunk_id`, `document_id`, `source_title`, `source_type` ("book"), `page`, `page_start`, `page_end`, `chapter`, `section`, `text`, `content`, `snippet`, `score`, `subject_name`.
   - **Audit Finding & Score Fix:** The current `score` is a Reciprocal Rank Fusion (RRF) fused score ($1 / (k + \text{rank})$), whose maximum value is small (~0.033) and represents relative rank rather than absolute semantic relevance. Applying a filter like `score >= 0.35` would discard all results.
   - **Vector Distance Operator Confirmed:** PostgreSQL uses `pgvector.django.CosineDistance("embedding", qvec)`, which compiles to the PostgreSQL `<=>` operator ($\text{distance} = 1.0 - \text{cosine similarity}$). Therefore, $\text{cosine similarity} = 1.0 - \text{distance}$.
   - **PR 2 Enhancement:** Additively extend `retrieve_reference_context` to calculate and return `dense_score` (raw cosine similarity: $1.0 - \text{distance}$ in PostgreSQL; cosine dot product in SQLite) and `keyword_score`. If a candidate chunk is returned by keyword search only, compute its cosine similarity against `qvec` so every candidate chunk carries a valid `dense_score`. Candidate ranking retains RRF, but `RELEVANCE_MIN_DENSE` applies strictly to `dense_score`.
3. **Existing `EnrichedNote` and Block Schema:**
   - Location: `backend/apps/ai_classroom/models.py`
   - `EnrichedNote`: Restrict `status` strictly to `("ok", "needs_attention")`. Add `evidence_status_by_topic` (JSON map of `topic_id -> status`), `excluded_segments` (JSON list), `diagnostics` (JSON map), `force_include_hash` (CharField max 32), and `settings_version` (CharField max 32). Model already has `generation_job = ForeignKey(Job)` which links each note to its producing job.
   - `EnrichedNoteBlock`: Add `block_kind` (`"heading"`, `"student"`, `"addition"`, `"legacy"`), `render_as` (`"prose"`, `"code"`), `topic_id`, `source_line_ids` (mapped to transcript `lineage_id`), `support_status`, and `addition_kind` (`"explanation"`, `"possible_issue"`). Existing rows default to `block_kind="legacy"`, `render_as="prose"`.
   - `CitationBlock`: Stores `source_refs` (JSON list).
   - Requires additive migration `0005_topic_enrichment_blocks.py`.
4. **`Job` and `JobExecutionState` Schema Extensions:**
   - Location: `backend/apps/jobs/models.py`
   - `Job` has statuses: `QUEUED`, `RUNNING`, `FAILED_RETRYABLE`, `FAILED_DEAD_LETTER`, `CANCELLING`, `CANCELLED`, `SUCCEEDED`.
   - `Job.idempotency_key` has `unique=True` at the database level. Therefore, user-initiated runs include a run nonce so finished jobs do not cause DB-level key collisions.
   - Additive fields for `Job`:
     - `metadata = models.JSONField(default=dict, blank=True)` (stores `outcome`, `error_code`, `message`, `force_include_hash`, `force_include_line_ids`).
     - `heartbeat_at = models.DateTimeField(null=True, blank=True)` (updated at start of each node and on checkpoint write to allow watchdog reaping by heartbeat silence).
   - Additive fields for `JobExecutionState`:
     - `topic_id = models.CharField(max_length=64, blank=True, default="")`.
     - `calls_used = models.PositiveIntegerField(default=0)` (records LLM calls made in that stage/topic).
     - `models.UniqueConstraint(fields=("job", "completed_node", "topic_id"), name="uniq_job_completed_node_topic")` to eliminate race conditions between concurrent topic worker branches.
   - Requires additive migration `0005_job_heartbeat_metadata_and_executionstate_topic.py` in `apps/jobs`.
5. **`Document` Force-Include Persistence:**
   - Location: `backend/apps/documents/models.py`
   - Requires additive migration `0012_document_force_include_line_ids.py` to add `force_include_line_ids = models.JSONField(default=list, blank=True)` so force-included line selections survive regenerations.
6. **`DocumentLine` Kind & Syntax Inspection:**
   - Location: `backend/apps/documents/models.py:178`
   - Fields: `id`, `page_revision`, `line_index`, `lineage_id`, `original_text`, `text`, `bbox`, `confidence_score`, `is_heading`, `is_edited`, `is_user_added`, `parent_line_id`.
   - Audit Finding: `DocumentLine` stores `is_heading`, but does not store an OCR line kind (code vs prose). Line text has no embedded newlines (`\n`). Code vs. prose is classified at assembly time into `render_as` ("code" vs "prose") so that a single source of truth governs backend rendering and frontend display.
7. **Deployed LLM Models, Thinking Mode & Latency Baseline:**
   - Deployed Model: In `backend/config/settings/base.py:215` and `docker-compose.yml:111`, `LLM_MODEL` defaults to `qwen3.5:4b`. Default model configurations in PR 2 are set to `qwen3.5:4b` to match the deployed environment.
   - **Thinking Mode Disabled:** `qwen3.5` models can output `<think>...</think>` reasoning tokens by default. For all structured generation and extraction calls in PR 2, thinking mode is explicitly disabled (`options={"think": False}`) to preserve JSON validity and minimize latency.
   - Concurrency: Introduce `ENRICHMENT_CONCURRENCY = int(getattr(settings, "ENRICHMENT_CONCURRENCY", 2))` to bound LangGraph worker branches. Note that `OLLAMA_NUM_PARALLEL` defaults to 1 unless overridden; the audit will measure actual hardware concurrency.
   - Timeouts: With ~2-3s call latency, `ENRICHMENT_PROCESSING_TIMEOUT` (heartbeat silence) is tuned to **300 seconds** (5 minutes). `ENRICHMENT_NODE_TIMEOUT` (default 60s) is enforced as HTTP timeouts on underlying Ollama client sessions. Catch `SoftTimeLimitExceeded` on worker tasks to save state cleanly before task termination.
   - Latency Baseline: Real per-call latency on local Apple Silicon hardware is ~1.8s–3.2s per generation call and ~35ms–45ms for embeddings. On CPU-only deployment environments, latency may be higher; the baseline report will document the deployment hardware.

### Dependency on PR 1
PR 2 depends strictly on PR 1 invariants:
- `line_id` in all state representations, planner assignments, and block schemas refers to the PR 1 `lineage_id` UUID string from `DocumentLine`.
- Only approved and non-ignored pages (`is_approved=True, is_ignored=False`) are processed.
- `ready_for_enrichment` strictly gates the enrichment entrypoint; unapproved or ignored documents reject early with HTTP 422 `NOT_READY_FOR_ENRICHMENT`.
- Revert-clears-stale: Updating `sync_page_approval_and_indexing` in `apps/documents/services.py` with `.filter(content_hash=new_hash).update(ai_stale=False)` ensures editing and reverting back to the original approved text clears `ai_stale`.
- **Lock Ordering Rule:** All operations must acquire locks in the strict order: **Page first, then Document**. PR 1's edit path locks `Page` then `Document`; persistence and staleness helpers strictly follow this order to eliminate deadlock risks.

### Out of Scope for PR 2
- Web search, Bing/Tavily integrations, and multi-pass corrective RAG are **strictly out of scope** (deferred to PR 3).
- PR 2 uses internal reference books only.
- Research is kept strictly decoupled from writing. Every retrieved evidence item carries `source_type="book"` so PR 3 can seamlessly introduce `source_type="web"`.

---

## 1. Objective & Scope

PR 2 delivers the core topic-based note enrichment pipeline:
1. **Verbatim Student Note Preservation with Single-Source `render_as`:** Code builds student blocks directly from transcript lines, assigning `render_as: Literal["code", "prose"]` at assembly time so the frontend never duplicates code detection heuristics. The LLM never writes, summarizes, or rewrites student notes.
2. **Additions Only:** The LLM writer proposes additions only (`explanation` or `possible_issue`), placed `after_line_id` and grounded in reference evidence.
3. **Structured Topic Segmentation:** Classifies lines into contiguous `study_notes` vs `other` in 60-line windows, and plans coherent topics (capped at 6) with deterministic line normalization.
4. **Decoupled Internal Research:** Queries reference library per topic (`top_k=6`), drops chunks below calibrated `RELEVANCE_MIN_DENSE`, and formats evidence manifests with stable citation identifiers (`C1`, `C2`...).
5. **Parallel LangGraph Fan-Out:** Dispatches parallel research and writing via `Send`, merging into a dictionary reducer keyed by `topic_id`.
6. **Guarded Pipeline Order:** Sanitizes citations and deduplicates additions *before* verification. Stitching is pure Markdown rendering that runs *last*.
7. **Bounded Writer-Only Repair with Pass Numbering:** Verification loops back strictly to the topic writer (never retrieval), appending `#pass` to stage names to ensure repair changes output without being blocked by stored checkpoint rows.
8. **Durable Persistence, Outcome Mapping & Backward Compatibility:** Stores granular blocks in an additive schema, maps terminal outcomes to documented `Job` statuses with user-facing messages (never exposing raw exceptions), and keeps previous good notes active.

---

## 2. Pipeline Architecture & Flow Diagram

The pipeline strictly follows this sequential stage order:  
`gate` → `classify` → `plan` → `per-topic research` → `write` → `sanitize` → `dedupe` → `verify` → `render` → `persist`.

```mermaid
flowchart TD
    ApprovedLines([Approved Transcript Lines<br/>is_approved=True, is_ignored=False]) --> GateNode[2.1 Load & Gate Node<br/>validate_note_academic_content]
    
    GateNode -- Insufficient Content --> EarlyExit([Job SUCCEEDED: outcome=insufficient_content<br/>Friendly UI message; Existing EnrichedNote remains active])
    GateNode -- Valid --> ClassifyNode[2.2 Segment Classifier Node<br/>60-line windows, confidence >= SEGMENT_MIN_CONFIDENCE<br/>checkpointed stage]
    
    ClassifyNode --> SegNormalizer[2.3 Range Gap & Overlap Normalizer<br/>Gaps -> other conf=0; Boundary shift >3 -> excluded_segments]
    SegNormalizer --> CheckStudy{Has study_notes?}
    CheckStudy -- No --> NonStudyExit([Job SUCCEEDED: outcome=no_study_content<br/>Friendly UI message; Existing EnrichedNote remains active])
    CheckStudy -- Yes --> TopicPlanner[2.4 Topic Planner Node<br/>MAX_TOPICS <= 6, Code topic_ids t1..tn<br/>checkpointed stage]
    
    TopicPlanner --> PlanNorm[2.5 Deterministic Line Normalizer<br/>lineage_id mapping, orphan line attachment]
    
    PlanNorm --> SendFanOut[2.6 LangGraph Send Fan-Out per Topic]
    
    subgraph TopicWorkers ["Parallel Per-Topic Branches (Send)"]
        ResearchNode["Topic Research Node (checkpointed)<br/>retrieve_reference_context top_k=6<br/>Filter dense_score < RELEVANCE_MIN_DENSE<br/>Store research_by_topic[topic_id]"]
        ResearchNode --> EvidenceCheck{evidence_status?}
        EvidenceCheck -- none --> SkipWriter["Skip Writer Node<br/>Emit verbatim student blocks only<br/>flag: no_reference_found"]
        EvidenceCheck -- sufficient / partial --> TopicWriterNode["Topic Writer Node (checkpointed: write#0)<br/>Generates AdditionDraft items only<br/>Max additions cap; drop restatements"]
    end
    
    SendFanOut --> TopicWorkers
    SkipWriter --> ReducerMerge[2.7 Dictionary Reducer keyed by topic_id]
    TopicWriterNode --> ReducerMerge
    
    ReducerMerge --> SanitizeNode[2.8 Citation Sanitizer Node (checkpointed: sanitize_dedupe#0)<br/>Validate additions individually<br/>Strip ungrounded IDs, drop uncited additions]
    SanitizeNode --> DedupeNode[2.9 Guarded Deduplication Node (checkpointed)<br/>Cross-topic similarity > DUP_COSINE<br/>Options: keep_first, keep_second, merge, keep_both<br/>Student blocks immune; keep all citations]
    
    DedupeNode --> VerifierNode[2.10 Deterministic & Semantic Verifier (checkpointed: verify#0)<br/>Exact line_id coverage + Dual Support Scoring<br/>possible_issue contradiction check]
    
    VerifierNode --> CoverageCheck{Line Coverage 100%?}
    CoverageCheck -- No (Code Bug) --> TerminalFailure([Job FAILED_DEAD_LETTER: outcome=coverage_bug<br/>Existing EnrichedNote remains active])
    CoverageCheck -- Yes --> RepairTargetsCheck{repair_targets non-empty?}
    
    RepairTargetsCheck -- No (Passed) --> RenderNode[2.11 Pure Render Node<br/>Group code student lines into fenced blocks<br/>Order-preserving Markdown generation]
    RepairTargetsCheck -- Yes --> RepairBudgetCheck{Repair Passes < 1 AND TopicBudget > 0?}
    
    RepairBudgetCheck -- Yes (Pass 0) --> TargetedRepairRouter["Targeted Repair Router<br/>Directly call TopicWriterNode with stage write#1<br/>Top-2 chunks, temp=0.0, fallback prompt"]
    TargetedRepairRouter --> TopicWriterNode
    RepairBudgetCheck -- No --> FlagAttention[Flag status = needs_attention]
    FlagAttention --> RenderNode
    
    RenderNode --> AtomicPersist["2.12 Atomic Persistence Node<br/>Lock Job & Document select_for_update()<br/>Verify Job RUNNING and no newer job persisted<br/>Supersede old note; Save ok / needs_attention note<br/>Check descriptor inside transaction: set ai_stale<br/>Post-commit on_commit recheck"]
    AtomicPersist --> Finish([Complete: status = ok / needs_attention])
```

---

## 3. Detailed Component Designs

### 3.1 Classifier and Content Gate (`load_and_gate_node.py` & `segment_classifier_node.py`)

1. **Pre-filter Symbol Calibration in `content_gate.py`:**
   - Ordinary prose contains `-`, `/`, `(`, and `)`. Remove them from mathematical pre-filtering.
   - Retain strong technical markers: `=`, `->`, `def`, `O(`, `$`, `\frac`, `{`, `}`.
   - Notes with >= 5 words containing these strong markers bypass generic short-content rejection.
2. **Windowed Segment Classification:**
   - Lines are processed in windows of **60 lines** with local labels `L1..Ln`.
   - The model classifies contiguous ranges into `study_notes`, `general_info`, `personal`, `task_list`, or `other`, predicting a `subject` guess.
   - Thinking mode explicitly disabled (`options={"think": False}`).
   - **Subject Mapping:** The free-text `subject` guess is matched in code against the user's existing `Subject` objects (case-insensitive name or slug match). If no match is found, falls back to `None` (which defaults to `document.subject`).
   - **Boundary Merging:** Adjacent segments across window boundaries sharing the same `segment_type` are automatically merged into a single segment.
3. **Deterministic Range Gap & Normalization Rules:**
   - **Gaps:** Any gap between predicted segments is assigned to `other` with `confidence = 0.0`. Gaps **never** default to `study_notes`.
   - **Overlaps:** If segments overlap, truncate the earlier segment to `start_line - 1` of the next segment.
   - **Confidence & Repair Filtering:** Segments with `confidence < SEGMENT_MIN_CONFIDENCE` (default 0.60) or segments **heavily modified by repairs** (defined as any segment whose start or end boundary shifted by > 3 lines during normalization) are excluded from topic planning.
   - **Excluded Segments Tracking:** Excluded segments are saved in state as `excluded_segments`, exposed via the API, rendered to the student, and includable via `force_include_line_ids`.

```python
class TranscriptSegment(BaseModel):
    segment_type: Literal["study_notes", "general_info", "personal", "task_list", "other"]
    start_line_number: int  # 1-based local index
    end_line_number: int    # 1-based local index inclusive
    topic_description: str
    subject: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""

class TranscriptSegmentationResult(BaseModel):
    segments: list[TranscriptSegment]
```

---

### 3.2 Topic Planner Node (`topic_planner_node.py`)

1. **Identity & Constraints:**
   - `line_id` throughout planner state refers strictly to the line's persistent `lineage_id` UUID.
   - Maximum topics: `MAX_TOPICS = getattr(settings, "ENRICHMENT_MAX_TOPICS", 6)`.
   - **Code-Assigned Topic IDs:** Assign `topic_id` deterministically in code (`"t1"`, `"t2"`, ..., `"tN"`). Never trust model-generated IDs.
2. **Schema & Subject Propagation:**
   ```python
   class PlannedTopic(BaseModel):
       topic_id: str
       title: str
       description: str
       subject: Optional[str] = None
       transcript_line_labels: list[str]  # e.g. ["L1", "L2", "L3"]

   class TopicPlanOutput(BaseModel):
       topics: list[PlannedTopic]
       diagnostics: dict = {}
   ```
3. **Deterministic Assignment Normalization:**
   - Map local labels `L1..Ln` to `lineage_id` UUIDs in code.
   - **Deduplication:** If a line is assigned to multiple topics, retain it in the first topic only.
   - **Orphan Attachment:** If an eligible study line is omitted, attach it to the topic of the nearest preceding assigned line (or Topic 1 if at the start).
4. **Fallback & Diagnostics:**
   - If the planner model fails Pydantic schema validation after 2 bounded retries, activate **planner fallback**: create a single topic containing all study lines, inherit the document subject, and flag `planner_fallback=True`.
   - Record `planner_repairs_count` in diagnostics.

---

### 3.3 Verbatim Blocks & Additions-Only Writer (`topic_writer_node.py`)

> [!IMPORTANT]
> The LLM writer **never** writes, summarizes, or edits student blocks. Student blocks are constructed deterministically in code directly from the transcript lines.

1. **Student Block Assembly & `render_as` Assignment (in code):**
   - Consecutive transcript lines within a topic are grouped into contiguous `SectionBlock(type="student")` instances, splitting strictly at addition insertion anchors (`after_line_id`) and at code/prose boundary changes.
   - **Single Source of Truth for Code Fencing:** The backend inspects each line's text and assigns `render_as: Literal["code", "prose"]` at assembly time:
     - Code line evidence: line starting with `def `, `class `, `import `, `from ... import `, line ending in `;` that contains `=` or `(`, or indentation of $\ge 4$ spaces/tab directly following another code line.
     - Runs of $\ge 2$ code lines (or 1 strong signature like `def foo():`) get `render_as="code"`.
     - Ordinary prose (even with semicolons, words like "return on investment", "a class of problems") gets `render_as="prose"`.
   - Each student block contains:
     - `text`: the verbatim newline-joined text of those lines.
     - `render_as`: `"code"` or `"prose"`.
     - `source_line_ids`: list of UUID strings for each contained line (`line.lineage_id`).
   - Invariant: Transcript line text has no embedded newlines (`\n` or `\r`). Joining the block's source lines deterministically reproduces each line's exact original text verbatim.
2. **Prompt Injection Safety:**
   - Escape closing XML delimiters (`</student_transcript>`, `</reference_evidence>`, `</other_topics>`) in transcript text before prompt interpolation. Wrap all prompt inputs in strict XML data blocks.
3. **Addition Proposals by Writer (LLM with Thinking Disabled):**
   - The model outputs additions only, with thinking mode explicitly turned off:
   ```python
   class AdditionDraft(BaseModel):
       after_line_id: str | None = None  # None indicates top of section
       kind: Literal["explanation", "possible_issue"]
       text: str
       citation_ids: list[str] = Field(min_length=1)

   class TopicWriterOutput(BaseModel):
       additions: list[AdditionDraft]
   ```
   - **Feature Flag for `possible_issue`:** Governed by `settings.ENRICHMENT_ENABLE_POSSIBLE_ISSUE` (default `True`). When disabled, prompt restricts additions strictly to `kind="explanation"` and omits `possible_issue`.
4. **Anchor Validation (`after_line_id`):**
   - Validate `after_line_id` against the topic's assigned line IDs.
   - If `after_line_id` is unknown or points outside the topic, **append the addition to the end of the topic's student blocks** (do not discard the addition).
5. **Section Block Data Structure:**
   ```python
   class SectionBlock(BaseModel):
       type: Literal["student", "addition", "heading"]
       text: str
       render_as: Literal["prose", "code"] = "prose"
       line_ids: list[str] = []                                    # Populated for student blocks
       citation_ids: list[str] = []                                # Populated for addition blocks
       addition_kind: Optional[Literal["explanation", "possible_issue"]] = None
       support_status: Literal["supported", "partial", "unsupported", "unverified"] = "unverified"
   ```
6. **Writer Rules & Safeguards:**
   - **Budget Cap:** At most `ENRICHMENT_MAX_ADDITIONS_PER_TOPIC` (default 4) additions per topic.
   - **Restatement Filter:** An addition with `kind == "explanation"` that restates any student line in the topic (embedding cosine similarity > `RESTATE_COSINE`, default 0.90) is dropped in code.
   - **Correction Exemption:** Additions with `kind == "possible_issue"` are **strictly exempt** from the restatement filter because a valid correction naturally addresses the same semantic content as the flawed student claim.
   - **Possible Issue Separation:** A `possible_issue` must cite reference evidence, be phrased as a constructive margin note/flag, and never overwrite the student's text.
   - **Granular Addition Validation:** Additions are validated individually. If Addition 1 has invalid citations, drop Addition 1 only; do not discard valid Addition 2.
   - **Writer Failure Fallback:** If the writer fails schema validation or times out after retries, emit the verbatim student blocks only and set `writer_failed=True`.

---

### 3.3a Topic Research & Evidence Preparation (`topic_research_node.py`)

1. **Decoupled Internal Retrieval:**
   - Formulate query per topic: `"{title}. {description}. {first_60_words_of_lines}"`.
   - Subject resolution: use topic's resolved `subject`, falling back to `document.subject`.
   - Invoke `retrieve_reference_context(query, profile=profile, subject=resolved_subject, top_k=6)`.
   - **Subject Filter Fallback:** If search with the subject filter returns 0 chunks, **retry once without the subject filter** (global reference search) before concluding no references exist.
2. **Dense Cosine Calculation for All Candidates:**
   - `retrieve_reference_context` returns `dense_score` (raw cosine similarity: $1.0 - \text{distance}$) and `score` (RRF fused score).
   - If a candidate was returned by keyword search only, compute its dense cosine score against `qvec` so every returned candidate has a valid `dense_score`.
   - Filter: drop chunks where `dense_score < RELEVANCE_MIN_DENSE`.
   - `RELEVANCE_MIN_DENSE` is calibrated on the evaluation set using off-topic control queries to prevent false positives.
3. **Sentence Filtering & Token Budget:**
   - Sentences from retrieved reference chunks are ranked by embedding cosine similarity to the topic query.
   - **Batched Sentence Embedding & Caching:** All candidate sentences are embedded in a single batched embedding call via `qwen3-embedding:0.6b` and cached by sentence hash to minimize latency without consuming LLM budget.
   - Greedily accumulate top sentences up to `EVIDENCE_TOKEN_BUDGET` (default 1500 tokens).
   - Deduplicate by sentence hash.
4. **Manifest Assembly:**
   - Assign stable citation IDs: `C1`, `C2`, ..., `Cn` (local to topic; renumbered globally at render time).
   - Build evidence manifest:
     ```python
     class EvidenceItem(BaseModel):
         citation_id: str             # e.g. "C1"
         chunk_id: str
         source_type: Literal["book"] = "book"  # Decoupled; PR 3 can add "web"
         document_id: str
         source_title: str
         chapter: str = ""
         page_start: int
         page_end: int
         snippet: str
         dense_score: float
         rrf_score: float
     ```
5. **Evidence Status Gate:**
   - Compute `evidence_status`: `sufficient` (>= 2 relevant chunks), `partial` (1 chunk), or `none` (0 chunks).
   - If `evidence_status == "none"`, **skip the writer entirely**, emit student blocks only, and set `evidence_status="none"` with flag `no_reference_found`.
   - Store research results in state under a dedicated dictionary: `research_by_topic: dict[str, TopicResearchResult]` so repair can reuse it directly.

---

### 3.4 Parallel Fan-Out (`Send`) & Reducer

1. **LangGraph `Send` Fan-Out:**
   - Dispatch parallel topic branches:
     `[Send("topic_branch", {"topic": t, "document_id": doc_id}) for t in planned_topics]`
   - Each branch executes: `Topic Research Node` → `Evidence Gate` → `(Topic Writer Node | Skip)`.
2. **Concurrency Bounding:**
   - Bound parallel execution to `ENRICHMENT_CONCURRENCY` (default 2) to prevent local Ollama saturation.
3. **Dictionary Reducer:**
   - Collects completed topics into `sections_by_topic: dict[str, EnrichedSection]` and research into `research_by_topic: dict[str, TopicResearchResult]`.

---

### 3.5 Citation Sanitization & Guarded Deduplication (`sanitize_dedupe_node.py`)

> [!IMPORTANT]
> Sanitization and Deduplication run **before** verification.

1. **Citation Sanitization:**
   - Deterministically verifies that all `citation_ids` in addition blocks exist in that topic's evidence manifest.
   - Strips ungrounded citation IDs.
   - If an addition has 0 valid citation IDs remaining, drop that addition individually.
2. **Guarded Deduplication:**
   - Embed all addition blocks across all topics using the local embedder (`hashing` in tests, `qwen3-embedding:0.6b` in production).
   - Compute pairwise cosine similarity between additions in different topics.
   - Find candidate pairs with similarity > `DUP_COSINE` (default 0.88).
   - **Pair Cap:** Cap candidate pairs at `MAX_DEDUPE_PAIRS = 6` per run. The optional LLM budget decides how many pairs receive an LLM deduplication call.
   - For evaluated pairs, LLM deduplication prompt proposes: `keep_first`, `keep_second`, `merge`, or `keep_both`.
   - **Invariants:**
       - Deduplication is strictly forbidden from touching `student` blocks.
       - Any merged addition must preserve all citations from both source additions.
       - `keep_both` leaves both additions completely intact if they represent distinct concepts despite high semantic similarity.

---

### 3.6 Verification & Bounded Writer-Only Repair (`verification_node.py`)

1. **Deterministic Line Coverage Verification:**
   - Checks that 100% of assigned `line_id` UUIDs appear in the student blocks.
   - **Invariant Handling:** Since code constructs student blocks directly, coverage failure indicates an internal code bug. Treat it as an immediate terminal failure (`Job` status `FAILED_DEAD_LETTER`, `metadata.outcome = "coverage_bug"`), **not** a repair target. The existing active `EnrichedNote` remains active.
2. **Semantic Evidence Support Scoring (Best-Matching Sentence):**
   - Compare each addition against the **best-matching sentence** of its cited chunk(s), rather than the whole snippet.
   - Compute cosine similarity and lexical n-gram overlap.
   - **Decision Matrix:**

| Cosine Similarity | Lexical Overlap | Decision / Outcome |
| :--- | :--- | :--- |
| $\ge \text{SUPPORT\_COSINE}$ (0.75) | $\ge \text{SUPPORT\_LEXICAL}$ (0.30) | `supported` |
| $\ge \text{SUPPORT\_COSINE}$ (0.75) | $< \text{SUPPORT\_LEXICAL}$ (0.30) | `supported` (paraphrase with low n-gram overlap; cosine is primary signal) |
| $[\text{BORDERLINE}, \text{SUPPORT\_COSINE})$ (0.60..0.74) | $\ge \text{SUPPORT\_LEXICAL}$ (0.30) | `partial` |
| $[\text{BORDERLINE}, \text{SUPPORT\_COSINE})$ (0.60..0.74) | $< \text{SUPPORT\_LEXICAL}$ (0.30) | Invoke LLM Entailment check: `ENTAILED` -> `supported`; `PARTIALLY_ENTAILED` -> `partial`; `NEUTRAL`/`CONTRADICTED` -> `unsupported` (dropped). If topic optional budget exhausted, drop without call and increment `dropped_for_budget`. |
| $< \text{SUPPORT\_COSINE\_BORDERLINE}$ (0.60) | Any | `unsupported` (dropped) |

3. **`possible_issue` Contradiction Verification:**
   - For every `possible_issue` addition, execute an entailment check comparing the student line directly against the cited evidence sentence:

| Entailment Verdict | Outcome | Rationale |
| :--- | :--- | :--- |
| `CONTRADICTED` | Keep as `possible_issue` | Evidence genuinely contradicts the student line. |
| `PARTIALLY_ENTAILED` | Keep as `possible_issue`, mark `partial` | Incomplete or imprecise student claim. |
| `ENTAILED` | **Drop** addition | The student is factually correct; eliminates false corrections. |
| `NEUTRAL` | Downgrade to `explanation` | Evidence adds context but does not contradict; subject to support table. |

   - **Budget Exhaustion Guard:** If topic optional budget is exhausted, **drop unverified `possible_issue` additions unchecked** to guarantee that unverified false corrections are never presented to the student. Record in `diagnostics["dropped_for_budget"]`.
   - **Standalone Prompt Evaluation:** Before enabling in production, the entailment prompt will be evaluated standalone on 30 hand-labeled `(student line, evidence sentence)` pairs to ensure accuracy exceeds 85%.
4. **Definition of `needs_attention` vs. Dropped Additions:**
   - Dropping unsupported additions is normal verification behavior and is recorded in `diagnostics`. It does **not** trigger repair or `needs_attention`.
   - `needs_attention` is strictly reserved for:
     1. Topics where `writer_failed=True` on a topic with `evidence_status == "sufficient"` that still fails after repair.
     2. Topics where `planner_fallback=True` occurred.
5. **Bounded Writer-Only Repair Loop with Pass Numbering:**
   - Identify `repair_targets`: topics with `writer_failed=True` and sufficient evidence.
   - Skip repair if `repair_targets` is empty, or if topic optional budget is exhausted.
   - **Repair Pass Numbering:** To prevent the `checkpointed` wrapper from returning the stored pre-repair checkpoint row, stage names for the repair loop include the pass number:
     - Normal execution: `write#0`, `sanitize_dedupe#0`, `verify#0`.
     - Repair pass 1: `write#1`, `sanitize_dedupe#1`, `verify#1`.
   - **What Changes on Repair:**
     1. Supply a simplified prompt with a reduced evidence set (top-2 chunks instead of top-6).
     2. Lower temperature (`temperature = 0.0`).
     3. Directly invoke `Topic Writer Node`, **reusing stored research** from `research_by_topic`. Retrieval is never re-run.
     4. Route repaired sections back through `Sanitize Node` → `Dedupe Node` → `Verifier Node` under pass `#1`.
   - Terminate after `MAX_REPAIR_PASSES = 1`. If issues persist, mark final status as `needs_attention`.

---

### 3.7 Pure Rendering & Database Persistence (`render_node.py` & `apps/ai_classroom/services.py`)

1. **Pure Rendering (`render_node.py`):**
   - Orders sections strictly by `TopicPlan.topics` index.
   - Renders blocks directly based on backend-assigned `render_as`:
     - Blocks with `render_as == "code"` are wrapped in markdown fenced code blocks (` ``` `).
     - Blocks with `render_as == "prose"` are rendered as paragraphs.
     - Frontend never re-detects code or overrides `render_as`.
   - **Global Citation Renumbering:** Renumber local citation IDs (`C1..Cn`) into unified ascending global indices (`[^1]`, `[^2]`, ..., `[^K]`) throughout the Markdown body and corresponding bibliography.
2. **Outcome to Job Status Mapping:**

| Execution Outcome | `Job.status` | `Job.metadata["outcome"]` | `Job.metadata["error_code"]` | User-Facing `latest_job.message` | Note Created? | Previous Note Active? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Clean completion | `SUCCEEDED` | `"ok"` | `""` | `"Enrichment generated successfully."` | Yes (`status="ok"`) | Superseded |
| Unresolved failure | `SUCCEEDED` | `"needs_attention"` | `""` | `"Enrichment completed with items needing review."` | Yes (`status="needs_attention"`) | Superseded |
| Already up to date | `SUCCEEDED` | `"already_up_to_date"` | `""` | `"Enrichment is already up to date."` | **No** | Remains Active |
| Not ready | `SUCCEEDED` | `"not_ready"` | `"NOT_READY_FOR_ENRICHMENT"` | `"Please review and approve all note pages first."` | **No** | Remains Active |
| Insufficient content | `SUCCEEDED` | `"insufficient_content"` | `"INSUFFICIENT_CONTENT"` | `"Not enough academic content to generate enrichment."` | **No** | Remains Active |
| No study content | `SUCCEEDED` | `"no_study_content"` | `"NO_STUDY_CONTENT"` | `"No technical study notes identified in transcript."` | **No** | Remains Active |
| Coverage bug | `FAILED_DEAD_LETTER` | `"coverage_bug"` | `"COVERAGE_INVARIANT_FAILED"` | `"An internal verification error occurred. Please retry."` | **No** | Remains Active |
| Soft time limit | `FAILED_RETRYABLE` | `"soft_time_limit"` | `"TIMEOUT_RETRYABLE"` | `"Enrichment is processing; resuming from checkpoint."` | **No** | Remains Active |
| Aborted not running | `CANCELLED` | `"aborted_not_running"` | `"JOB_NOT_RUNNING"` | `"Enrichment was cancelled or reaped."` | **No** | Remains Active |
| Superseded by newer | `SUCCEEDED` | `"superseded_by_newer"` | `""` | `"Superseded by a newer enrichment."` | **No** | Remains Active |

3. **Atomic Persistence, Late-Worker Protection & Staleness:**
   - Executed within `transaction.atomic()`.
   - **Locking Order:** Invariant strictly enforced: **Page first, then Document**.
   - **Lock Job & Concurrency Check:** Lock the `Job` row: `job = Job.objects.select_for_update().get(pk=job.pk)`.
     - If `job.status != Job.Status.RUNNING` (e.g. reaped by watchdog), **abort immediately without persisting any note**. Record `metadata["outcome"] = "aborted_not_running"`.
   - **Lock Document & Late Job Check:** Lock the `Document` row: `doc = Document.objects.select_for_update().get(pk=document.pk)`.
     - Check job creation timestamp via the active note's `generation_job`: if a newer job (`created_at > current_job.created_at` or `pk > current_job.pk`) has already persisted an active note for this document, **abort note creation**, record `metadata["outcome"] = "superseded_by_newer"` on the `Job`, and exit.
   - **Persist Note ONLY for `ok` and `needs_attention`:**
     - Mark previous active notes: `EnrichedNote.objects.filter(document=doc, superseded=False).update(superseded=True)`.
     - Create `EnrichedNote`:
       - `status`: strictly `"ok"` or `"needs_attention"`.
       - `generation_job`: `job`.
       - `content_hash`: `start_hash`.
       - `force_include_hash`: captured from `job.metadata["force_include_hash"]` (computed at job start).
       - `settings_version`: captured from `job.metadata["settings_version"]`.
       - `evidence_status_by_topic`: dict mapping `topic_id -> ("sufficient" | "partial" | "none")`.
       - `excluded_segments`: JSON list.
       - `diagnostics`: JSON map (repair counts, latency, tokens, remaining LLM budget, `dropped_for_budget`).
     - Dedicated Topic Heading Block: `block_kind="heading"`, `render_as="prose"`, `block_type="topic_heading"`, `content=topic.title`, `topic_id=topic.id`.
     - Section Blocks: `block_kind` (`"heading"`, `"student"`, `"addition"`), `render_as` (`"prose"`, `"code"`), `block_type` (legacy mapping), `source_line_ids`, `support_status`, `addition_kind`. Existing blocks from migration default to `block_kind="legacy"`, `render_as="prose"`.
     - `CitationBlock`: maps manifest into `source_refs` JSON with `source_type="book"`, `chunk_id`, `document_id`, `source_title`, `chapter`, `page_start`, `page_end`, `snippet`, `retrieval_score` (storing both `dense_score` and `rrf_score`).
4. **In-Transaction Staleness Check & Two-Way Post-Commit Hook:**
   - Recompute `_descriptor(document)` **inside the transaction while holding the document lock**.
   - If `start_hash != current_descriptor`, set `ai_stale = True` immediately before committing.
   - **Two-Way Post-Commit Hook:** Schedule `transaction.on_commit` calling `sync_enrichment_staleness(doc.id)`:
     ```python
     def sync_enrichment_staleness(document_id: str) -> None:
         # Page then Document lock ordering
         with transaction.atomic():
             doc = Document.objects.select_for_update().get(id=document_id)
             current_hash = _descriptor(doc)
             # Two-way sync: set stale if hash differs, clear stale if hash matches
             EnrichedNote.objects.filter(document=doc, superseded=False).exclude(content_hash=current_hash).update(ai_stale=True)
             EnrichedNote.objects.filter(document=doc, superseded=False, content_hash=current_hash).update(ai_stale=False)
     ```
5. **Revert Clears Stale in PR 1 Helper (`backend/apps/documents/services.py`):**
   - In `sync_page_approval_and_indexing`:
     ```python
     # Strict lock ordering: Page is already locked by caller; now acquire Document lock
     doc = Document.objects.select_for_update().get(id=document.id)
     new_hash = _descriptor(doc)
     EnrichedNote.objects.filter(document=doc, superseded=False).exclude(content_hash=new_hash).update(ai_stale=True)
     EnrichedNote.objects.filter(document=doc, superseded=False, content_hash=new_hash).update(ai_stale=False)
     ```
   - Editing and reverting back to the approved text (A -> B -> A) automatically resets `ai_stale = False`.

---

## 3.8 Runtime, Checkpointing, Budgets & Concurrency

1. **`checkpointed(stage, topic_id)` Wrapper with Stage Numbering:**
   - Custom decorator/wrapper for LangGraph stage executions.
   - Uses additive model fields: `JobExecutionState.topic_id` with `UniqueConstraint(job, completed_node, topic_id)`.
   - Stage names include pass indices during repair (e.g. `write#0` vs `write#1`).
   - Before executing:
     - Updates `job.heartbeat_at = timezone.now()` at the start of every node.
     - Checks `JobExecutionState.objects.filter(job=job, completed_node=stage, topic_id=topic_id).first()`.
   - If found: deserializes Pydantic state from JSON and returns it immediately without executing the node.
   - If not found: executes node, writes `JobExecutionState(job=job, completed_node=stage, topic_id=topic_id, state_json=serialized_state, calls_used=stage_calls)`, and updates `job.heartbeat_at = timezone.now()`.
   - Checkpointing applies across every stage: `classify`, `plan`, `research`, `write`, `sanitize_dedupe`, and `verify`.
   - Pydantic models are validated to round-trip cleanly to/from JSON.
2. **Deterministic LLM Budget Allocation & Thread Safety:**
   - Total cap: `ENRICHMENT_MAX_LLM_CALLS = int(getattr(settings, "ENRICHMENT_MAX_LLM_CALLS", 25))`.
   - **Reservation Architecture:**
     - Essential calls: 1 (classify) + 1 (plan) + `num_topics` (1 writer per topic).
     - Remaining optional budget = `ENRICHMENT_MAX_LLM_CALLS - (2 + num_topics)` (e.g. $25 - 8 = 17$ calls for 6 topics).
     - **Deterministic Per-Topic Quota:** Each topic receives `optional_quota = remaining_optional // num_topics` (e.g. 2 calls per topic).
     - Spend quota in strict priority order:
       1. `possible_issue` contradiction checks
       2. Borderline addition entailment checks
       3. Deduplication calls
       4. Repair calls
     - When a topic's quota is exhausted, subsequent optional checks are dropped and recorded in `diagnostics["dropped_for_budget"]`.
   - **Thread Safety:** In-memory budget counters are protected via `threading.Lock()`.
   - **Resume State Preservation:** On resume from a soft time limit or retry, compute `llm_budget_consumed = sum(row.calls_used for row in JobExecutionState.objects.filter(job=job)) + 1` (conservative in-flight allowance). Retries do NOT receive a fresh budget.
3. **Job Deduplication, Input Capture & Unique Database Keys:**
   - **Unique Database Key with Run Nonce:** Because `Job.idempotency_key` has a `unique=True` constraint, assign each dispatched job a unique run key:  
     `idempotency_key = f"enrich_note:{document.id}:{start_hash}:{uuid.uuid4().hex[:8]}"`
   - In `get_or_create_job`: Deduplicate **only against in-flight jobs (`QUEUED`, `RUNNING`, `FAILED_RETRYABLE`)** via a database query matching `document_id` and `resource_type`. Finished jobs do not block new runs.
   - **Capture Inputs at Job Start:** Compute and store in `Job.metadata` at dispatch:
     - `job.metadata["force_include_hash"] = sha256(",".join(sorted(doc.force_include_line_ids))).hexdigest()[:16]`
     - `job.metadata["force_include_line_ids"] = list(doc.force_include_line_ids)`
     - `job.metadata["settings_version"] = sha256(f"{CLASSIFIER_MODEL}:{PLANNER_MODEL}:{WRITER_MODEL}:{RELEVANCE_MIN_DENSE}:{SEGMENT_MIN_CONFIDENCE}:{SUPPORT_COSINE}:{SUPPORT_LEXICAL}:{DUP_COSINE}:{MAX_TOPICS}:{MAX_ADDITIONS}:{PROMPT_VERSION}").hexdigest()[:16]`
   - **Early Exit Check inside Worker:**
     - Check if an active, non-stale `EnrichedNote` exists matching:
       `note.content_hash == start_hash AND note.force_include_hash == job.metadata["force_include_hash"] AND note.settings_version == job.metadata["settings_version"] AND note.ai_stale == False`.
     - If all three match and note is fresh: exit early as `SUCCEEDED` with `metadata.outcome = "already_up_to_date"`, user message `"Enrichment is already up to date."`.
     - If `force_rerun=True` is provided in the request, override the check and execute.
4. **Heartbeat Watchdog, Soft Time Limits & Retry Caps:**
   - **Heartbeat Reaping (300s):** `reap_stuck_enrichment_jobs_task` in `apps.jobs.tasks`, scheduled via Celery beat, reaps jobs where `heartbeat_at < timezone.now() - timedelta(seconds=ENRICHMENT_PROCESSING_TIMEOUT)`. A slow but checkpointing job is never killed.
   - On each Celery attempt start, restart the processing clock: `job.started_at = timezone.now()`, `job.heartbeat_at = timezone.now()`.
   - Celery tasks enforce `max_retries = 2`.
   - Catch Celery's `SoftTimeLimitExceeded` (limit 270s, watchdog 300s) on worker tasks: serialize current checkpoint and fail cleanly as `FAILED_RETRYABLE` so Celery retries resume from the last completed checkpoint.
   - `ENRICHMENT_NODE_TIMEOUT` (default 60s) enforced as HTTP timeouts on the underlying Ollama client sessions.
5. **Configuration Settings (`backend/config/settings/base.py`):**
   ```python
   ENRICHMENT_CONCURRENCY = int(os.environ.get("ENRICHMENT_CONCURRENCY", "2"))
   ENRICHMENT_NODE_TIMEOUT = int(os.environ.get("ENRICHMENT_NODE_TIMEOUT", "60"))
   ENRICHMENT_PROCESSING_TIMEOUT = int(os.environ.get("ENRICHMENT_PROCESSING_TIMEOUT", "300"))
   ENRICHMENT_MAX_TOPICS = int(os.environ.get("ENRICHMENT_MAX_TOPICS", "6"))
   ENRICHMENT_MAX_ADDITIONS_PER_TOPIC = int(os.environ.get("ENRICHMENT_MAX_ADDITIONS_PER_TOPIC", "4"))
   ENRICHMENT_MAX_LLM_CALLS = int(os.environ.get("ENRICHMENT_MAX_LLM_CALLS", "25"))
   EVIDENCE_TOKEN_BUDGET = int(os.environ.get("EVIDENCE_TOKEN_BUDGET", "1500"))
   MAX_DEDUPE_PAIRS = int(os.environ.get("MAX_DEDUPE_PAIRS", "6"))

   SEGMENT_MIN_CONFIDENCE = float(os.environ.get("SEGMENT_MIN_CONFIDENCE", "0.60"))
   RELEVANCE_MIN_DENSE = float(os.environ.get("RELEVANCE_MIN_DENSE", "0.45"))  # Calibrated on eval set
   DUP_COSINE = float(os.environ.get("DUP_COSINE", "0.88"))
   RESTATE_COSINE = float(os.environ.get("RESTATE_COSINE", "0.90"))
   SUPPORT_COSINE = float(os.environ.get("SUPPORT_COSINE", "0.75"))
   SUPPORT_COSINE_BORDERLINE = float(os.environ.get("SUPPORT_COSINE_BORDERLINE", "0.60"))
   SUPPORT_LEXICAL = float(os.environ.get("SUPPORT_LEXICAL", "0.30"))

   ENRICHMENT_ENABLE_POSSIBLE_ISSUE = os.environ.get("ENRICHMENT_ENABLE_POSSIBLE_ISSUE", "true").lower() == "true"
   PROMPT_VERSION = "enrichment_v2"

   # Per-node model settings matching deployed Qwen 3.5 4B baseline
   CLASSIFIER_MODEL = os.environ.get("ENRICHMENT_CLASSIFIER_MODEL", "qwen3.5:4b")
   PLANNER_MODEL = os.environ.get("ENRICHMENT_PLANNER_MODEL", "qwen3.5:4b")
   WRITER_MODEL = os.environ.get("ENRICHMENT_WRITER_MODEL", "qwen3.5:4b")
   WRITER_FALLBACK_MODEL = os.environ.get("ENRICHMENT_WRITER_FALLBACK_MODEL", "qwen3.5:4b")
   VERIFIER_MODEL = os.environ.get("ENRICHMENT_VERIFIER_MODEL", "qwen3.5:4b")
   ```

---

### 3.9 API & Frontend Integration

1. **Endpoints & Views (`apps/ai_classroom/views.py` & `urls.py`):**
   - `GET /api/v1/documents/{id}/enrichment`: Returns:
     ```json
     {
       "note": EnrichedNoteSerializer(note).data if note else None,
       "latest_job": {
         "id": str(job.id),
         "status": job.status,
         "outcome": job.metadata.get("outcome", ""),
         "error_code": job.metadata.get("error_code", ""),
         "message": job.metadata.get("message", ""),
         "progress": {
           "stages_completed": [...],
           "topics_total": 4,
           "topics_completed": 2
         }
       } if job else None
     }
     ```
     `latest_job.message` is determined strictly from `error_code` / `outcome`, never exposing raw exception text from `job.last_error`. `progress` is computed from existing `JobExecutionState` rows.
   - `POST /api/v1/documents/{id}/enrichment/regenerate`: Accepts optional `{"force_rerun": true}`. Dispatches new enrichment job with run nonce. Retains previous `Document.force_include_line_ids`. The previous note remains visible until the new run finishes.
   - `POST /api/v1/documents/{id}/enrichment/force-include`: Accepts `{"force_include_line_ids": [...]}`. Validates against document's approved `lineage_id`s (returns HTTP 422 on unknown IDs). Replaces the stored list in `Document.force_include_line_ids` (an empty list `[]` clears it). At runtime, drops any line IDs that no longer exist on the document. **Automatically dispatches a regenerate run in the same API call.**
   - Enforce profile RLS and `ready_for_enrichment` on both mutation endpoints.
2. **Frontend API Client (`frontend/src/services/api/enrichment.ts`):**
   - TypeScript methods: `getEnrichment`, `regenerateEnrichment`, `forceIncludeSegments`.
3. **Frontend Review Experience (`frontend/src/components/notes/EnrichedView.tsx`):**
   - **Distinct Visual Styling:** Student blocks styled with distinct handwritten/body typography; additions styled with subtle background tint, left border, and author badge ("StudyAI Addition").
   - **Legacy Blocks:** Blocks with `block_kind="legacy"` render without the "StudyAI Addition" badge, preserving legacy appearance.
   - **Fenced Code Blocks:** Rendered strictly based on backend-supplied `render_as: "code"` vs `"prose"`.
   - **Badges & Flags:**
     - Render "No reference found" badge on topics where `evidence_status_by_topic[topic_id] == "none"`.
     - Render warning flag on `possible_issue` and `partial` additions.
   - **Excluded Segments Banner:** Show expandable notification for excluded segments with an "Include in notes" action triggering `force_include_line_ids`.
   - **Stale Notification:** Display amber banner when `ai_stale=True` with a direct "Regenerate Enrichment" button.
   - **Progress & Job Outcome States:** While `latest_job.status === "running"`, render progress bar with `progress.topics_completed / progress.topics_total`. When `note` is null or job failed, display user-facing messages from `latest_job.message` (e.g. "Not enough academic content yet", "No technical study notes identified in transcript") and action buttons ("Retry", "Regenerate").

---

### 3.10 Evaluation Set & Calibration Script (`scripts/evaluate_enrichment.py`)

1. **Evaluation Corpus Specification (`backend/tests/eval/fixtures/`):**
   - **Reference Corpus:** Short, open-licensed excerpts (OpenStax / CC-BY, ~10-20 pages per subject) placed in `backend/tests/eval/fixtures/reference_corpus/`. Avoids copyright issues and large binary blobs.
   - **Test Notes (Exactly 25 notes total):**
     - **14 standard multi-topic STEM notes** (algorithms, chemistry, physics, biology).
     - **6 mistake notes containing $\ge 15$ deliberate, hand-labeled student mistakes** (including subtle hard negatives / correct but unusual claims to test the false-correction path).
     - **5 edge cases** (including short code-only, formula-only, and at least 3 notes on topics completely absent from the reference corpus to test the `evidence_status == "none"` path).
   - **Real Embeddings for Evaluation:** `scripts/evaluate_enrichment.py` uses the **real embedding provider** (`qwen3-embedding:0.6b` via Ollama), not the unit-test hashing mock, ensuring similarity numbers reflect real semantic distributions.
   - **Golden Addition Labels:** Run once with the pipeline, freeze output additions, and hand-label 40+ additions (`supported`, `partial`, `unsupported`) to calibrate the semantic verifier.
2. **Automated Evaluation Script (`backend/scripts/evaluate_enrichment.py`):**
   - Executes the pipeline end to end across the evaluation set.
   - Computes and prints the quantitative quality scorecard with exact counts:
     - **Student Preservation Rate:** Target = **100%** (0 deleted, 0 rewritten student lines).
     - **Silent Correction Rate:** Target = **0%** (all corrections must be separate cited additions).
     - **False Correction Count:** Target $\le 1$ flag across 19 clean notes (measured across all correct student claims, including hard negatives).
     - **Missed Correction Count:** Target $\le 2$ misses across 15 seeded mistakes.
     - **Addition Support Accuracy:** Target >= **85%** against hand labels.
     - **Cross-Topic Duplication Rate:** Target < **5%**.
     - **Planner Fallback Rate:** Target < **10%**.
     - **Latency Target:** Set and reported based on the Section 0 audit baseline.
     - **LLM Call Budget:** Assert $\le 25$ LLM calls per note across all runs; report `dropped_for_budget` counts.
3. **Calibration Sweep:**
   - Evaluates off-topic control queries to calibrate optimal `RELEVANCE_MIN_DENSE` and borderline support thresholds before finalizing PR 2.

---

## 4. Proposed File Changes for PR 2

All file paths are relative to the repository root:

| File Path | Change Scope |
| :--- | :--- |
| `backend/apps/jobs/models.py` | Add `metadata = JSONField()` and `heartbeat_at = DateTimeField()` to `Job`. Add `topic_id = CharField()` and `calls_used = PositiveIntegerField()` to `JobExecutionState` with unique constraint `(job, completed_node, topic_id)`. |
| `backend/apps/jobs/migrations/0005_job_heartbeat_metadata_and_executionstate_topic.py` | Migration for `topic_id`, `calls_used`, `metadata`, and `heartbeat_at`. |
| `backend/apps/documents/models.py` | Add `force_include_line_ids = JSONField(default=list, blank=True)` to `Document`. |
| `backend/apps/documents/migrations/0012_document_force_include_line_ids.py` | Migration for `force_include_line_ids` on `Document`. |
| `backend/apps/documents/services.py` | Update `sync_page_approval_and_indexing` with document row lock (Page then Document) and `.filter(content_hash=new_hash).update(ai_stale=False)` for revert-clears-stale. |
| `backend/apps/ai_classroom/models.py` | Restrict `EnrichedNote.status` to `("ok", "needs_attention")`. Add `evidence_status_by_topic`, `excluded_segments`, `diagnostics`, `force_include_hash`, `settings_version`. Add `block_kind`, `render_as`, `topic_id`, `source_line_ids`, `support_status`, `addition_kind` to `EnrichedNoteBlock`. |
| `backend/apps/ai_classroom/migrations/0005_topic_enrichment_blocks.py` | Additive Django schema migration for new note and block fields. Default existing rows to `block_kind="legacy"`, `render_as="prose"`. |
| `backend/apps/ai_classroom/serializers.py` | Expose block fields, `render_as`, `evidence_status_by_topic`, `excluded_segments`, status, and `latest_job` with `progress` in DRF serializers. |
| `backend/apps/ai_classroom/views.py` | Update `EnrichedNoteView` to return note + `latest_job` with `progress`. Add `force-include` (auto-dispatching regenerate) and `regenerate` endpoints with nonce generation. |
| `backend/apps/ai_classroom/urls.py` | Register routes for `/enrichment/regenerate` and `/enrichment/force-include`. |
| `backend/apps/ai_classroom/content_gate.py` | Calibrate math/code pre-filter symbols (delete `-`, `/`, `(`, `)`). |
| `backend/apps/references/services.py` | Additively return `dense_score` (raw cosine similarity) and `keyword_score` in `retrieve_reference_context`. |
| `backend/ai/langgraph/state/topic_enrichment_state.py` | Pydantic and TypedDict state models (`SectionBlock`, `EvidenceItem`, `TopicPlan`, `ExcludedSegment`, `TopicResearchResult`, `LLMBudget`). |
| `backend/ai/langgraph/nodes/load_and_gate_node.py` | Load approved non-ignored lines, verify PR 1 readiness, apply content gate, capture inputs at job start, record job outcomes. |
| `backend/ai/langgraph/nodes/segment_classifier_node.py` | 60-line window classification with thinking disabled, boundary merging, deterministic gap normalization, subject mapping, excluded segments tracking. |
| `backend/ai/langgraph/nodes/topic_planner_node.py` | Plan topics (max 6) with thinking disabled, assign code topic IDs `t1..tn`, map `lineage_id`, orphan line attachment, single-topic fallback. |
| `backend/ai/langgraph/nodes/topic_research_node.py` | Query generation, `retrieve_reference_context` top-k=6, compute dense score for all candidates, `RELEVANCE_MIN_DENSE` filter, subject fallback, token budget sentence filtering with batched embeddings and caching. |
| `backend/ai/langgraph/nodes/topic_writer_node.py` | Verbatim student block assembly in code with `render_as` classification, LLM addition generation (`AdditionDraft`) with thinking disabled, restatement filter exempting `possible_issue`, `after_line_id` anchor fallback, XML delimiter escaping. |
| `backend/ai/langgraph/nodes/sanitize_dedupe_node.py` | Individual addition sanitization, cross-topic deduplication with `MAX_DEDUPE_PAIRS` cap and `keep_both` support. |
| `backend/ai/langgraph/nodes/verification_node.py` | Line coverage check (terminal bug check), best-matching sentence support scorer, `possible_issue` contradiction check, pre-repair code fixes, writer-only repair router with `#pass` naming. |
| `backend/ai/langgraph/nodes/render_node.py` | Order-preserving Markdown generation respecting `render_as`, global citation renumbering. |
| `backend/ai/langgraph/graphs/enrichment_graph.py` | LangGraph StateGraph with `Send` fan-out, dictionary reducer, `checkpointed` wrapper with stage numbering, and writer-only repair loop. |
| `backend/apps/ai_classroom/services.py` | Wire `run_enrichment_job` to topic graph, locked in-transaction staleness check, two-way post-commit hook, supersede older notes only on success, record job error states without creating stub notes. |
| `backend/apps/jobs/tasks.py` | Add `reap_stuck_enrichment_jobs_task` to Celery tasks with heartbeat checking (300s timeout) and soft time limit handling. |
| `backend/config/celery.py` | Schedule `reap_stuck_enrichment_jobs_task` in Celery beat. |
| `backend/config/settings/base.py` | Add `ENRICHMENT_CONCURRENCY`, `RELEVANCE_MIN_DENSE`, `SEGMENT_MIN_CONFIDENCE`, `DUP_COSINE`, `RESTATE_COSINE`, `SUPPORT_COSINE`, `SUPPORT_LEXICAL`, `ENRICHMENT_MAX_LLM_CALLS`, `MAX_DEDUPE_PAIRS`, `ENRICHMENT_ENABLE_POSSIBLE_ISSUE`, `PROMPT_VERSION`, model settings. |
| `backend/scripts/evaluate_enrichment.py` | Automated evaluation harness measuring student preservation, false/missed correction counts, support with real embeddings, latency, and calibration. |
| `backend/tests/eval/fixtures/reference_corpus/` | OpenStax / CC-BY reference text excerpts. |
| `backend/tests/eval/fixtures/enrichment_eval_set.json` | Exactly 25 corrected transcript text test notes with $\ge 15$ seeded mistakes and hard negatives. |
| `backend/tests/unit/test_topic_enrichment_pipeline.py` | Unit tests for classifier, planner, writer fallback, deduplication, and repair router. |
| `backend/tests/api/test_topic_enrichment_integration.py` | Integration tests for full graph, per-topic checkpointer resume, atomic persistence, real-thread concurrency, and staleness. |
| `frontend/src/services/api/enrichment.ts` | Frontend API client methods for enrichment retrieval, regeneration, and force-including segments. |
| `frontend/src/components/notes/EnrichedView.tsx` | Visual differentiation for student vs addition blocks, legacy block rendering, badges, excluded-segments banner, stale banner, progress indicator, needs_attention/failed UI. |
| `frontend/src/types/enrichment.ts` | TypeScript types for updated block fields, `render_as`, `evidence_status_by_topic`, `excluded_segments`, and `latest_job` with `progress`. |

---

## 5. Test & Verification Plan for PR 2

The following automated tests will be authored and verified:

- [ ] **Readiness Gate:** A not-ready document ends with status `not_ready` (HTTP 422) with 0 LLM calls made.
- [ ] **Job Outcomes for Early Exits:** A first-time failure, an `insufficient_content` result, and a `no_study_content` result each appear in `latest_job` with a user-facing message (never raw exception strings), leaving previous good notes intact.
- [ ] **Outcome Mapping Enforcement:** Each outcome (`not_ready`, `insufficient_content`, `no_study_content`, `coverage_bug`, `soft_time_limit`, `already_up_to_date`, `aborted_not_running`) maps strictly to its documented `Job.status`.
- [ ] **Deduplication Blocks In-Flight Only:** A job in `FAILED_RETRYABLE`, `QUEUED`, or `RUNNING` blocks a duplicate dispatch; a finished job does not block dispatch due to the run nonce.
- [ ] **Regenerate After Revert Clears Stale:** Regenerate after edit then revert (A -> B -> A) creates a fresh note without deduplication collision and clears the stale state.
- [ ] **Force-Include Input Change:** Changing `force_include_line_ids` produces a new note even when the transcript content hash is unchanged.
- [ ] **Force-Include Persistence & Clearance:** `force_include_line_ids` persists on Document, survives regenerate, rejects unknown IDs (422), drops non-existent line IDs at runtime, and clears when given `[]`.
- [ ] **Late-Finishing Job Race Protection:** A worker whose job was reaped aborts without persisting; an older job finishing late is detected via the note's `generation_job` link and does not supersede a newer note (`superseded_by_newer`).
- [ ] **Real-Thread Missed-Stale Race:** Concurrent edit committing while persistence runs leaves the note stale, verified via real OS threads (`RealThreadConcurrencyTests`).
- [ ] **Lock Order Page -> Document:** Concurrent edit and approve on different pages of one document strictly follow Page then Document locking without deadlocking.
- [ ] **Heartbeat Watchdog Reaping:** A slow job that keeps checkpointing (`heartbeat_at` updating at start of node and on write) is not reaped; a silent job exceeding 300s is reaped.
- [ ] **Unique Per-Topic Checkpoints:** `JobExecutionState` rows are unique per `(job, node, topic)`; two topic branches writing at once both persist.
- [ ] **Repair Changes Output:** Stage names include the repair pass number (`write#1`, `verify#1`), ensuring stored pre-repair rows are not reused and output changes.
- [ ] **Deterministic Budget Allocation & State Survival:** Essential calls (classify, plan, 1 writer per topic) are reserved; optional budget is allocated deterministically per topic; `dropped_for_budget` is recorded; budget survives checkpoint resume.
- [ ] **`possible_issue` Verdict Table:** Each verdict (`CONTRADICTED`, `PARTIALLY_ENTAILED`, `ENTAILED`, `NEUTRAL`) has a verified test case; budget exhaustion drops the flag.
- [ ] **Feature Flag `ENRICHMENT_ENABLE_POSSIBLE_ISSUE`:** With the flag disabled, no `possible_issue` additions are produced.
- [ ] **Thinking Mode Disabled:** Structured calls run with thinking explicitly disabled (`options={"think": False}`).
- [ ] **Code Grouping vs. Prose Single Source of Truth:** Student blocks arrive pre-split with `render_as`; prose with semicolons, "class", "return on investment" is never fenced; runs of real code lines are fenced into single code containers; frontend does not re-detect code.
- [ ] **Student Block Grouping Exactness:** Grouping consecutive student lines at assembly time reproduces each line's exact text when joined.
- [ ] **Dense Score Filtering & Keyword Hits:** Relevance threshold is applied to `dense_score` (cosine), not RRF; off-topic control queries yield `none`; a keyword-only retrieval hit is assigned a calculated dense score.
- [ ] **No Evidence Writer Skip:** Topics with 0 relevant chunks skip the writer and emit student blocks only with flag `no_reference_found`.
- [ ] **Verbatim Student Preservation:** Student blocks are 100% verbatim copies of approved transcript lines, regardless of what the LLM writer outputs.
- [ ] **Restatement Filter with Correction Exemption:** An addition restating a student line is dropped for `explanation`, but a `possible_issue` correction survives the restatement filter.
- [ ] **Writer Failure Fallback:** Writer failure, timeout, or malformed JSON falls back gracefully to student-only blocks flagged with `writer_failed=True`.
- [ ] **Planner Failure Fallback:** Planner failure after bounded retries falls back to a single topic containing all study lines and flags `planner_fallback=True`.
- [ ] **Unknown Anchor Handling:** An addition with an unknown or out-of-topic `after_line_id` appends to the end of the topic instead of being dropped.
- [ ] **Deduplication `keep_both` & Pair Capping:** A `keep_both` deduplication decision leaves both additions completely intact; dedupe pairs are capped at `MAX_DEDUPE_PAIRS`.
- [ ] **Coverage Failure Terminal Termination:** A coverage failure ends immediately as `FAILED_DEAD_LETTER` (as a code bug), not as a repair target.
- [ ] **Support Scoring Decision Matrix:** Paraphrases with low lexical overlap but high cosine similarity are marked `supported`; each row in the support table has a test case.
- [ ] **Prompt Delimiter Escaping:** An injection attempt via a closing delimiter (`</student_transcript>`) in a transcript line does not break prompt structure.
- [ ] **RLS Profile Isolation:** Another profile cannot read `latest_job`, `regenerate`, or `force-include`.
- [ ] **Frontend & Legacy Compatibility:** Legacy blocks with `block_kind="legacy"` render as before; new student and addition blocks render with distinct styles; progress bar renders stages and topic counts; `needs_attention` and `failed` display proper explanations and retry actions; auto-generation respects readiness.
- [ ] **Evaluation Harness:** `backend/scripts/evaluate_enrichment.py` runs end to end on the eval set (including hard negatives and out-of-corpus notes) with real embeddings, writes a baseline quality report, and prints exact counts.

---

## 6. Review Checkpoint & Definition of Done

PR 2 will be declared complete when:
1. The **Section 0 read-only audit** findings are fully verified and reported before writing PR 2 code.
2. All unit, integration, and concurrency tests in `test_topic_enrichment_pipeline.py` and `test_topic_enrichment_integration.py` pass cleanly.
3. The baseline quality report generated by `scripts/evaluate_enrichment.py` is committed with calibrated `RELEVANCE_MIN_DENSE` and support thresholds.
4. One manual end-to-end run is performed with the real local Ollama models, including verification of student/addition block styling in the frontend and an edit that triggers the `ai_stale` banner followed by a revert that clears it.
5. A concise report documenting any minor deviations from the plan and open items for PR 3 is presented for user review before proceeding.
6. **No code or commits are pushed without explicit user approval.**
