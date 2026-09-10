# Final Report: Commit Series Analysis (G10–G15, G5 Validation & Infrastructure Fixes)

**Branch:** `fix/RLS`
**Commit range:** `d2960ec` … `8401125` (5 commits by @Palakds)
**Author:** Palakds
**Date of analysis:** 2026-09-11

---

## Executive Summary

Five commits were made in rapid succession on the `fix/RLS` branch. They follow an
**add-then-remove cycle**: validation/verification scripts for G10, G11, G12, and G15
were added in the first two commits, then removed as obsolete in the third. The
remaining two commits address code-quality refactors (redundant imports, transaction
atomicity) and a database security improvement (PostgreSQL application password).

| # | Commit | Type | Key outcome |
|---|--------|------|-------------|
| 1 | `d2960ec` | feat | Add G10/G11/G12/G15 validation scripts + sanitization module |
| 2 | `bace85d` | fix  | Add `verify_g5.py` and `verify_g11.py` enrichment checks |
| 3 | `e9923a8` | refactor/chore | **Remove** all validation scripts; clean up imports |
| 4 | `7e60689` | refactor | Remove redundant `Optional` imports; atomic chat message persistence |
| 5 | `8401125` | feat | PostgreSQL app password support; DB check scripts |

---

## Timeline & Detailed Breakdown

### 1. `d2960ec` — feat: add new validation scripts for G10, G11, G12, and G15 checks

**Files added (6 new):**
- `backend/check_g10.py`
- `backend/check_g11.py`
- `backend/check_g12.py`
- `backend/check_g15.py`
- `backend/read_prompts.py`
- `backend/shared/sanitization.py`

**Files modified (4):**
- `backend/apps/ai_classroom/enrichment_nodes.py`
- `backend/apps/ai_classroom/services.py`
- `backend/apps/retrieval/services.py`
- `backend/providers/llm/chain.py`

#### Issues addressed

| Check | Issue | Resolution in this commit |
|-------|-------|---------------------------|
| **G10** | Non-deterministic chunk retrieval via `order_by("?")` | Replaced with `RetrievalService.search()` — relevance-based retrieval seeded from document content |
| **G11** | Prompt injection: unseparated system/task instructions from untrusted evidence content | Wrapped evidence chunks in `<source id="…">` tags; prepended explicit directive telling the model to treat evidence as untrusted factual context only |
| **G12** | Data minimization: PII sent to external LLM providers | Created `backend/shared/sanitization.py` with redaction for emails, phone numbers, credit cards, and SSNs; `llm/chain.py._sanitize_for_provider` now delegates to the shared utility |
| **G15** | DB concurrency race in document revision creation (no row locking) | Flagged `select_for_update` / `_create_revision_locked` for verification in `documents/services.py` |
| **G5** | Change magnitude computed from hash-string Jaccard (always ~0.5, coalescing broken) | Rewrote `_compute_change_magnitude` to use **content-based** word-token Jaccard similarity over actual chunk `.content` |

**Additional infra improvement (not a G-check):**
- `_execute_node()` introduced in `services.py` to execute enrichment nodes individually with **checkpoint persistence** after each successful node, enabling resumable retries instead of full re-execution.

---

### 2. `bace85d` — enrichment fixes

**Files added (2 new):**
- `backend/verify_g11.py`
- `backend/verify_g5.py`

#### Issue addressed

| Check | Issue | Resolution in this commit |
|-------|-------|---------------------------|
| **G11** | No automated verification that `<source>` wrapper and untrusted-content directive were actually present in enrichment nodes | Added `verify_g11.py` — parses `enrichment_nodes.py`, counts `<source` occurrences, and checks the directive is present per-node (`draft_node`, `gap_detection_node`, `gap_fill_node`) |
| **G5** | No automated verification that `_compute_change_magnitude` uses content-based Jaccard (not hash-based) | Added `verify_g5.py` — AST-parses `services.py`, locates the method, and runs critical checks (no `split("|")`, uses `.content`, uses `jaccard`, `1.0 - jaccard`, no `0.5` placeholder, returns `1.0` if no previous enrichment) |

These were **verification helpers** to validate the fixes from commit 1 were correctly applied.

---

### 3. `e9923a8` — Remove obsolete validation scripts for G10, G11, G12, and G15 checks, and clean up related imports

