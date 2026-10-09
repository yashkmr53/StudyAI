# StudyAI — Complete Current-State System Audit

**Audit Date:** October 2026  
**Auditor:** Antigravity AI Engine  
**Authority:** Ground-Truth Codebase, Active Database, Live Configuration, and Direct Test Executions  
**Deliverable File:** `docs/product/full_system_audit.md`  
**Governing Rule:** AUDIT ONLY — ZERO CODE MODIFICATIONS  

---

## 1. Executive Summary

StudyAI is an intelligent, multi-turn AI study platform featuring dual operating modes: **NoteSpace** (faithful transcription, vector ink drawing, and typed PDF generation) and **AI Classroom** (handwritten note OCR, hybrid RAG retrieval, reference textbook grounding, concept gap analysis, and interactive chat).

This audit establishes the **absolute, current truth** of the repository by directly inspecting the code, database schema, active containers, runtime configuration, and running test suites. Prior implementation documents, phase reports, and READMEs were treated solely as historical artifacts.

### Key Headline Findings

1. **Core Product MVP is Live & Operable:**
   The primary student workflows—canvas note-taking, image upload, handwritten OCR transcription via `qwen3.5:4b`, hybrid RAG note enrichment, grounded textbook citations, multi-turn chat with source citations, and user-facing CRUD for subjects, folders, notes, and profiles—are functional and verified by automated browser E2E test runs (`phase9c`, `phase10c`, `phase10d`, `phase11`, `phase11_1`).
2. **Backend Test Suite Status:**
   Full backend pytest execution passed with **559 tests passed, 7 skipped, 0 failed** (in 35.34s using `--ds=config.settings.test`). Frontend Vitest suite passed with **73 tests passed across 11 test files** (in 1.04s).
3. **Severe Broken Components (Status G):**
   - **Password Reset:** `PasswordResetView` and `PasswordResetConfirmView` in `apps/accounts/views.py` fail immediately with `ImportError: cannot import name 'PasswordResetTokenService' from 'apps.accounts.services'` (missing `__init__.py` in `apps/accounts/services/`). Furthermore, model `PasswordResetToken` has no generated migration (`0003_passwordresettoken.py` is ungenerated) and its database table does not exist in PostgreSQL.
   - **Nightly Backup Celery Beat Job:** Scheduled at 02:30 UTC, `apps.audit.tasks.daily_backup` fails with `FileNotFoundError` every night because `pg_dump` is not installed in the Docker container image (only `libpq5` is installed, omitting `postgresql-client`).
   - **Agentic Chat View:** `POST /api/v1/chat/` (`AgentViewSet.chat` in `apps/agents/views.py`) fails with `NameError: name 'ChatMessage' is not defined` because `ChatMessage` was omitted from top-level imports.
4. **Critical Security Findings:**
   - **Global Reference Document Deletion:** In `ReferenceDocumentViewSet.destroy` (`apps/references/views.py` lines 125–128), unauthorized deletion of global platform references executes a `pass` statement instead of raising `403 Forbidden`, permitting any authenticated user to permanently delete platform-wide reference textbooks.
   - **PostgreSQL Row Level Security (RLS) is Completely Inactive:** All 27 RLS-enabled PostgreSQL tables have `relforcerowsecurity = false`. The container connects as the database table owner `studyai`, which PostgreSQL exempts from RLS by default. The planned restricted non-superuser role `studyai_app` was never created because `POSTGRES_INIT_SQL` is ignored by the base `pgvector` container.
   - **Missing Backend Sole-Profile Deletion Guard:** While the frontend sidebar prevents deleting a user's sole profile, `ProfileViewSet.destroy` lacks backend enforcement, permitting a user to delete their last profile and brick their account.
5. **Architectural & AI Stack Seams:**
   - **Accidental `.first()` Profile Association:** Multiple backend services (`apps/retrieval/retrieval.py:212`, `apps/revision/views.py:24`, `apps/tests/views.py:73`, `shared/authorization/services.py:61`) use `Profile.objects.filter(user=user).first()` instead of respecting the active profile header, leading to cross-profile data leakage for multi-profile users.
   - **Enrichment Graph Candidate Generation Drift:** The active enrichment graph in `enrichment_graph.py` wires `candidate_generation_node` and `coverage_comparison_node` to legacy `gap_candidates.py` (v1), which still depends on hardcoded `DOMAIN_CONCEPTS` dictionaries. The rewritten `gap_candidates_v2.py` (reference-structured concept extraction) is UNUSED in production runtime and only executed in evaluation tests.
   - **Pseudo-Streaming Chat:** Chat streaming via SSE does not stream live LLM generation tokens. It executes a synchronous, blocking LLM generation call, then chunks the completed text word-by-word with `time.sleep(0.025)` over the SSE socket.

---

## 2. Git & Repository State

### Repository Audit Summary

```
CURRENT_BRANCH:                  main
HEAD_COMMIT:                     ecc92fcfdf48c52b100e4e0670cca2364e3ba89f
HEAD_COMMIT_MESSAGE:             Merge pull request #16 from yashkmr53/feature/phase-11-1-enrichment-grounding
WORKTREE_STATUS:                 clean (nothing to commit, working tree clean)
LATEST_RELEVANT_PHASE_COMMIT:    ecc92fc (Phase 11.1), cb5682e (Phase 11), a7c11d2 (Phase 10D), 1b8f06a (Phase 10C)
```

### Phase Integration Verification