**This commit reverses the script additions.** All 6 scripts from commits 1–2 were deleted:
- `backend/check_g10.py` — **deleted**
- `backend/check_g11.py` — **deleted**
- `backend/check_g12.py` — **deleted**
- `backend/check_g15.py` — **deleted**
- `backend/verify_g11.py` — **deleted**
- `backend/verify_g5.py` — **deleted**
- `backend/read_prompts.py` — **deleted**

**Files modified (3 substantive + 2 already-tracked):**
- `backend/apps/ai_classroom/enrichment_nodes.py`
- `backend/apps/ai_classroom/services.py`
- `backend/providers/llm/chain.py`

#### Issues addressed

| Area | Issue | Resolution |
|------|-------|------------|
| **Validation scripts** | Ad-hoc, hard-coded-path validation scripts were not maintainable or part of the test suite | All removed; the underlying fixes they validated remain in place |
| **G11 / enrichment nodes** | Placeholder dead import `from_provider = get_llm_provider()` in `retrieve_chunks_node` | Removed the unused placeholder line |
| **G12 / chain.py** | Redundant `_REDACTION_PATTERNS` list still defined locally after delegating to `shared/sanitization.py` | Removed the local `_REDACTION_PATTERNS` constant and the `import re` that only fed it |
| **Checkpoint resume logic** | `run_enrichment_job` had inconsistent/dead logic in the `gap_fill` resume path (comment said "gap_fill already completed, go to citation_stitch" with a `pass`) | Simplified: `gap_fill` resume node only executes `gap_fill_node` if gaps exist; otherwise skips directly to `citation_stitch` |
| **services.py** | Missing `re` and `time` imports, missing node function imports | Added `import re`, `import time`, and explicit imports of all enrichment node functions from `enrichment_nodes.py` |

#### What **stayed** (the actual security fixes remain):
- `<source>` wrapping + untrusted directive in `enrichment_nodes.py` (G11)
- Content-based Jaccard in `_compute_change_magnitude` returning `0.0` (not `0.5`) for empty tokens (G5)
- `sanitize_for_provider` delegation to shared module (G12)
- `RetrievalService.search` replacing `order_by("?")` (G10)
- Checkpoint-based node execution (infra)

---

### 4. `7e60689` — Refactor: Remove redundant optional imports + atomic chat message persistence

**Files modified (17):**

*Redundant `from typing import Optional` removal (9 files):*
- 7 LangGraph state files (`adaptive_test_state.py`, `agent_state.py`, `base_state.py`, `chat_state.py`, `enrichment_state.py`, `question_generation_state.py`, `revision_planning_state.py`, `verification_state.py`)
- `backend/ai/schemas/chat.py`
- `backend/providers/registry.py`
- `backend/apps/chat/services.py`
- `backend/ai/tracing/decorators.py`

*Transaction atomicity (chat service):*
- `backend/apps/chat/services.py`
- `backend/apps/chat/views.py`
- `backend/apps/chat/langgraph_nodes.py`
- `backend/tests/unit/test_chat_graph.py`

*Frontend normalization:*
- `frontend/src/components/chat/ChatPage.tsx`
- `frontend/src/services/api/chat.ts`

#### Issues addressed

| Area | Issue | Resolution |
|------|-------|-----------|
| **Code quality** | 9 files had a duplicate `from typing import Optional` line (one in the multi-import line, one standalone) | Removed the redundant standalone import line in all 10 files |
| **G15-adjacent / data integrity** | `ChatService.ask()` had no explicit `@transaction.atomic` — user message + auto-title were in separate operations | Replaced loose `@transaction.atomic` decorator with an explicit `with transaction.atomic():` block wrapping user-message creation + title generation, so the message persists even if the downstream graph/LLM call fails |
| **Chat verification** | `citation_verification_node` was a standalone node that duplicated logic now in the graph's `_run_verification` path | Removed the node from `langgraph_nodes.py`; updated the test `test_citation_verification_node` → `test_verification_via_graph_path` to exercise the real `_run_verification` path |
| **Chat API** | Chat message serializer omitted verification fields | Added `verification_status` and `verification_score` to `ChatMessageSerializer` fields |
| **Frontend normalization** | `normalizeCitations` in both ChatPage.tsx and chat.ts had `obj.field ?? null` after already checking `typeof obj.field === "string"` — the fallback `?? null` was redundant/dead code that could mask `undefined` as `null` | Replaced `obj.field ?? null` with literal `null` in both files |

---

### 5. `8401125` — feat: add PostgreSQL application password support and new database check scripts

**Files modified (2) + added (2):**
- `.env.example` — modified
- `backend/config/settings/prod.py` — modified
- `check_db.ps1` — **new**
- `test_db.py` — **new**
- `docker-compose.yml` — modified

#### Issues addressed

| Area | Issue | Resolution |
|------|-------|-----------|
| **Database security / RLS** | The `studyai_app` role (restricted, non-superuser for RLS enforcement) was created at init time with **no password**, and `prod.py` hardcoded `USER = "studyai_app"` | Added `POSTGRES_APP_PASSWORD` environment variable (see `.env.example`); `docker-compose.yml` `POSTGRES_INIT_SQL` now creates the role **with** the password; `prod.py` `USER` now reads from `POSTGRES_USER` env var instead of the hardcoded restricted-role name |
| **DB connectivity verification** | No easy way to verify the database accepts connections with configured credentials, especially after the RLS role change | Added `check_db.ps1` — reads `.env`, extracts `POSTGRES_USER`/`POSTGRES_PASSWORD`, and runs `docker compose exec db psql -U <user> -c "SELECT 1;"` |
| **Ad-hoc DB testing** | Needed a quick Python-level connection test | Added `test_db.py` using `psycopg` |

#### ⚠️ Security concern identified (not resolved)

`test_db.py` contains a **hardcoded plaintext password** (`'jIqNdghWtOWpvfn0VK--fO_p1nhV8dv9qiS3H2EY-54'`). While the file itself is a utility (not part of the app), committing a real credential is a secret-exposure risk. Recommendation: load from environment variables instead.

---

## Final State of the Repository

| File | Status |
|------|--------|
| `backend/check_g10.py` | ❌ Removed (obsolete) |
| `backend/check_g11.py` | ❌ Removed (obsolete) |
| `backend/check_g12.py` | ❌ Removed (obsolete) |
| `backend/check_g15.py` | ❌ Removed (obsolete) |
| `backend/verify_g11.py` | ❌ Removed (obsolete) |
| `backend/verify_g5.py` | ❌ Removed (obsolete) |
| `backend/read_prompts.py` | ❌ Removed (obsolete) |
| `backend/shared/sanitization.py` | ✅ **Kept** — shared PII redaction utility |
| `backend/apps/ai_classroom/enrichment_nodes.py` | ✅ **Kept** — `<source>` wrapping + untrusted directive (G11) |
| `backend/apps/ai_classroom/services.py` | ✅ **Kept** — content-based Jaccard (G5), checkpoint execution (infra) |
| `backend/providers/llm/chain.py` | ✅ **Kept** — delegates to `shared/sanitization.py` (G12) |
| `backend/apps/retrieval/services.py` | ✅ **Kept** — sanitized content before embedding (G12) |
| `backend/apps/chat/services.py` | ✅ **Kept** — atomic message persistence |
| `backend/apps/chat/views.py` | ✅ **Kept** — verification fields in serializer |
| `backend/apps/chat/langgraph_nodes.py` | ✅ **Kept** — removed redundant `citation_verification_node` |
| `backend/tests/unit/test_chat_graph.py` | ✅ **Kept** — updated test for graph-path verification |
| 9 LangGraph state/schema files | ✅ **Kept** — redundant imports removed |
| `frontend/src/components/chat/ChatPage.tsx` | ✅ **Kept** — simplified nullable citation normalization |
| `frontend/src/services/api/chat.ts` | ✅ **Kept** — simplified nullable citation normalization |
| `.env.example` | ✅ **Kept** — added `POSTGRES_APP_PASSWORD` |
| `backend/config/settings/prod.py` | ✅ **Kept** — env-based DB user |
| `docker-compose.yml` | ✅ **Kept** — app password in init SQL |
| `check_db.ps1` | ✅ **Kept** — new DB connectivity check |
| `test_db.py` | ✅ **Kept** — new ad-hoc DB test *(contains hardcoded password)* |

---

## Summary of Issues & Resolutions

### Security issues resolved (✅)