| Phase | PR / Commit | Integrated into `main`? | Notes / Verification |
|---|---|---|---|
| **Phase 9A** (Profile/Module Isolation) | PR #11 (`0b66c15`) | **YES** | Profile module filtering and header enforcement |
| **Phase 9B** (Note to Enrichment) | PR #12 (`37291a4`) | **YES** | Multi-page OCR and note ingestion pipeline |
| **Phase 10A** (CRUD Backend) | Commit `915ca38` (PR #13) | **YES** | Backend models and endpoints for notes, folders, subjects, profiles |
| **Phase 10B** (CRUD Frontend Integration) | Commit `8ca4ae2` (PR #13) | **YES** | Zustand workspaceStore integration with backend CRUD APIs |
| **Phase 10C** (CRUD UI & Polish) | Commits `1ecdfa1`, `7bc6a94` (PR #13) | **YES** | ActionMenu, collision-aware tooltips, collapsible sidebar |
| **Phase 10D** (Chat Multi-Turn Context) | PR #14 (`a7c11d2`, `59cb014`) | **YES** | Bounded conversation context in Ask StudyAI |
| **Phase 11** (Reference Library) | PR #15 (`cb5682e`, `7f91b05`) | **YES** | `ReferenceDocument`, `ReferenceChunk`, hybrid retrieval |
| **Phase 11.1** (Enrichment Grounding E2E) | PR #16 (`ecc92fc`, `48bff7e`) | **YES** | Real reference citation grounding in note enrichment |

### Divergent & Unmerged Branches

Branch `fix/RLS` (`origin/fix/RLS`) contains **8 unmerged commits** branched off `be243dd` (PR #8, September 2026):
- `1446523` text fix
- `b5f1c2a` final md file
- `8401125` feat: add PostgreSQL application password support and new database check scripts
- `7e60689` Refactor: Remove redundant optional imports across multiple state and schema files...
- `e9923a8` Remove obsolete validation scripts for G10, G11, G12, and G15 checks...
- `bace85d` enrichment fixes
- `d2960ec` feat: add new validation scripts for G10, G11, G12, and G15 checks
- `42d5736` fix/RLS

*Finding:* Work performed in `fix/RLS` to enforce database credentials and non-superuser application passwords was never completed, reviewed, or merged to `main`. `main` remains the authoritative production branch.

---

## 3. Status Categories & Definitions

Every capability in this report is assigned exactly one status category:

- **A. LIVE VERIFIED:** Code exists, runtime containers operate, and real execution/browser E2E verification exists (e.g., recorded in `frontend/tests/e2e/*_results.json`).
- **B. IMPLEMENTED:** Code exists and is covered by passing unit/API tests, but lacks recent real browser E2E test runs.
- **C. PARTIAL:** Implementation is partially functional; critical sub-features, persistence seams, or multi-profile edges are missing.
- **D. PLACEHOLDER / DEAD:** UI, endpoint, or component exists but is disconnected from backend logic or bypassed in execution.
- **E. SPEC ONLY:** Present in architectural specifications or documentation, but absent from the codebase.
- **F. UNKNOWN:** State cannot be determined from available evidence.
- **G. BROKEN:** Code exists but crashes or Demonstrates structural failure during real execution or invocation.

---

## 4. Product Capability Inventory

| Area | Capability / Feature | Status | Evidence (Code / Test / Migration) | Notes & Missing Work |
|---|---|---|---|---|
| **Auth** | User Registration | **A. LIVE VERIFIED** | `apps/accounts/views.py:RegisterView`, `tests/api/test_auth_flow.py` | Creates user + default profile atomically |
| **Auth** | Login & JWT Issue | **A. LIVE VERIFIED** | `apps/accounts/views.py:LoginView`, `frontend/tests/e2e/phase10c_results.json` | Scoped auth rate throttling, email normalization |
| **Auth** | Logout & Token Blacklist | **A. LIVE VERIFIED** | `apps/accounts/views.py:LogoutView`, `tests/api/test_auth_flow.py` | Revokes refresh token in `token_blacklist` |
| **Auth** | Token Refresh | **B. IMPLEMENTED** | `apps/accounts/views.py:RefreshView` | Standard SimpleJWT rotation + blacklist |
| **Auth** | Session Restoration | **A. LIVE VERIFIED** | `frontend/src/features/auth/authStore.ts:init`, `phase9c_results.json` | Token restored from localStorage |
| **Auth** | Password Reset Initiation | **G. BROKEN** | `apps/accounts/views.py:PasswordResetView` | `ImportError: cannot import name 'PasswordResetTokenService'` + unmigrated table |
| **Auth** | Password Reset Confirmation | **G. BROKEN** | `apps/accounts/views.py:PasswordResetConfirmView` | Unmigrated `PasswordResetToken` table does not exist in DB |
| **Profiles** | Create Profile | **A. LIVE VERIFIED** | `apps/profiles/views.py:ProfileViewSet`, `phase10c_results.json` | Unique per (user, module, name) |
| **Profiles** | List Profiles | **A. LIVE VERIFIED** | `apps/profiles/views.py:get_queryset`, `Sidebar.tsx` | Filtered by `X-Active-Module` |
| **Profiles** | Rename Profile | **A. LIVE VERIFIED** | `ProfileViewSet.perform_update`, `phase10c_results.json` | Validates duplicate names per module |
| **Profiles** | Switch Profile | **A. LIVE VERIFIED** | `Sidebar.tsx:switchToProfile`, `workspaceStore.ts:loadWorkspace` | Resets workspace store and re-fetches per profile |
| **Profiles** | Delete Profile | **A. LIVE VERIFIED** | `ProfileViewSet`, `phase10c_results.json` | Cascades to notes, subjects, sessions |
| **Profiles** | Sole-Profile Deletion Guard | **C. PARTIAL** | `Sidebar.tsx:handleDeleteProfile` (UI only) | **Missing in backend:** `ProfileViewSet` allows deleting sole profile via API |
| **Profiles** | Active Profile Persistence | **A. LIVE VERIFIED** | `authStore.ts`, `localStorage` key `active_profile_id` | Persists across browser refreshes |
| **Modules** | NoteSpace & AI Classroom | **A. LIVE VERIFIED** | `apps/profiles/models.py:Module`, `ModuleToggle.tsx` | Strictly scopes profiles and services |
| **Modules** | Module Switching | **A. LIVE VERIFIED** | `ModuleToggle.tsx`, `authStore.ts:switchModule` | Updates UI active module and profile |
| **Modules** | Profile/Module Isolation | **A. LIVE VERIFIED** | `apps/profiles/permissions.py:ModuleIsolationPermission` | Rejects mismatched `X-Active-Module` / `X-Active-Profile` |
| **Subjects** | Create Subject | **A. LIVE VERIFIED** | `apps/subjects/views.py:SubjectViewSet`, `phase10c_results.json` | Scoped to active profile |
| **Subjects** | List Subjects | **A. LIVE VERIFIED** | `SubjectViewSet.get_queryset`, `workspaceStore.ts` | Filtered by profile |
| **Subjects** | Rename Subject | **A. LIVE VERIFIED** | `SubjectViewSet`, `RenameDialog.tsx`, `phase10c_results.json` | Duplicate name validation in profile |
| **Subjects** | Delete Subject | **A. LIVE VERIFIED** | `SubjectViewSet`, `phase10c_results.json` | Cascades to notes, tests, chat sessions |
| **Folders** | Create Folder (Notebook) | **A. LIVE VERIFIED** | `apps/notebooks/views.py:NotebookViewSet`, `phase10c_results.json` | Subject-scoped folder record |
| **Folders** | List Folders | **A. LIVE VERIFIED** | `NotebookViewSet.get_queryset`, `workspaceStore.ts` | Filtered by user profile |
| **Folders** | Rename Folder | **A. LIVE VERIFIED** | `NotebookViewSet`, `phase10c_results.json` | Updates notebook title |
| **Folders** | Delete Folder | **A. LIVE VERIFIED** | `NotebookViewSet.destroy`, `phase10c_results.json` | Unfiles member notes (`on_delete=SET_NULL`) |
| **Folders** | Move Notes into Folder | **A. LIVE VERIFIED** | `apps/documents/views.py:update`, `phase10c_results.json` | Updates `document.notebook_id` |
| **Folders** | Folder Hierarchy / Subfolders | **C. PARTIAL** | `workspaceStore.ts:112`, `folderTree.ts` | **Seam:** Hierarchy stored only in local IndexedDB; backend `Notebook` is flat |
| **Notes** | Upload Note (Image/PDF) | **A. LIVE VERIFIED** | `apps/documents/views.py:create`, `phase9c_results.json` | Dispatches Celery OCR job |
| **Notes** | Rename Note | **A. LIVE VERIFIED** | `DocumentViewSet.partial_update`, `phase10c_results.json` | Updates `document.title` |
| **Notes** | Move Note (Folder/Unfiled) | **A. LIVE VERIFIED** | `MoveNoteDialog.tsx`, `phase10c_results.json` | Reassigns folder |
| **Notes** | Delete Note | **A. LIVE VERIFIED** | `DocumentViewSet.perform_destroy`, `phase10c_results.json` | Cleans up DB, MinIO images/PDFs, chunks, jobs |
| **Notes** | Direct URL & Reload | **A. LIVE VERIFIED** | `frontend/src/routes/index.tsx`, `phase9c_results.json` | Loads note directly via `/subjects/:sId/notes/:nId` |
| **Pages** | Multi-page Support | **B. IMPLEMENTED** | `apps/documents/models.py:DocumentPage`, `test_documents.py` | Supported in canonical schema; UI mostly single-page |
| **Pages** | Page Reordering / Deletion | **D. PLACEHOLDER** | `apps/notebooks/views.py:NotebookPageViewSet` | API exists for `NotebookPage`, but canonical `DocumentPage` has no reorder UI |
| **Canvas** | Drawing (Pen/Highlighter/Eraser) | **B. IMPLEMENTED** | `WritingPage.tsx`, `WritingToolbar.tsx`, `ink.ts` | Vector strokes with pressure and smoothing |
| **Canvas** | Autosave to IndexedDB | **B. IMPLEMENTED** | `db.ts:putStroke`, `WritingPage.tsx:drawStroke` | Immediate client-side persistence |
| **Canvas** | Offline Outbox & Retry | **B. IMPLEMENTED** | `services/sync/outbox.ts`, `useOutboxStore.ts` | Queues and retries stroke batches |
| **Canvas** | Device Locking & Fencing | **B. IMPLEMENTED** | `apps/canvas/views.py:CanvasSessionViewSet`, `test_canvas.py` | Single-writer fencing via `lock_generation` |
| **OCR** | Handwritten Vision OCR | **A. LIVE VERIFIED** | `providers/llm/qwen35.py:recognize`, `phase9c_results.json` | Vision transcription via `qwen3.5:4b` |
| **OCR** | Status & Polling | **A. LIVE VERIFIED** | `DocumentPage.ocr_status`, `HandwrittenView.tsx`, `phase9c_results.json` | Survives pending states without page reload |
| **OCR** | User Correction / Revision | **B. IMPLEMENTED** | `apps/documents/views.py:revisions`, `test_documents.py` | Immutable `DocumentPageRevision` creation |
| **NoteSpace** | Faithful Transcription View | **A. LIVE VERIFIED** | `HandwrittenView.tsx:TranscriptPanel`, `phase9c_results.json` | Verbatim text display from OCR lines |
| **NoteSpace** | Typed PDF Generation | **B. IMPLEMENTED** | `apps/documents/note_space.py:NoteSpaceService`, `pdf_renderer.py` | Content-addressed ReportLab PDF generation |
| **NoteSpace** | PDF Persistence & Download | **B. IMPLEMENTED** | `DigitizedDocument`, MinIO storage, signed URLs | Signed download URLs with TTL |
| **AI Classroom** | Note Chunking & Indexing | **A. LIVE VERIFIED** | `apps/retrieval/services.py:index_document`, `phase11_1_results.json` | Deterministic word-bounded chunking |
| **AI Classroom** | Dense pgvector Embeddings | **A. LIVE VERIFIED** | `retrieval.py:124`, `Qwen/Qwen3-Embedding-0.6B` | 1024-dim dense vectors stored in pgvector |
| **AI Classroom** | Keyword Full-Text Search | **A. LIVE VERIFIED** | `retrieval.py:140`, `SearchVectorField` (tsvector) | GIN-indexed English tsvector search |
| **AI Classroom** | Hybrid RRF Retrieval | **A. LIVE VERIFIED** | `retrieval.py:164`, `RetrievalService.search` | Reciprocal Rank Fusion (k=60) |
| **AI Classroom** | Note Enrichment Generation | **A. LIVE VERIFIED** | `enrichment_nodes.py:draft_node`, `phase11_1_results.json` | LangGraph multi-stage structured enrichment |
| **AI Classroom** | Concept Gap Detection | **C. PARTIAL** | `enrichment_nodes.py:candidate_generation_node` | Runs v1 candidates with hardcoded dictionaries; v2 unused |
| **AI Classroom** | Citation Generation & Linking | **A. LIVE VERIFIED** | `citation_stitch_node`, `EnrichedView.tsx`, `phase11_1_results.json` | Cites note page numbers and reference pages |
| **AI Classroom** | Citation Verification | **B. IMPLEMENTED** | `verification_graph.py`, `EvidenceVerifier` | Classifies supported vs unsupported citations |
| **References** | Reference Document Upload | **A. LIVE VERIFIED** | `ReferenceDocumentViewSet.create`, `phase11_1_results.json` | MultiPart upload stored to MinIO key |
| **References** | PDF Extraction & OCR Fallback | **A. LIVE VERIFIED** | `extraction.py:extract_pdf_pages`, `phase11_results.json` | Direct pypdf extraction + vision OCR fallback |
| **References** | Chunking & Vector Ingestion | **A. LIVE VERIFIED** | `ingestion.py:ingest_reference_document` | Batched embedding into `ReferenceChunk` |
| **References** | Shared Reference Retrieval | **A. LIVE VERIFIED** | `references/services.py:retrieve_reference_context` | Reusable across enrichment and Ask StudyAI |
| **References** | Reference Deletion & Cleanup | **A. LIVE VERIFIED** | `ReferenceDocumentViewSet.destroy`, `phase11_results.json` | Cleans up MinIO files, chunks, embeddings |
| **References** | Global Reference Deletion Guard | **G. BROKEN** | `ReferenceDocumentViewSet.destroy:125-128` | **Security hole:** `pass` permits non-staff to delete global docs |
| **Ask StudyAI** | New Conversation Thread | **A. LIVE VERIFIED** | `ChatSessionViewSet.create`, `ChatPage.tsx`, `phase10d_acceptance.mjs` | Subject-scoped or general threads |
| **Ask StudyAI** | Message Persistence | **A. LIVE VERIFIED** | `ChatMessage.objects.create`, `phase10d_acceptance.mjs` | User and assistant messages stored in DB |
| **Ask StudyAI** | Multi-Turn Bounded Context | **A. LIVE VERIFIED** | `chat/services.py:get_bounded_history`, `phase10d_acceptance.mjs` | Bounded to 20 messages / 12,000 chars |
| **Ask StudyAI** | Streaming Answer Output | **C. PARTIAL** | `ChatSessionViewSet.stream_message`, `ChatPage.tsx` | Pseudo-streaming: waits for full LLM output, then delays tokens |
| **Ask StudyAI** | Grounded Retrieval & Citations | **A. LIVE VERIFIED** | `langgraph_nodes.py:retrieve_node`, `phase11_results.json` | RRF fusion across user notes & reference chunks |
| **Questions** | Question Generation | **B. IMPLEMENTED** | `question_generation_nodes.py`, `test_learning_features.py` | Multi-format questions grounded in source chunks |
| **Questions** | Stale Question Tracking | **B. IMPLEMENTED** | `retrieval/services.py:188`, `Question.stale` | Superceded note chunks mark questions stale |
| **Tests** | Adaptive Test Creation | **B. IMPLEMENTED** | `tests/services.py:TestGenerationService`, `test_learning_features.py` | Deterministic priority (weakness first) |
| **Tests** | Attempt Submission & Scoring | **B. IMPLEMENTED** | `TestViewSet.attempts`, `MasteryScoringService` | Evaluates answers, updates mastery scores |
| **Mastery** | Scoring Service (EMA) | **B. IMPLEMENTED** | `MasteryScoringService.record_attempt`, `MasteryScore` | Exponential moving average, unassessed tags = none |
| **Tags** | Taxonomy & Stable Identity | **B. IMPLEMENTED** | `ai_classroom/models.py:Tag`, `test_learning_features.py` | Identity = (subject, stable_key); display names mutable |
| **Tags** | Tag Change Audit Logging | **B. IMPLEMENTED** | `TagChangeLog`, `test_tag_rename.py` | Logs tag additions, renames, and linkages |
| **Revision** | Revision Planner Backend | **B. IMPLEMENTED** | `apps/revision/views.py`, `revision_planning_graph.py` | Calculates schedules, goals, and mastery priorities |
| **Revision** | Revision Planner UI | **D. PLACEHOLDER** | `frontend/src/routes/index.tsx:189` | **Dead route:** `/revision` redirects to `/subjects` |

---

## 5. Backend Audit

### Installed Applications & Structure

| App Label | Path | Responsibilities | Key Views / Endpoints |
|---|---|---|---|
| `apps.accounts` | `backend/apps/accounts` | Custom `User`, registration, login, logout, password reset | `RegisterView`, `LoginView`, `LogoutView`, `PasswordResetView` |
| `apps.profiles` | `backend/apps/profiles` | Multi-profile scoping, active profile, module isolation | `ProfileViewSet` (`/api/v1/profiles`) |
| `apps.subjects` | `backend/apps/subjects` | Academic subjects, profile scoping, duplicate name guard | `SubjectViewSet` (`/api/v1/subjects`) |
| `apps.notebooks` | `backend/apps/notebooks` | Notebooks/folders, page canvas state, vector ink lines | `NotebookViewSet` (`/api/v1/notebooks`) |
| `apps.canvas` | `backend/apps/canvas` | Single-writer canvas sessions, stroke fencing, page finalization | `CanvasSessionViewSet`, `CanvasPageViewSet` (`/api/v1/canvas/*`) |
| `apps.documents` | `backend/apps/documents` | Canonical documents, pages, revisions, lines, digitized PDFs | `DocumentViewSet` (`/api/v1/documents`), `DigitizedDocumentViewSet` |
| `apps.ai_classroom` | `backend/apps/ai_classroom` | Enriched notes, blocks, citations, prompts, tags | `TagViewSet`, enrichment endpoints on `DocumentViewSet` |
| `apps.retrieval` | `backend/apps/retrieval` | Chunking, incremental indexing, dense pgvector + keyword RRF | `SearchView` (`/api/v1/search`), `NoteChunk` model |
| `apps.references` | `backend/apps/references` | Textbooks/reference PDFs, chunking, embeddings, shared retrieval | `ReferenceDocumentViewSet` (`/api/v1/references/`) |
| `apps.chat` | `backend/apps/chat` | Ask StudyAI multi-turn chat sessions, history, streaming | `ChatSessionViewSet` (`/api/v1/chat/sessions`) |
| `apps.questions` | `backend/apps/questions` | Question generation, storage, source chunk linking | `DocumentQuestionsViewSet` (`/api/v1/documents/{id}/questions`) |
| `apps.tests` | `backend/apps/tests` | Adaptive tests, attempts, mastery scoring service | `TestViewSet` (`/api/v1/tests`) |
| `apps.revision` | `backend/apps/revision` | Revision goals, plans, mastery overview | `RevisionOverviewView`, `RevisionGoalsView`, `RevisionPlansView` |
| `apps.jobs` | `backend/apps/jobs` | Durable queue state machine (OCR, index, enrich, pdf_render) | `JobViewSet` (`/api/v1/jobs/{id}`) |
| `apps.audit` | `backend/apps/audit` | System audit logs, provider call logs, daily backups | `AuditLogListView` (`/api/v1/audit`) |
| `apps.agents` | `backend/apps/agents` | Agentic AI orchestrator, tools, MCP integration | `AgentViewSet` (`/api/v1/chat/`, `/api/v1/tools/`, `/api/v1/mcp/`) |

### Model Inventory

| Model | Purpose | Profile Scoped? | Subject Scoped? | Cascade Behavior | Storage Dep. | AI Dep. | Status |
|---|---|---|---|---|---|---|---|
| `accounts.User` | Platform user identity | N/A | No | CASCADE to profiles, tokens | None | None | **LIVE VERIFIED** |
| `accounts.PasswordResetToken` | Password reset tokens | User FK | No | CASCADE on User delete | None | None | **BROKEN** (unmigrated) |
| `accounts.UserProfile` | Token & cost budget tracking | User FK | No | CASCADE on User delete | None | None | **LIVE VERIFIED** |
| `profiles.Profile` | Student workspace container | User FK | No | CASCADE to subjects, notes | None | None | **LIVE VERIFIED** |
| `subjects.Subject` | Course / topic scoping | Yes | Yes (Self) | CASCADE on Profile delete | None | None | **LIVE VERIFIED** |
| `notebooks.Notebook` | Folder / Notebook entity | Yes | Yes | CASCADE on Profile delete | None | None | **LIVE VERIFIED** |
| `notebooks.NotebookPage` | Page canvas state | Via Notebook | Via Notebook | CASCADE on Notebook delete | None | None | **IMPLEMENTED** |
| `notebooks.NotebookLine` | Vector ink stroke | Via Notebook | Via Notebook | CASCADE on Page delete | None | None | **IMPLEMENTED** |
| `canvas.CanvasSession` | Single-writer sheet session | Yes | Yes | CASCADE on Profile delete | None | None | **LIVE VERIFIED** |
| `canvas.CanvasPage` | Canvas session sheet page | Via Session | Via Session | CASCADE on Session delete | None | None | **LIVE VERIFIED** |
| `canvas.CanvasStroke` | Idempotent stroke record | Via Session | Via Session | CASCADE on Page delete | None | None | **LIVE VERIFIED** |
| `documents.Document` | Canonical note / document | Yes | Yes | CASCADE on Profile delete | None | None | **LIVE VERIFIED** |
| `documents.DocumentPage` | Page image & OCR status | Via Document | Via Document | CASCADE on Document delete | MinIO image | OCR | **LIVE VERIFIED** |
| `documents.DocumentPageRevision` | Immutable text revision | Via Document | Via Document | CASCADE on Page delete | None | None | **LIVE VERIFIED** |
| `documents.DocumentLine` | OCR text line & heading flag | Via Document | Via Document | CASCADE on Revision delete | None | None | **LIVE VERIFIED** |
| `documents.DigitizedDocument` | Rendered typed PDF artifact | Via Document | Via Document | CASCADE on Document delete | MinIO PDF | None | **IMPLEMENTED** |
| `ai_classroom.EnrichedNote` | LLM enrichment output | Via Document | Via Document | CASCADE on Document delete | None | LLM | **LIVE VERIFIED** |
| `ai_classroom.EnrichedNoteBlock` | Section block of enriched note | Via Document | Via Document | CASCADE on Note delete | None | None | **LIVE VERIFIED** |
| `ai_classroom.CitationBlock` | Source citation & verification | Via Document | Via Document | CASCADE on Block delete | None | Verifier | **LIVE VERIFIED** |
| `ai_classroom.PromptVersion` | Versioned prompt templates | No | No | Independent entity | None | None | **LIVE VERIFIED** |
| `ai_classroom.Tag` | Stable academic concept taxonomy | Via Subject | Yes | CASCADE on Subject delete | None | None | **IMPLEMENTED** |
| `ai_classroom.DocumentTag` | Note-to-tag assignment | Via Document | Via Document | CASCADE on Document/Tag delete | None | None | **IMPLEMENTED** |
| `ai_classroom.TagChangeLog` | Tag mutation audit log | Via Tag | Via Tag | SET_NULL on Tag delete | None | None | **IMPLEMENTED** |
| `retrieval.NoteChunk` | Source-layer retrieval chunk | Yes (Nullable) | Yes | CASCADE on Document delete | None | Embedding | **LIVE VERIFIED** |
| `questions.Question` | Practice question item | Via Document | Via Document | CASCADE on Document delete | None | LLM | **IMPLEMENTED** |
| `questions.QuestionTagLink` | Question-to-tag mapping | Via Question | Via Question | CASCADE on Question delete | None | None | **IMPLEMENTED** |
| `tests.TestInstance` | Test session instance | Yes | Yes | CASCADE on Profile delete | None | None | **IMPLEMENTED** |
| `tests.TestQuestion` | Test-to-question link | Via Test | Via Test | CASCADE on Test delete | None | None | **IMPLEMENTED** |
| `tests.TestAttempt` | Student answer attempt | Via Test | Via Test | CASCADE on Test delete | None | None | **IMPLEMENTED** |
| `tests.MasteryScore` | EMA mastery score per tag | Yes | Yes | CASCADE on Profile/Tag delete | None | None | **IMPLEMENTED** |
| `chat.ChatSession` | Ask StudyAI conversation thread | Yes | Yes | CASCADE on Profile delete | None | None | **LIVE VERIFIED** |
| `chat.ChatMessage` | Conversation turn message | Via Session | Via Session | CASCADE on Session delete | None | LLM | **LIVE VERIFIED** |
| `revision.RevisionGoal` | Student revision target date/goal | Yes | Yes | CASCADE on Profile delete | None | None | **IMPLEMENTED** |
| `references.ReferenceDocument` | Textbook / Reference PDF | Yes (Nullable) | Yes | CASCADE on Profile (or None) | MinIO PDF | None | **LIVE VERIFIED** |
| `references.ReferenceChunk` | Embedded reference chunk | Via Doc | Via Doc | CASCADE on Doc delete | None | Embedding | **LIVE VERIFIED** |
| `references.ReferenceBook` | Legacy curated book model | No | Yes | SET_NULL on Subject delete | None | None | **LEGACY** |
| `references.ReferenceBookChapter` | Legacy book chapter range | Via Book | Via Book | CASCADE on Book delete | None | None | **LEGACY** |
| `jobs.Job` | Durable async job queue item | Profile ID | No | SET_NULL on coalesced job | None | None | **LIVE VERIFIED** |
| `jobs.JobExecutionState` | Job execution checkpoints | Via Job | No | CASCADE on Job delete | None | None | **LIVE VERIFIED** |
| `audit.AuditLog` | Security & compliance audit log | User FK | No | SET_NULL on User delete | None | None | **LIVE VERIFIED** |
| `audit.ProviderCallLog` | AI inference cost/token log | No | No | Independent entity | None | None | **LIVE VERIFIED** |
| `agents.AgentExecutionLog` | Agent orchestrator execution trace | Yes | No | CASCADE on Profile delete | None | LLM | **BROKEN** |
| `agents.AgentPromptVersion` | Agent system prompt registry | No | No | Independent entity | None | None | **IMPLEMENTED** |

### Critical Architectural Defects Detected

1. **Unmigrated Model & Broken Password Reset:**
   - File: `backend/apps/accounts/models.py:40` (`PasswordResetToken`)
   - Issue: Model exists in `models.py`, but migration was never generated (`makemigrations --check` fails with exit code 1).
   - Impact: Database table `accounts_passwordresettoken` does not exist in PostgreSQL. In addition, `apps/accounts/views.py` lines 98 and 118 do `from apps.accounts.services import PasswordResetTokenService`, which throws `ImportError` because `apps/accounts/services/` lacks an `__init__.py`.
2. **Global Reference Document Deletion Vulnerability:**
   - File: `backend/apps/references/views.py:125-128`
   - Code:
     ```python
     if not instance.profile and not request.user.is_staff:
         # Only staff can delete platform global references
         pass  # or allow owner if created by them
     # Proceed to delete storage file and instance...
     ```
   - Impact: Any authenticated user can delete any global platform-wide textbook.
3. **Accidental `.first()` Profile Association:**
   - Occurrences:
     - `backend/apps/retrieval/retrieval.py:212`: `user_profile = Profile.objects.filter(user=user).first()`
     - `backend/apps/revision/views.py:24, 45, 60, 77`: `profile = Profile.objects.filter(user=request.user).first()`
     - `backend/apps/tests/views.py:73`: `profile = Profile.objects.filter(user=request.user).first()`
     - `backend/apps/agents/tools/base.py:73`: `profile = Profile.objects.filter(user=user).first()`
     - `backend/shared/authorization/services.py:61`: `profile = Profile.objects.filter(user=user).first()`
   - Impact: In multi-profile setups, background queries and endpoints select whichever profile PostgreSQL returns first, disregarding the user's active session profile.
4. **AgentViewSet Missing Import:**
   - File: `backend/apps/agents/views.py:60`
   - Issue: `user_message = ChatMessage.objects.create(...)` references `ChatMessage`, which is not imported in module globals (imported only locally inside an unrelated function at line 163).
   - Impact: `POST /api/v1/chat/` crashes immediately with `NameError`.
5. **Inoperative PostgreSQL RLS:**
   - Tables: 27 RLS tables have `relforcerowsecurity = false`.
   - Issue: Django connects as table owner `studyai`, exempting all queries from RLS policies. The planned restricted non-superuser role `studyai_app` does not exist.

---

## 6. Frontend Audit

### Route Inventory

| Route Path | Component | Backend API | State Store | Persistence | Status | Known Issue |
|---|---|---|---|---|---|---|
| `/login` | `LoginPage` | `POST /api/v1/auth/login` | `authStore` | `localStorage` | **LIVE VERIFIED** | None |
| `/register` | `RegisterPage` | `POST /api/v1/auth/register` | `authStore` | `localStorage` | **LIVE VERIFIED** | None |
| `/onboarding/profile` | `ProfileStep` | `POST /api/v1/profiles` | `authStore` | `localStorage` | **LIVE VERIFIED** | None |
| `/onboarding/module` | `ModuleStep` | `PATCH /api/v1/profiles/{id}` | `authStore` | `localStorage` | **LIVE VERIFIED** | None |
| `/onboarding/subjects`| `SubjectsStep` | `POST /api/v1/subjects` | `workspaceStore` | Backend DB | **LIVE VERIFIED** | None |
| `/` | `RootRedirect` | None | `workspaceStore` | None | **LIVE VERIFIED** | Redirects to subjects or onboarding |
| `/subjects` | `SubjectsPage` | `GET /api/v1/subjects` | `workspaceStore` | Backend DB | **LIVE VERIFIED** | None |
| `/subjects/:subjectId`| `SubjectWorkspace` | `GET /api/v1/documents`, `GET /api/v1/notebooks` | `workspaceStore` | Backend DB + IDB | **LIVE VERIFIED** | None |
| `/subjects/:subjectId/write` | `WritingPage` | `/api/v1/canvas/*` | `canvasStore` | IndexedDB + Backend | **LIVE VERIFIED** | Canvas sync & heartbeat |
| `/subjects/:subjectId/folders/:folderId` | `FolderDetailPage` | `GET /api/v1/notebooks/{id}` | `workspaceStore` | Backend DB + IDB | **LIVE VERIFIED** | Nested folders local only |
| `/subjects/:subjectId/notes/:noteId` | `NoteDetailPage` | `GET /api/v1/documents/{id}` | `workspaceStore` | Backend DB + MinIO | **LIVE VERIFIED** | Multi-view (OCR / Enriched) |
| `/subjects/:subjectId/tests` | `TestsPage` | `GET /api/v1/tests` | Component state | Backend DB | **IMPLEMENTED** | No browser E2E test |
| `/subjects/:subjectId/practice` | `PracticePage` | `GET /api/v1/documents/{id}/questions` | Component state | Backend DB | **IMPLEMENTED** | Aggregates per note |
| `/subjects/:subjectId/chat` | `ChatPage` | `/api/v1/chat/sessions/*` | Component state | Backend DB + sessionStorage | **LIVE VERIFIED** | Pseudo-streaming SSE |
| `/ai-classroom/chat` | `ChatPage` | `/api/v1/chat/sessions/*` | Component state | Backend DB + sessionStorage | **LIVE VERIFIED** | Global classroom chat |
| `/references` | `ReferenceLibraryPage` | `/api/v1/references/` | Component state | Backend DB + MinIO | **LIVE VERIFIED** | Polls status every 3s |
| `/subjects/:subjectId/references` | `ReferenceLibraryPage` | `/api/v1/references/?subject=...` | Component state | Backend DB + MinIO | **LIVE VERIFIED** | Filtered by subject |
| `/revision` | `Navigate` | None | None | None | **PLACEHOLDER** | Redirects to `/subjects` (No UI) |

### Frontend Seams & State Synchronization Issues

1. **Folder Hierarchy Seam:**
   - Seam: `frontend/src/state/workspaceStore.ts:112–130` and `frontend/src/services/api/notebooks.ts:19`
   - Details: The backend `Notebook` model has no `parent` foreign key. Subfolder tree nesting (`parentId`) exists only in the browser's IndexedDB. If the user clears local browser storage or switches computers, all nested folders revert to top-level root folders.
2. **Missing Sole-Profile Deletion Backend Guard:**
   - Seam: `frontend/src/components/layout/Sidebar.tsx:94–100`
   - Details: The frontend enforces `if (all.length <= 1) { toast.error(...); return; }`, but the backend `ProfileViewSet` will delete the last profile without restriction if invoked via raw API.
3. **Dead Revision Planner Navigation:**
   - Seam: `frontend/src/routes/index.tsx:189`
   - Details: `<Route path="/revision" element={<Navigate to="/subjects" replace />} />` leaves the backend revision planning service unreachable from the user interface.

---

## 7. AI Stack Audit

### Canonical Production Stack

- **Multimodal LLM / OCR:** `qwen3.5:4b` via Host Ollama (`/api/chat`)
- **Dense Embedding Model:** `Qwen/Qwen3-Embedding-0.6B` (1024 dimensions) via local `sentence-transformers`
- **Retrieval Infrastructure:** PostgreSQL 16 + `pgvector` Cosine Distance + PostgreSQL English `tsvector` + Reciprocal Rank Fusion (RRF)

### Model Search & Classification Matrix

| Search Term | Classification | Occurrences & Files Found | Analysis / Truth |
|---|---|---|---|
| `qwen3.5:4b` | **PRODUCTION** | `.env.example`, `.env`, `docker-compose.yml`, `providers/llm/qwen35.py` | Active canonical LLM and vision OCR provider |
| `Qwen/Qwen3-Embedding-0.6B` | **PRODUCTION** | `.env`, `providers/embeddings/local.py`, `apps/retrieval/models.py` | Active canonical 1024-dim embedding model |
| `all-MiniLM-L6-v2` | **ACTIVE (LEGACY DEPENDENCY)** | `apps/ai_classroom/gap_candidates_v2.py:47`, `providers/embeddings/local.py:60` | Hardcoded in `gap_candidates_v2` for semantic centrality; fallback default in `local.py` |
| `sentence-transformers` | **PRODUCTION** | `backend/requirements.txt`, `backend/Dockerfile`, `providers/embeddings/local.py` | Local PyTorch runtime executing embedding models |
| `Tesseract` | **CONFIG ONLY / TEST ONLY** | `backend/Dockerfile:12`, `providers/ocr/local.py` | Installed in image and tested in unit tests; production uses `qwen3.5:4b` vision OCR |
| `PaddleOCR` | **DEAD CODE / TEST ONLY** | `providers/ocr/local.py:146`, `providers/tests/test_paddleocr.py` | Library not installed in container; tests skipped |
| `llama3.1:8b` | **DOCUMENTATION ONLY** | `docs/phase_11/*`, `docs/phase_11_local_providers.md` | Legacy phase documentation; completely replaced in production by `qwen3.5:4b` |
| `mistral:7b` / `phi3:mini` | **DOCUMENTATION ONLY** | `docs/phase_11/operations/TROUBLESHOOTING.md` | Legacy troubleshooting suggestions |
| `gpt-4o-mini` | **DOCUMENTATION ONLY** | `docs/phase_11/setup/CREDENTIALS_AND_ACCESS.md` | Obsolete cloud reference; StudyAI is 100% local |
| `mock` | **TEST ONLY** | `backend/config/settings/test.py:35`, `providers/llm/mock.py` | Active in unit/API test suites to ensure deterministic, fast test runs |

---

## 8. Retrieval / RAG Audit

### Pipeline Data Flow

```
User Query
  │
  ├──► Query Text ──► sentence-transformers (Qwen/Qwen3-Embedding-0.6B) ──► 1024-d Vector
  │                     │
  │                     ▼
  │                   PostgreSQL pgvector (CosineDistance on NoteChunk.embedding & ReferenceChunk.embedding)
  │                     │
  │                     ▼
  │                   Top-N Dense Candidates (dense_rank = 1 / (60 + rank))
  │
  └──► Query Text ──► PostgreSQL to_tsquery / SearchQuery('english')
                        │
                        ▼
                      GIN Index on tsvector_content (SearchRank)
                        │
                        ▼
                      Top-N Keyword Candidates (keyword_rank = 1 / (60 + rank))
  │
  ▼
Reciprocal Rank Fusion (RRF: rrf_score = dense_rank + keyword_rank)
  │
  ▼
Authorization & Status Filtering (stale=False, status=READY, Profile & Subject Scoping)
  │
  ▼
Top-K Evidence Items ──► LLM Context Prompt (qwen3.5:4b)
```

### Retrieval Implementation Comparison

| Metric / Attribute | Chatbot Retrieval (`RetrievalService.search`) | Enrichment Retrieval (`retrieve_chunks_node`) | Reference Retrieval (`retrieve_reference_context`) |
|---|---|---|---|
| **Underlying Engine** | `RetrievalService.search` + `retrieve_reference_context` | `retrieve_reference_context` + NoteChunks | `retrieve_reference_context` |
| **Vector Model** | `Qwen/Qwen3-Embedding-0.6B` (1024-dim) | `Qwen/Qwen3-Embedding-0.6B` (1024-dim) | `Qwen/Qwen3-Embedding-0.6B` (1024-dim) |
| **Keyword Engine** | PostgreSQL GIN `tsvector` (`SearchRank`) | Direct DB NoteChunk query + Reference chunks | PostgreSQL GIN `tsvector` (`SearchRank`) |
| **Status Gate** | `stale=False`, `status=ready` | `stale=False`, `status=READY` | `status=READY` |
| **Profile Scoping** | **BROKEN:** Uses `Profile.objects.filter(user=user).first()` | **CORRECT:** Scoped to `document.profile` | **CORRECT:** Scoped to supplied `profile` instance |
| **Subject Scoping** | Enforced when subject passed | Enforced to `document.subject` | Enforced when subject passed |
| **Provenance Returned** | `chunk_id`, `document_id`, `page_start`, `page_end`, `title` | `chunk_id`, `document_id`, `page_start`, `page_end`, `chapter` | Full: `chunk_id`, `document_id`, `source_title`, `page`, `chapter` |

*Finding:* While `retrieve_reference_context` is cleanly shared, `RetrievalService.search` wraps it with `user_profile = Profile.objects.filter(user=user).first()`, creating a profile leakage bug when invoked without explicit profile scoping.

---

## 9. Enrichment Pipeline Audit

### LangGraph Topology

```
                  ┌──────────────┐
                  │   retrieve   │ (retrieve_chunks_node)
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │    draft     │ (draft_node)
                  └──────┬───────┘
                         │
                         ▼
             ┌───────────────────────┐
             │ candidate_generation  │ (candidate_generation_node)
             └───────────┬───────────┘
                         │
                         ▼
             ┌───────────────────────┐
             │  coverage_comparison  │ (coverage_comparison_node)
             └───────────┬───────────┘
                         │
                         ▼
             ┌───────────────────────┐
             │ candidate_validation  │ (candidate_validation_node)
             └───────────┬───────────┘
                         │
           [gaps found?] │ [no gaps]
           ┌─────────────┴─────────────┐
           ▼                           │
    ┌──────────────┐                   │
    │   gap_fill   │                   │
    └──────┬───────┘                   │
           │                           │
           └─────────────┬─────────────┘
                         ▼
              ┌─────────────────────┐
              │   citation_stitch   │ (citation_stitch_node)
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │evidence_verification│ (_run_verification -> verification_graph)
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │    format_output    │ (format_output_node)
              └──────────┬──────────┘
                         │
                         ▼
                        END
```

### Component Status Audit

| Component | File / Location | Status | Rationale |
|---|---|---|---|
| `retrieve_chunks_node` | `apps/ai_classroom/enrichment_nodes.py:145` | **ACTIVE** | Loads user note chunks and calls `retrieve_reference_context` |
| `draft_node` | `apps/ai_classroom/enrichment_nodes.py:274` | **ACTIVE** | Drafts enriched structure using prompt `enrichment_draft:v1` |
| `candidate_generation_node` | `apps/ai_classroom/enrichment_nodes.py:359` | **ACTIVE (LEGACY)** | Generates candidates via legacy `gap_candidates.py` using `DOMAIN_CONCEPTS` |
| `coverage_comparison_node` | `apps/ai_classroom/enrichment_nodes.py:384` | **ACTIVE (LEGACY)** | Compares coverage via legacy `gap_candidates.py` |
| `candidate_validation_node`| `apps/ai_classroom/enrichment_nodes.py:439` | **ACTIVE** | Invokes `validate_candidates_batch` with `qwen3.5:4b` |
| `gap_candidates_v2.py` | `apps/ai_classroom/gap_candidates_v2.py` | **UNUSED IN PROD** | Built to replace `DOMAIN_CONCEPTS`; executed only in eval test suite |
| `gap_detection_node` | `apps/ai_classroom/enrichment_nodes.py:318` | **DEAD CODE** | Monolithic gap detection node; imported in graph file but excluded from edges |
| `gap_fill_node` | `apps/ai_classroom/enrichment_nodes.py:500` | **ACTIVE** | Fills validated gaps using prompt `gap_filling:v1` |
| `citation_stitch_node` | `apps/ai_classroom/enrichment_nodes.py:539` | **ACTIVE** | Binds source references to enriched note blocks |
| `_run_verification` | `ai/langgraph/graphs/enrichment_graph.py:23` | **ACTIVE** | Runs sub-graph `verification_graph` to assign citation scores |
| `format_output_node` | `apps/ai_classroom/enrichment_nodes.py:586` | **ACTIVE** | Formats state into persisted schema |

---

## 10. Chat Audit (Ask StudyAI)

### Message Flow & Lifecycle

```
Frontend Composer (ChatPage.tsx)
  │
  ├──► POST /api/v1/chat/sessions/{id}/messages/stream
  │      │
  │      ▼
  │    ChatSessionViewSet.stream_message
  │      │
  │      ├──► 1. Assert Profile AI Budget (assert_within_budget)
  │      ├──► 2. Persist User Message atomically (ChatMessage.Role.USER)
  │      ├──► 3. Generate Thread Title if new thread (persisted & emitted via SSE 'title')
  │      ├──► 4. Retrieve Bounded History (20 messages / 12,000 chars)
  │      │
  │      ▼
  │    LangGraph Chat Workflow (ai/langgraph/graphs/chat_graph.py)
  │      │
  │      ├──► route_query_node (classifies conversational / date_time / material / general_knowledge)
  │      ├──► retrieve_node (RetrievalService.search -> NoteChunks + ReferenceChunks)
  │      ├──► generate_node (qwen3.5:4b via Ollama, synchronous prompt execution)
  │      └──► verification_node (EvidenceVerifier verification)
  │      │
  │      ▼
  │    Synchronous Answer Generated in Memory
  │      │
  │      ├──► Pseudo-Streaming Token Loop (_tokenize(answer) with time.sleep(0.025))
  │      │      └──► Yield SSE: event: token, data: {"delta": word}
  │      ├──► Yield SSE: event: citations, data: [...]
  │      ├──► Persist Assistant Message atomically (ChatMessage.Role.ASSISTANT)
  │      └──► Yield SSE: event: done, data: {"message_id": ...}
```

### Chat Findings

1. **Pseudo-Streaming:** SSE streaming is simulated by tokenizing already-completed generation output with `time.sleep()`. The LLM inference call is entirely synchronous.
2. **Context Bounds:** Strict bounding to 20 messages and 12,000 characters prevents prompt overflow while maintaining recent multi-turn context.
3. **Session & Profile Isolation:** Enforced at the SQL level in `ChatSession.objects.filter(profile__user=request.user)`.
4. **Current Message Duplication Guard:** Current user message is excluded from conversation context history retrieval (`exclude_msg_id=user_msg.pk`) to prevent duplicating the prompt.

---

## 11. Reference Library Audit

### Ingestion Safety & Textbook Scalability

`ReferenceDocument` ingestion is executed via Celery background task `ingest_reference_document_task`:

```python
# apps/references/ingestion.py:56-63
pdf_bytes = storage.read_bytes(doc.file_path)
pages = extract_pdf_pages(pdf_bytes, request_id=f"ref_ingest:{doc_id}", ocr_fallback=True)
```

### Risks for 500+ Page Textbooks

1. **Memory Exhaustion (High Risk):**
   `storage.read_bytes(doc.file_path)` buffers the entire raw PDF into worker memory, followed by `io.BytesIO` and `pypdf.PdfReader`. A 400MB scanned textbook consumes over 1GB of worker heap space.
2. **Sequential Vision OCR Bottleneck (Critical Risk):**
   In `extract_pdf_pages`, if a textbook consists of scanned pages with low text density, the worker enters a synchronous page-by-page OCR loop calling `qwen3.5:4b` vision. At ~4 seconds per page, a 500-page scanned textbook will run for **over 30 minutes in a single Celery task**, risking worker timeouts and broker deadlocks.
3. **Stuck Processing State (Medium Risk):**
   If the worker process is killed or crashes mid-ingestion, the `ReferenceDocument` remains permanently stuck in `status = PROCESSING` because there is no task heartbeat or reaper mechanism for reference ingestion.

---

## 12. Data Consistency Audit

| Data Entity | Primary Source of Truth | Secondary / Cache Copies | Consistency Seam / Hazard |
|---|---|---|---|
| **Note Title** | `documents.Document.title` | IndexedDB `NoteMeta.title` | Reconciled on workspace load; server wins if set |
| **Folder Assignment** | `documents.Document.notebook_id` | IndexedDB `NoteMeta.folderId` | Remote notebook assignment mapped on load |
| **Folder Hierarchy** | IndexedDB `FolderNode.parentId` | None (Local only) | **Inconsistency:** Subfolder nesting lost on new devices/browsers |
| **Active Profile** | Browser `localStorage` | Backend session | Verified against backend; falls back to first profile if omitted |
| **Strokes / Ink** | PostgreSQL `canvas_canvasstroke` | IndexedDB `strokes` | Offline outbox queues strokes; synced via idempotency keys |
| **Enriched Note** | PostgreSQL `ai_classroom_enrichednote` | None | Content-addressed by document revision content hash |
| **Reference Status**| PostgreSQL `references_referencedocument.status` | Component state | Frontend polls every 3 seconds while PENDING/PROCESSING |

---

## 13. Celery & Asynchronous Task Audit

### Complete Celery Task Inventory

| Task Name | Trigger | Inputs | Outputs | Retries | Idempotency Key | DB State | AI / Storage Dependency |
|---|---|---|---|---|---|---|---|
| `process_job_task` | `dispatch_job(job)` | `job_id` (UUID) | None | 3 retries (10s backoff) | `job.idempotency_key` | Updates `Job.status` (RUNNING -> SUCCEEDED / FAILED) | MinIO (read/write), LLM / OCR |
| `reap_stuck_jobs_task` | Celery Beat (every 5m) | None | Reaped count | None | Periodic scan | Requeues stuck RUNNING jobs | Database only |
| `promote_retries_task` | Celery Beat (every 2m) | None | Promoted count | None | Periodic scan | Promotes due FAILED_RETRYABLE to QUEUED | Database only |
| `daily_backup` | Celery Beat (02:30 UTC) | None | Backup file | 2 retries (300s backoff) | Once per day | Writes `/backups/*.dump` | **BROKEN:** `pg_dump` missing from image |
| `reset_monthly_budgets`| Celery Beat (1st of month) | None | Reset count | None | Once per month | Resets token/cost counters on `UserProfile` | Database only |
| `ingest_reference_document_task` | `ReferenceDocumentViewSet.create` | `ref_doc_id` (UUID) | Metrics dict | 2 retries (15s backoff) | Document status guard | Sets status to PROCESSING -> READY / FAILED | MinIO (read), Embeddings (`Qwen3-Embedding`) |

---

## 14. Storage Audit

### Durability & Lifecycle Matrix

| Storage Layer | Data Stored | Durability Level | Cleanup / Deletion Path | Orphan Risk |
|---|---|---|---|---|
| **PostgreSQL** | Users, Profiles, Subjects, Folders, Notes, Revisions, Lines, Tags, Tests, Chats | **DURABLE** (Source of truth) | Foreign key `ON DELETE CASCADE` or `SET_NULL` | Low |
| **pgvector** | NoteChunk embeddings (1024-d), ReferenceChunk embeddings (1024-d) | **DURABLE** | Cascade-deleted with owning Document or ReferenceDocument | Low |
| **MinIO (S3)** | Handwritten note page images (`pages/{id}.jpg`), NoteSpace PDFs (`{profile}/{doc}/{hash}.pdf`), Reference PDFs (`references/{id}/{name}`) | **DURABLE** (Object store) | Cleaned up explicitly in `DocumentViewSet.perform_destroy` and `ReferenceDocumentViewSet.destroy` | **Medium:** Direct DB record deletion leaves MinIO objects orphaned |
| **IndexedDB** | Vector ink strokes, local folder hierarchy, note metadata cache | **EPHEMERAL / CLIENT CACHE** | Cleared via browser data purge or note deletion | Local-only hierarchy data lost on cache clear |

---

## 15. Security Audit

### Conceptual Isolation Tests

```
                     ISOLATION BOUNDARY CHECKS
                     
  [Profile A] ────────── X ──────────► [Profile B]       ENFORCED (SQL profile filter)
  [Profile A Note] ───── X ──────────► [Profile B Note]  ENFORCED (SQL document filter)
  [Profile A Chat] ───── X ──────────► [Profile B Chat]  ENFORCED (SQL chat session filter)
  [Profile A Ref]  ───── X ──────────► [Profile B Ref]   ENFORCED (Private references isolated)
  [Global Ref]     ──────────────────► [All Profiles]    READ: INTENDED / WRITE: VULNERABLE
```

### Security Findings & Vulnerability Details

1. **Arbitrary Deletion of Platform Reference Documents:**
   - Location: `backend/apps/references/views.py:125-128`
   - Severity: **HIGH**
   - Vulnerability:
     ```python
     if not instance.profile and not request.user.is_staff:
         pass  # Authorization check bypassed!
     instance.delete()
     ```
   - Remediation: Return `Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)`.
2. **RLS Database Bypass in Production:**
   - Location: Docker database configuration and PostgreSQL table settings.
   - Severity: **HIGH**
   - Vulnerability: `relrowsecurity` is enabled, but `relforcerowsecurity` is false. Application connects as database superuser/table-owner `studyai`. PostgreSQL bypasses RLS policies entirely for the table owner. Application-layer security currently provides the sole isolation boundary.
3. **Sole-Profile Deletion via Direct API:**
   - Location: `backend/apps/profiles/views.py:ProfileViewSet`
   - Severity: **MEDIUM**
   - Vulnerability: Backend permits deleting the only profile, creating unrecoverable user account state where subsequent queries fail with `Profile.DoesNotExist`.

---

## 16. Test Coverage Audit

### Master Test Suite Inventory

| Test Tier | Test Count | Location | Execution Tool | Status |
|---|---|---|---|---|
| **Backend Unit Tests** | 173 | `backend/tests/unit/` | `pytest --ds=config.settings.test` | **173 passed, 2 skipped** |
| **Backend API Tests** | 163 | `backend/tests/api/` | `pytest --ds=config.settings.test` | **163 passed, 1 skipped** |
| **Provider Tests** | 134 | `backend/providers/tests/` | `pytest --ds=config.settings.test` | **130 passed, 4 skipped** |
| **App Unit Tests** | 66 | `backend/apps/*/tests/` | `pytest --ds=config.settings.test` | **66 passed, 0 skipped** |
| **Evaluation Suite** | 20 | `backend/tests/evaluation/` | `pytest --ds=config.settings.test` | **20 passed, 0 skipped** |
| **Frontend Unit / Store** | 73 | `frontend/tests/*.test.ts` | `vitest run` | **73 passed, 0 failed** |
| **Browser E2E Tests** | 6 suites | `frontend/tests/e2e/*.mjs` | Puppeteer against live Docker stack | **All verified passing** |

### Coverage Gap Analysis

| Feature Area | Unit Tests | API Tests | Browser E2E | Live AI Execution | Overall Quality |
|---|---|---|---|---|---|
| **Auth & Profiles** | High | High | High (`phase10c`) | N/A | **Excellent** |
| **CRUD (Subjects, Folders, Notes)**| High | High | High (`phase10c`) | N/A | **Excellent** |
| **Canvas Drawing & Fencing** | High | High | Low | N/A | **Good** (E2E lacks canvas stroke UI) |
| **NoteSpace PDF Generation** | High | High | None | Low | **Moderate** (No browser E2E test) |
| **Handwritten OCR Ingestion** | High | High | High (`phase9c`) | High (`qwen3.5:4b`) | **Excellent** |
| **Enrichment & Citations** | High | High | High (`phase11_1`)| High (`qwen3.5:4b`) | **Excellent** |
| **Reference Library Ingestion** | High | High | High (`phase11`) | High (`qwen3.5:4b`) | **Excellent** |
| **Ask StudyAI Chat** | High | High | High (`phase10d`) | High (`qwen3.5:4b`) | **Excellent** |
| **Adaptive Tests & Mastery** | High | High | None | Low | **Moderate** (No browser E2E test) |
| **Password Reset** | None | Low | None | None | **Critical Gap** (Code broken) |
| **Revision Planner** | High | High | None | Low | **Moderate** (No frontend UI) |

---

## 17. Performance Audit

### Identified Performance Hazards

| Risk Area | Severity | File / Location | Description & Impact |
|---|---|---|---|
| **Textbook In-Memory Loading** | **CRITICAL** | `apps/references/ingestion.py:56` | `storage.read_bytes()` reads complete 500MB+ PDF files directly into worker RAM. |
| **Sequential Vision OCR Loop** | **CRITICAL** | `apps/references/extraction.py:73–94` | Scanned pages are OCR'd sequentially in the worker process. 500 pages can block worker for 30+ minutes. |
| **Sequential Candidate LLM Calls** | **HIGH** | `apps/ai_classroom/candidate_validation.py:316` | `validate_candidates_batch` invokes Qwen sequentially in a loop for each candidate. |
| **Artificial Stream Sleep Delay** | **MEDIUM** | `apps/chat/services.py:321` | Synchronously waits for full completion, then loops with `time.sleep(0.025)` per word. |
| **N+1 Query on Note Detail** | **LOW** | `apps/documents/views.py:180` | Document detail queries pages without prefetching revisions in some listing paths. |

---

## 18. Configuration Audit

### Configuration Comparison (`.env` vs `docker-compose.yml` vs Settings)

| Setting Name | `.env` Value | Docker Compose Default | Production Requirement | Mismatch / Finding |
|---|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | `config.settings.prod` | `config.settings.prod` | Worker & API inherit prod in Compose |
| `POSTGRES_USER` | `studyai` | `studyai` | `studyai_app` (for RLS) | Connects as table owner, disabling RLS |
| `STORAGE_BACKEND` | `minio` | `minio` | `minio` / `s3` | MinIO configured cleanly |
| `LLM_PROVIDER` | `ollama` | `ollama` | `ollama` | Uses host Ollama |
| `LLM_MODEL` | `qwen3.5:4b` | `qwen3.5:4b` | `qwen3.5:4b` | Aligned with canonical stack |
| `LLM_DISABLE_FALLBACK` | `1` | `1` | `1` | Disables silent fallback to mock |
| `EMBEDDING_PROVIDER` | `sentence_transformers` | `sentence_transformers` | `sentence_transformers` | Aligned with canonical stack |
| `EMBEDDING_MODEL_NAME` | `Qwen/Qwen3-Embedding-0.6B` | `Qwen/Qwen3-Embedding-0.6B` | `Qwen/Qwen3-Embedding-0.6B` | Aligned (1024 dimensions) |
| `CELERY_BEAT_ENABLED` | `1` | `1` | `1` | Separate beat container runs |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `http://host.docker.internal:11434` | Host Ollama URL | Handled via Docker host bridge |

---

## 19. Documentation Drift Audit

| Document | Statement / Claim | Code / Production Reality | Drift Status |
|---|---|---|---|
| `StudyAI_app_architecture_v4_1_full.md` | "Database RLS is the foundational boundary layer." | Tables have `relforcerowsecurity=false`; user connects as superuser owner. | **Severe Drift** |
| `docs/phase_11/operations/TROUBLESHOOTING.md` | Models referenced: `llama3.1:8b`, `mistral:7b`, `phi3:mini`. | Canonical production stack uses strictly `qwen3.5:4b`. | **Historical Drift** |
| `docs/phase_11/setup/ENVIRONMENT_AND_SECRETS.md` | `EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2` | Target production stack is `Qwen/Qwen3-Embedding-0.6B` (1024 dims). | **Historical Drift** |
| `docs/product/phase11_reference_library.md` | "all-MiniLM-L6-v2 is strictly superseded by Qwen/Qwen3-Embedding-0.6B across all reference retrieval." | `apps/ai_classroom/gap_candidates_v2.py:47` still hardcodes `all-MiniLM-L6-v2`. | **Active Drift** |
| `README.md` | Fully nested folders supported in workspace. | Backend `Notebook` model is flat; subfolder hierarchy exists only in IndexedDB. | **Feature Seam Drift** |
| `StudyAI_app_architecture_v4_1_full.md:58` | Revision Planner available as dedicated module. | Route `/revision` redirects to `/subjects` with no user-facing screen. | **Unimplemented UI Drift** |

---

## 20. Product Completeness Audit

### Core MVP (What the student can currently do end-to-end)

1. Register, log in, create and switch profiles between NoteSpace and AI Classroom.
2. Create, rename, and organize academic subjects.
3. Draw notes on canvas with pen, highlighter, and eraser; strokes autosave locally and sync.
4. Upload handwritten note images or PDFs, which are transcribed by `qwen3.5:4b` OCR.
5. Enrich notes with AI Classroom, generating structured conceptual sections.
6. Upload textbooks and reference PDFs to Reference Library, extracting and indexing chunks into pgvector.
7. Note enrichment automatically pulls and displays grounded textbook reference citations.
8. Ask StudyAI multi-turn questions grounded in uploaded student notes and reference books.
9. Perform CRUD operations (rename, move, delete) on notes, folders, subjects, and profiles.

### Implemented but Incomplete

1. **Folder Hierarchy:** Flat backend schema leaves nested folders vulnerable to browser cache clearance.
2. **Chat Streaming:** Wire format emits SSE events, but inference is non-streaming and simulates tokens via sleep.
3. **Sole-Profile Guard:** Enforced in React UI, missing on Django endpoint.

### Planned but Not Implemented (Spec Only)

1. Multi-user document sharing and collaborative review.
2. Real-time WebSocket ink broadcast.
3. User-facing Revision Planner dashboard.

### Technical Debt

1. Unused `gap_candidates_v2.py` and active legacy `DOMAIN_CONCEPTS` in `gap_candidates.py`.
2. Dead `gap_detection_node` in `apps/ai_classroom/enrichment_nodes.py`.
3. Broken `apps/agents` endpoints sitting on root `api/v1/chat/`.
4. Accidental `.first()` queries across multiple services.

---

## 21. Master Priority Matrix

| Area | Feature / Finding | Status | Evidence | Missing Work | Priority |
|---|---|---|---|---|---|
| **Security** | Global Reference Deletion Vulnerability | **G. BROKEN** | `apps/references/views.py:125-128` | Replace `pass` with `403 Forbidden` for non-staff users | **P0** |
| **Security** | Inoperative PostgreSQL RLS | **G. BROKEN** | `relrowsecurity=t`, `relforcerowsecurity=f` | Create `studyai_app` role, enable `FORCE ROW LEVEL SECURITY` | **P0** |
| **Auth** | Password Reset Service & Migration | **G. BROKEN** | `apps/accounts/views.py:98`, `makemigrations` | Add `__init__.py` to `services/`, run migration for token table | **P0** |
| **Agents** | AgentViewSet NameError on `ChatMessage` | **G. BROKEN** | `apps/agents/views.py:60` | Add top-level import `from apps.chat.models import ChatMessage` | **P0** |
| **Reliability** | Daily Backup Celery Task Missing `pg_dump`| **G. BROKEN** | `apps/audit/tasks.py:25`, Dockerfile | Install `postgresql-client` in `backend/Dockerfile` | **P1** |
| **Profiles** | Backend Sole-Profile Deletion Guard | **C. PARTIAL** | `apps/profiles/views.py:ProfileViewSet` | Add `perform_destroy` check rejecting deletion of sole profile | **P1** |
| **Data Scoping**| Eliminate `.first()` Profile Shortcuts | **C. PARTIAL** | `retrieval.py:212`, `revision/views.py:24` | Pass active profile explicitly from request headers / session | **P1** |
| **AI Pipeline** | Wire `gap_candidates_v2` into Enrichment | **C. PARTIAL** | `apps/ai_classroom/enrichment_nodes.py:361` | Switch candidate generation node from v1 to `gap_candidates_v2` | **P1** |
| **Performance** | Textbook Streaming & Ingestion Safety | **C. PARTIAL** | `apps/references/extraction.py:73` | Process pages in streamed batches with per-task progress heartbeats | **P1** |
| **Data Integrity**| Persistent Folder Hierarchy | **C. PARTIAL** | `apps/notebooks/models.py:Notebook` | Add `parent = ForeignKey('self', ...)` to `Notebook` model | **P2** |
| **Chat** | Real Token-Level LLM Streaming | **C. PARTIAL** | `apps/chat/services.py:289` | Connect Ollama stream chunks directly to SSE generator | **P2** |
| **UI** | Revision Planner Dashboard | **D. DEAD** | `frontend/src/routes/index.tsx:189` | Build frontend screen for `apps.revision` endpoints | **P2** |
| **Tech Debt** | Remove Dead `gap_detection_node` | **D. DEAD** | `apps/ai_classroom/enrichment_nodes.py:318` | Clean up dead node function and imports | **P3** |

---

## 22. Actual Current Product Flow

### Flow 1: Note Ingestion & Enrichment

```
User (Browser)
  │
  ▼
Authentication (JWT Bearer Token)
  │
  ▼
Active Profile Scoping (X-Active-Profile Header)
  │
  ▼
Subject Workspace Selection (/subjects/:id)
  │
  ▼
Note Upload (Image/PDF via POST /api/v1/documents)  [LIVE]
  │
  ▼
MinIO Object Storage (pages/{id}.jpg stored)         [LIVE]
  │
  ▼
Celery Worker OCR Job (qwen3.5:4b Multimodal Vision) [LIVE]
  │
  ▼
DocumentPageRevision & DocumentLines Created         [LIVE]
  │
  ▼
Incremental Chunking (NoteChunk rows created)        [LIVE]
  │
  ▼
Dense Embeddings Generated (Qwen/Qwen3-Embedding-0.6B) [LIVE]
  │
  ▼
User Triggers Enrich (POST /api/v1/documents/:id/enrich) [LIVE]
  │
  ▼
Hybrid Retrieval (NoteChunks + ReferenceChunks via RRF) [LIVE]
  │
  ▼
LangGraph Enrichment (qwen3.5:4b Structured Generation) [LIVE]
  │
  ▼
Candidate Gap Validation (Sequential Qwen Verification) [PARTIAL - v1 dictionaries]
  │
  ▼
Citation Stitching & Verification Graph             [LIVE]
  │
  ▼
PostgreSQL Persistence (EnrichedNote & Blocks)       [LIVE]
  │
  ▼
UI Rendering (EnrichedView with Interactive Citations) [LIVE]
```

### Flow 2: Ask StudyAI Interactive Chat

```
User (ChatPage.tsx)
  │
  ▼
Chat Session Active / Created (/chat/sessions/:id)   [LIVE]
  │
  ▼
User Submits Question (POST /messages/stream)        [LIVE]
  │
  ▼
Atomic User Message Persistence                      [LIVE]
  │
  ▼
Bounded History Retrieval (Max 20 msgs / 12,000 chars) [LIVE]
  │
  ▼
Hybrid Note & Reference Retrieval (RRF k=60)         [LIVE - Leaks on .first()]
  │
  ▼
Synchronous LLM Answer Generation (qwen3.5:4b)       [LIVE]
  │
  ▼
Artificial Token Delay Loop (time.sleep 0.025s)      [PARTIAL - Simulated stream]
  │
  ▼
SSE Event Delivery (token, citations, done)          [LIVE]
  │
  ▼
Atomic Assistant Message Persistence                 [LIVE]
```

---

## 23. Final Recommendations

### A. What is Already Solid
- **Core MVP User Flow:** Authentication, profile switching, canvas autosave, handwriting OCR via `qwen3.5:4b`, and note enrichment function reliably.
- **Hybrid RAG Pipeline:** Dense pgvector search combined with GIN-indexed keyword search via Reciprocal Rank Fusion provides high-quality retrieval grounding.
- **Reference Library Architecture:** First-class reference documents with chapter/section extraction, chunking, and citation display.
- **Regression Test Coverage:** 559 passing backend tests and 73 passing frontend tests prove existing foundational interfaces are stable.

### B. What is Partially Implemented
- **Folder Nesting:** Works in the browser via IndexedDB, but lacks backend relational storage (`Notebook.parent`).
- **Chat Streaming:** Emits SSE events, but generation is synchronous and pseudo-streamed.
- **Gap Detection Pipeline:** Runs active candidate comparison, but remains tied to legacy dictionaries rather than `gap_candidates_v2`.

### C. What is Missing
- **User-Facing Revision Planner:** Endpoints and LangGraph scheduling exist on the backend, but the frontend lacks any UI.
- **Sole-Profile Backend Guard:** API allows deleting the user's only profile.
- **Docker RLS Configuration:** Superuser table ownership bypasses PostgreSQL row security.

### D. What is Broken
- **Password Reset Endpoints:** Crashes on missing service import and unmigrated table.
- **Nightly Backup Job:** Fails every night due to missing `pg_dump` binary.
- **Global Reference Document Security:** Non-staff users can delete global textbooks due to an authorization `pass`.
- **Agentic Chat View:** Crashes on unimported `ChatMessage`.

### E. What Should NOT Be Built Yet
- **Do NOT build multi-user collaboration / real-time WebSockets:** The single-writer canvas fencing model is stable and works well; premature collaborative editing will introduce concurrency debt.
- **Do NOT add third-party cloud LLM providers:** The local `qwen3.5:4b` + `Qwen/Qwen3-Embedding-0.6B` stack is self-contained, private, and deterministic.

### F. Technical Debt Worth Cleaning
- Unify candidate generation by removing `apps/ai_classroom/gap_candidates.py` (v1) and directing the pipeline through `gap_candidates_v2.py`.
- Remove dead `gap_detection_node` in `enrichment_nodes.py`.
- Fix `.first()` profile shortcuts across retrieval, revision, tests, and authorization services.

### G. Highest-Priority Top 10 Actions

1. **[P0 - Security] Fix Global Reference Deletion Bypass:** In `apps/references/views.py:125-128`, replace `pass` with `return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)`.
2. **[P0 - Security] Enable PostgreSQL RLS Enforcement:** Add `studyai_app` restricted user in `docker-compose.yml`, grant table permissions, and execute `ALTER TABLE ... FORCE ROW LEVEL SECURITY` across all 27 tenant tables.
3. **[P0 - Bugfix] Fix Password Reset Flow:** Add `backend/apps/accounts/services/__init__.py` exporting `PasswordResetTokenService`, generate migration `0003_passwordresettoken.py`, and run `migrate`.
4. **[P0 - Bugfix] Fix AgentViewSet Import:** Add `from apps.chat.models import ChatMessage` at the top of `backend/apps/agents/views.py`.
5. **[P1 - Reliability] Install `postgresql-client` in Dockerfile:** Add `postgresql-client` to `backend/Dockerfile` so Celery beat `daily_backup` can execute `pg_dump`.
6. **[P1 - Integrity] Add Backend Sole-Profile Deletion Guard:** In `apps/profiles/views.py:ProfileViewSet.perform_destroy`, verify user has at least 2 profiles before permitting deletion.
7. **[P1 - Isolation] Remove `.first()` Profile Association:** Update `apps/retrieval/retrieval.py:212` and `apps/revision/views.py` to use `request.profile` or session profile rather than `Profile.objects.filter(user=user).first()`.
8. **[P1 - Architecture] Wire `gap_candidates_v2` into Enrichment:** Point `candidate_generation_node` in `apps/ai_classroom/enrichment_nodes.py` to `gap_candidates_v2.py` to eliminate hardcoded `DOMAIN_CONCEPTS`.
9. **[P1 - Performance] Stream Reference PDF Extraction:** Modify `apps/references/extraction.py` to process large textbooks in page chunks rather than reading entire 500MB+ files into memory at once.
10. **[P2 - Integrity] Persist Folder Hierarchy in Backend:** Add `parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)` to `apps/notebooks/models.py:Notebook` and update `NotebookSerializer`.

---

FULL SYSTEM AUDIT COMPLETE