| ID | Check | Issue | Resolution | Status |
|----|-------|-------|------------|--------|
| G5 | Change magnitude | Hash-based Jaccard always returned ~0.5; coalescing broken | Content-based word-token Jaccard; empty→0.0; no-prev→1.0 | **Resolved** |
| G10 | Non-deterministic retrieval | `order_by("?")` used for chunk retrieval | Replaced with `RetrievalService.search()` on document content | **Resolved** |
| G11 | Prompt injection | Evidence content mixed with system/task instructions | `<source>` tags + explicit untrusted-content directive | **Resolved** |
| G12 | Data minimization / PII leakage | No centralized redaction before LLM/embedding calls | `shared/sanitization.py` redacts email/phone/CC/SSN; used in both `chain.py` and `retrieval/services.py` | **Resolved** |
| G15 | DB concurrency | No `select_for_update` on revision creation | Flagged for verification (check_g15.py removed, but `_create_revision_locked` expectation documented) | **Partially resolved** |

### Code quality / data integrity issues resolved (✅)

| ID | Issue | Resolution | Status |
|----|-------|------------|--------|
| G5-adjacent | No automated verification of G5 fix | `verify_g5.py` added then removed as obsolete | **Process changed** |
| G11-adjacent | No automated verification of G11 fix | `verify_g11.py` added then removed as obsolete | **Process changed** |
| — | Redundant `from typing import Optional` import in 10 files | Removed all duplicates | **Resolved** |
| — | `ChatService.ask()` message creation not atomic with title generation | Wrapped in explicit `with transaction.atomic():` | **Resolved** |
| — | `citation_verification_node` duplicated graph logic | Removed; test updated to use `_run_verification` path | **Resolved** |
| — | Frontend `?? null` dead fallback after typeof check | Replaced with literal `null` in 2 files | **Resolved** |
| — | Checkpoint resume path in `run_enrichment_job` had dead `pass` code | Simplified conditional logic | **Resolved** |
| — | Placeholder unused `from_provider` import in retrieval node | Removed | **Resolved** |

### Infrastructure issues resolved (✅)

| ID | Issue | Resolution | Status |
|----|-------|------------|--------|
| DB-RLS | `studyai_app` role created without password; hardcoded DB user in prod | `POSTGRES_APP_PASSWORD` in `.env.example`, `docker-compose.yml`, and `prod.py` | **Resolved** |
| DB-OPS | No DB connectivity check tooling | Added `check_db.ps1` | **Resolved** |

### Outstanding concerns (⚠️)

| Area | Issue | Recommendation |
|------|-------|----------------|
| **Secret management** | `test_db.py` contains a hardcoded plaintext database password | Replace with `os.environ.get("POSTGRES_PASSWORD")` |
| **G15 verification** | `check_g15.py` was removed; it is unclear if `_create_revision_locked` and `select_for_update` are actually implemented in `documents/services.py` | Verify the current state of `documents/services.py` for these constructs; the check script's removal means there is no automated guard |
| **Validation approach** | Ad-hoc scripts were used instead of the project test suite (pytest/Django TestCase) | The G10/G11/G12/G15/G5 fixes remain, but there is **no automated regression guard** unless they are covered by unit tests. Recommend adding assertions to the existing test suite rather than standalone scripts |
| **Script churn** | 3 validation scripts (check_g10/g11/g12/g15, verify_g5/g11, read_prompts) were added and removed within 3 commits | This represents ~280 lines of churn; the underlying fixes are valuable but the validation layer should be decided (keep as tests vs. remove as obsolete) |

---

## Conclusion

The 5-commit series delivered meaningful improvements across three domains:

1. **AI security hardening** — G11 (prompt injection segregation), G12 (PII redaction), G5 (correct change-magnitude computation), and G10 (deterministic retrieval) are all genuinely fixed in production code. The `shared/sanitization.py` module is a clean, reusable addition.

2. **Data integrity** — Chat message persistence is now atomic, preventing message loss on LLM failures.

3. **Database security** — The PostgreSQL restricted `studyai_app` role now uses an environment-configured password, improving the RLS security posture.

The **validation scripts** (commits 1–2) were correctly removed in commit 3 as obsolete, but their removal leaves the G10–G15 fixes without an automated regression guard. The one security concern that remains outstanding is the hardcoded password in `test_db.py`.
