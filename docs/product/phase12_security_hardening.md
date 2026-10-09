# StudyAI — Phase 12: Security & Integrity Hardening Report

**Execution Date:** 2026-10-09  
**Branch:** `main`  
**Phase Status:** **COMPLETE**

---

## 1. Executive Summary

Phase 12 addressed four critical security and data-integrity vulnerabilities identified during the comprehensive current-state repository audit:
1. **Global Reference Document Deletion Authorization Bypass**: Non-staff users could delete platform-wide reference materials (`profile = NULL`) via an improper authorization branch in `ReferenceDocumentViewSet.destroy`.
2. **PostgreSQL Row Level Security (RLS) Non-Enforcement**: Although RLS migration scripts existed historically, the live Django application connected to PostgreSQL using the table owner/superuser role (`studyai`), completely bypassing PostgreSQL RLS policies at the engine level. Furthermore, 12 of the 28 multi-tenant tables lacked active RLS policies or `FORCE ROW LEVEL SECURITY`.
3. **Backend Sole-Profile Deletion Guard Absence**: While the web UI disabled deleting the last remaining profile, the backend `DELETE /api/v1/profiles/{id}` endpoint allowed complete profile deletion, leaving users orphaned with zero profiles.
4. **Arbitrary `.first()` Profile Resolution Ambiguity**: Critical services (hybrid retrieval, revision planning, adaptive test generation, and agentic workflows) fell back to `Profile.objects.filter(user=user).first()`, causing cross-profile state bleeding and silent tenant misattribution for multi-profile users.

All four vulnerabilities were remediated with architectural defense-in-depth, backed by dedicated automated test suites across unit, integration, and live E2E levels. Regression testing confirms 100% test passage (569 passed backend tests, 73 passed frontend unit tests, and 17 passed live E2E integration assertions) with zero regressions to existing core product functionality.

---

## 2. Threat Model & Hardening Goals

### 2.1 Threat Model
* **Threat Actor 1 (Malicious Authenticated Student)**: Authenticates normally, possesses valid JWT, attempts to issue REST requests deleting shared global reference textbooks or querying private notes, notebooks, and subjects belonging to other students or different profiles.
* **Threat Actor 2 (Privilege Escalation / Cross-Profile Confusion)**: User possesses two profiles (e.g. NoteSpace profile vs. AI Classroom profile). Initiates hybrid RAG retrieval or adaptive test generation while Profile B is active. Improper backend query resolution selects Profile A's notes, leaking private student data into Profile B's context.
* **Threat Actor 3 (Application-Layer Bypass / SQL Injection Defense)**: An attacker exploits an application-layer logical flaw or ORM leak. Without database-level RLS enforcement, the compromised query accesses all rows in the PostgreSQL database.

### 2.2 Hardening Goals
* **G1: Strict Global Reference Access Control**: Only staff/admin users (`request.user.is_staff`) may delete global references (`profile is NULL`). Only profile owners may delete their private references.
* **G2: Database Engine Level RLS (Defense-in-Depth)**: Ensure all multi-tenant tables enforce `ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`. Migrate runtime application connections to a restricted `studyai_app` role (`NOSUPERUSER NOBYPASSRLS`), guaranteeing database-level row filtering even if application ORM filters are omitted.
* **G3: Server-Enforced Sole-Profile Guard**: Prevent deleting a user's final profile at the API layer with HTTP 400 (`SOLE_PROFILE_CANNOT_BE_DELETED`).
* **G4: Explicit Active Profile Propagation**: Eliminate all arbitrary `.first()` profile fallbacks. Require explicit profile propagation across hybrid search, LangGraph chat nodes, test generation, and revision services.

---

## 3. Findings Resolved

### 3.1 Global Reference Deletion Authorization Bypass
* **Root Cause**: `ReferenceDocumentViewSet.destroy` evaluated:
  ```python
  if not instance.profile and not request.user.is_staff:
      pass  # Execution fell through to super().destroy()!
  ```
* **Remediation**: Replaced with strict guard logic in `backend/apps/references/views.py`:
  ```python
  if instance.profile is None:
      if not request.user.is_staff:
          return Response(
              {"detail": "Only staff members can delete global reference documents."},
              status=status.HTTP_403_FORBIDDEN,
          )
  else:
      if instance.profile.user_id != request.user.id:
          return Response(
              {"detail": "You do not have permission to delete this reference document."},
              status=status.HTTP_403_FORBIDDEN,
          )
  ```
* **Verification**:
  - Non-staff user attempting to delete global reference: **HTTP 403 Forbidden** (verified in unit tests and live E2E).
  - Staff user deleting global reference: **HTTP 204 No Content**.
  - Non-owner attempting to delete foreign private reference: **HTTP 403/404**.
  - Owner deleting own private reference: **HTTP 204 No Content**.

### 3.2 Real PostgreSQL Row Level Security (RLS) Enforcement
* **Root Cause**:
  1. The Django application connected as `studyai`, the table owner and PostgreSQL superuser. In PostgreSQL, table owners and superusers bypass RLS by default.
  2. RLS policies existed for only 16 tables. 12 multi-tenant tables (`references_referencedocument`, `references_referencechunk`, `notebooks_notebook`, `retrieval_canvasstroke`, `questions_documentquestion`, etc.) had no RLS enabled.
  3. `FORCE ROW LEVEL SECURITY` was not universally applied.
* **Remediation**:
  1. Created restricted application role `studyai_app`:
     ```sql
     CREATE ROLE studyai_app WITH LOGIN PASSWORD 'studyai_app_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
     GRANT USAGE ON SCHEMA public TO studyai_app;
     GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO studyai_app;
     GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO studyai_app;
     ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO studyai_app;
     ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO studyai_app;
     ```
  2. Created container initialization script `docker/postgres/init/01-init-roles.sql` and mounted it into PostgreSQL container init scripts.
  3. Created migrations `audit.0003_phase12_rls_hardening` and `references.0003_enable_rls` applying `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` to all 28 multi-tenant tables.
  4. Configured `backend/config/settings/prod.py` to connect via `studyai_app` at runtime.
  5. Updated `RlsContextMiddleware` (`backend/shared/database/middleware.py`) to resolve authenticated JWT users and wrap request transactions in `profile_scoped_transaction(profile_id)`.
* **Verification**:
  - Direct execution in PostgreSQL: `studyai_app` cannot see or insert rows belonging to other profiles or when `app.current_profile_id` is unset (`psycopg.errors.InsufficientPrivilege: new row violates row-level security policy`).
  - All 28 tenant tables report `relrowsecurity = true` and `relforcerowsecurity = true`.

### 3.3 Backend Sole-Profile Deletion Guard
* **Root Cause**: `ProfileViewSet.destroy` called `super().destroy()` without inspecting the count of profiles owned by the requesting user.
* **Remediation**: Added server-side validation in `backend/apps/profiles/views.py`:
  ```python
  def destroy(self, request, *args, **kwargs):
      instance = self.get_object()
      user_profiles_count = Profile.objects.filter(user=request.user).count()
      if user_profiles_count <= 1:
          return Response(
              {
                  "error": {
                      "code": "SOLE_PROFILE_CANNOT_BE_DELETED",
                      "message": "Cannot delete profile. At least one profile must remain.",
                  }
              },
              status=status.HTTP_400_BAD_REQUEST,
          )
      return super().destroy(request, *args, **kwargs)
  ```
* **Verification**:
  - Direct API `DELETE /api/v1/profiles/{sole_profile_id}` returns **HTTP 400 Bad Request** with payload `{"error": {"code": "SOLE_PROFILE_CANNOT_BE_DELETED", ...}}`.
  - When >= 2 profiles exist, deletion of non-sole profile returns **HTTP 204 No Content**.

### 3.4 Elimination of `.first()` Profile Ambiguity
* **Root Cause**:
  Arbitrary `.first()` invocations occurred in 5 key subsystems:
  - `backend/shared/authorization/services.py`: `get_active_profile()` fell back to `Profile.objects.filter(user=user).first()`.
  - `backend/apps/retrieval/retrieval.py`: Hybrid search defaulted to user's first profile if none specified.
  - `backend/apps/revision/views.py`: All four view endpoints (`recommendations`, `schedule`, `daily_queue`, `complete_session`) fetched `request.user.profiles.first()`.
  - `backend/apps/tests/views.py`: `TestViewSet.create` resolved active profile via `.first()`.
  - `backend/apps/agents/tools/base.py`: Tools executed with `.first()` when profile was absent.
* **Remediation**:
  1. Updated `ProfileAuthorizationService.get_active_profile(request)`: Only resolves automatically if the user has exactly 1 profile. If the user has multiple profiles and no `X-Active-Profile` header is provided, it returns `None`. Added `require_active_profile(request)` which raises `ValidationError({"profile": "Active profile header required."})`.
  2. Updated `RetrievalService.search`: Accepts explicit `profile=None` parameter. For multi-profile users, omitting `profile` raises a `ValueError`.
  3. Scoped LangGraph nodes (`apps/chat/langgraph_nodes.py`, `apps/tests/adaptive_test_nodes.py`, `apps/ai_classroom/enrichment_nodes.py`) to pass explicit session/job profile.
  4. Updated `backend/apps/revision/views.py` and `backend/apps/tests/views.py` to use `require_active_profile(request)`.
  5. Updated retrieval tools (`ai/tools/retrieval_tool.py`, `apps/agents/tools/base.py`) to pass active profile context into retrievers.
* **Verification**:
  - Multi-profile search without profile raises `ValueError`.
  - Calling retrieval under Profile A returns only Profile A notes and chunks; Profile B resources are completely hidden.

---

## 4. Database Security Architecture

### 4.1 Database Roles & Privilege Separation
| Database Role | Privileges | Bypass RLS? | Purpose |
| :--- | :--- | :---: | :--- |
| `studyai` | `SUPERUSER`, `CREATEDB`, `CREATEROLE` | YES | Table Owner; used strictly for schema migrations and administrative operations. |
| `studyai_app` | `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOBYPASSRLS` | **NO** | Runtime application role; executed by Django API and Celery workers. |

### 4.2 Comprehensive RLS Table Inventory (All 28 Multi-Tenant Tables)
All 28 tables have been verified in PostgreSQL with `relrowsecurity = true` and `relforcerowsecurity = true`:

| # | Table Name | RLS Enabled | FORCE RLS | Isolation Policy Summary |
| :-: | :--- | :---: | :---: | :--- |
| 1 | `profiles_profile` | YES | YES | `user_id = current_user_id()` or active profile match |
| 2 | `subjects_subject` | YES | YES | `profile_id = current_profile_id()` |
| 3 | `documents_document` | YES | YES | `profile_id = current_profile_id()` OR (`profile_id IS NULL AND source = 'reference'`) |
| 4 | `documents_documentpage` | YES | YES | via document ownership |
| 5 | `documents_documentpagerevision` | YES | YES | via document ownership |
| 6 | `notebooks_notebook` | YES | YES | `profile_id = current_profile_id()` |
| 7 | `retrieval_canvasstroke` | YES | YES | `profile_id = current_profile_id()` |
| 8 | `retrieval_canvasdevice` | YES | YES | `profile_id = current_profile_id()` |
| 9 | `retrieval_canvasdrawing` | YES | YES | `profile_id = current_profile_id()` |
| 10 | `retrieval_canvasclientstate` | YES | YES | `profile_id = current_profile_id()` |
| 11 | `retrieval_canvasoutboxop` | YES | YES | `profile_id = current_profile_id()` |
| 12 | `retrieval_notechunk` | YES | YES | `profile_id = current_profile_id()` |
| 13 | `references_referencedocument` | YES | YES | `profile_id = current_profile_id() OR profile_id IS NULL` |
| 14 | `references_referencechunk` | YES | YES | via `reference_document` profile match or global |
| 15 | `chat_chatsession` | YES | YES | `profile_id = current_profile_id()` |
| 16 | `chat_chatmessage` | YES | YES | via `session.profile_id = current_profile_id()` |
| 17 | `ai_classroom_tag` | YES | YES | `profile_id = current_profile_id()` |
| 18 | `ai_classroom_enrichmentcandidate` | YES | YES | via document profile match |
| 19 | `ai_classroom_verifiedgap` | YES | YES | via document profile match |
| 20 | `questions_documentquestion` | YES | YES | via document profile match |
| 21 | `questions_stalequestionlog` | YES | YES | via document profile match |
| 22 | `tests_testinstance` | YES | YES | `profile_id = current_profile_id()` |
| 23 | `tests_testquestion` | YES | YES | via `test.profile_id = current_profile_id()` |
| 24 | `tests_testattempt` | YES | YES | via `test.profile_id = current_profile_id()` |
| 25 | `tests_studentmastery` | YES | YES | `profile_id = current_profile_id()` |
| 26 | `tests_masteryhistory` | YES | YES | `profile_id = current_profile_id()` |
| 27 | `revision_revisionschedule` | YES | YES | `profile_id = current_profile_id()` |
| 28 | `revision_revisionsession` | YES | YES | `profile_id = current_profile_id()` |

### 4.3 `app.current_profile_id` Lifecycle & Celery Propagation
1. **HTTP Requests**:
   - `RlsContextMiddleware` inspects incoming `X-Active-Profile`.
   - Resolves and verifies user ownership via JWT.
   - Enters context `profile_scoped_transaction(profile_id)` using `SELECT set_config('app.current_profile_id', :id, true)`.
   - On request completion or exception, transaction boundary commits or rolls back, automatically resetting the setting to `''`.
2. **Celery Asynchronous Tasks**:
   - Celery tasks never accept client-supplied profile context directly from parameters without validation.
   - Job payloads serialize trusted `profile_id`.
   - Background workers execute within `with profile_scoped_transaction(job.profile_id):` blocks, binding RLS for the duration of ingestion, embedding generation, or test creation.

---

## 5. Application Authorization Architecture

### 5.1 Profile Resolution Order
Endpoints resolve the active profile using `ProfileAuthorizationService.get_active_profile(request)` according to the following precedence:
1. `X-Active-Profile` HTTP header (validated against `request.user`).
2. Single-profile user fallback (only if `user.profiles.count() == 1`).
3. If user owns > 1 profile and no header is provided: returns `None` (requiring caller to explicitly specify or prompting client error).

### 5.2 Module-Profile Affinity
- Profiles belong strictly to either `NOTE_SPACE` or `AI_CLASSROOM`.
- `X-Active-Module` validation in `ProfileViewSet` and middleware prevents cross-module profile execution with HTTP 403.

### 5.3 Direct UUID Protection
All detail views (`GET /api/v1/subjects/{id}`, `GET /api/v1/documents/{id}`, etc.) filter through profile-scoped querysets:
- If an authenticated user queries a valid UUID belonging to another user or another profile of the same user, DRF returns **HTTP 404 Not Found** (or 403 Forbidden). No object metadata or existence leaks.

---

## 6. Retrieval & AI Security

### 6.1 Multi-Profile Search Scoping
- `RetrievalService.search` requires explicit `profile` scoping when searching documents and note chunks.
- When Profile A is active:
  - Private notes from Profile B are excluded by both application ORM filter (`profile=profile_a`) and PostgreSQL RLS engine policy.
  - Multi-profile searches without profile context raise explicit `ValueError`.

### 6.2 Reference Scope Policy
- `retrieve_reference_context` combines:
  1. Global platform reference documents (`profile IS NULL`).
  2. Active profile private reference documents (`profile = current_profile`).
- Private reference documents belonging to any other profile are strictly excluded.

---

## 7. Test Methodology & Results

### 7.1 Regression Suite Summary
```text
================================================================================
Test Suite                                         Passed   Skipped   Failed
================================================================================
Backend Pytest Suite (tests/, apps/, providers/)      569         8        0
Frontend Unit & Integration (Vitest)                   73         0        0
Phase 12 Dedicated API Security Tests (Pytest)         10         1*       0
Live E2E Security & Integrity Suite (Node.js)          17         0        0
================================================================================
*Note: 1 SQLite skip in Phase 12 Pytest runs only on PostgreSQL where it was verified live.
```

### 7.2 Dedicated Security E2E Test Execution (`phase12_security_isolation.mjs`)
Live execution output against running Docker containers (`studyai-api-1`, `studyai-db-1`, `studyai-worker-1`):
```text
[04:29:02.774] Starting Phase 12 Security & Integrity E2E Verification...
[04:29:02.942]   [PASS] Authentication (Staff and User tokens acquired for sec_user_1791520142860@studyai.dev)
[04:29:02.957]   [PASS] Profile Setup (Normal user prepared with exactly 1 initial profile)
[04:29:02.967]   [PASS] Sole Profile Deletion Guard (Rejected with 400 SOLE_PROFILE_CANNOT_BE_DELETED)
[04:29:02.981]   [PASS] Sole Profile Persistence (Profile survived illegal deletion attempt)
[04:29:02.992]   [PASS] Create Profile 2 (Created secondary profile ce7988ed-1236-485e-b83e-a108c5b20438)
[04:29:03.013]   [PASS] Multi-Profile Deletion Allowed (Successfully deleted non-sole profile with 204)
[04:29:03.045]   [PASS] Create Global Reference (Staff created global reference c0e91535-4e1f-4b39-aae0-4504af2f8a37)
[04:29:03.058]   [PASS] Create Private Reference A (Created private reference 5c549c5f-6e7c-4c7c-9295-d6f881fdb1e8 under Profile A)
[04:29:03.069]   [PASS] Global Reference Deletion Guard (Non-staff user blocked with 403 Forbidden)
[04:29:03.083]   [PASS] Cross-Profile Private Reference Deletion Guard (Blocked cross-profile deletion with status 404)
[04:29:03.096]   [PASS] Own Private Reference Deletion (Owner successfully deleted private reference with 204)
[04:29:03.112]   [PASS] Staff Global Reference Deletion (Staff successfully deleted global reference with 204)
[04:29:03.137]   [PASS] Create Profile A Resources (Subject 5a15f22d and Document a2ef0d77 created under Profile A)
[04:29:03.150]   [PASS] Cross-Profile Direct Subject Access Blocked (Status 404)
[04:29:03.160]   [PASS] Cross-Profile Direct Document Access Blocked (Status 404)
[04:29:03.169]   [PASS] Subject List Scoping (Profile B subject list strictly excludes Profile A subjects)
[04:29:03.183]   [PASS] Document List Scoping (Profile B document list strictly excludes Profile A documents)
==========================================
ALL 17 E2E SECURITY CHECKS PASSED!
==========================================
```

---

## 8. Current Repository Health

- **Django Migrations**: Clean. `makemigrations --check` reports "No changes detected". All migrations applied cleanly.
- **Database Engine**: PostgreSQL 16 with pgvector extension active. All 28 tenant tables protected by `FORCE ROW LEVEL SECURITY`.
- **Containers**: All 7 services healthy (`api`, `worker`, `beat`, `frontend`, `db`, `redis`, `minio`).
- **Frontend Production Build**: `tsc -b && vite build` built cleanly with zero errors.

---

## 9. Remaining Non-Security Backlog (Reference Only)

The following items were identified during the full repository audit but are explicitly **out-of-scope for Phase 12 (Security & Integrity Hardening)** and remain for future product phases:
1. **Revision Planner Full UI**: Real-time calendar/schedule interaction component in frontend.
2. **True SSE/WebSocket Streaming in Chat**: Replacing simulated chunk streaming with backend SSE tokens.
3. **Large Textbook PDF Scalability**: Multi-part background chunking for 500+ page books.
4. **Enrichment Graph Expansion**: Additional gap analysis heuristics and teacher-facing summaries.

---

## 10. Sign-Off

All objectives of Phase 12 (Global Reference Authorization, PostgreSQL RLS Enforcement, Sole-Profile Deletion Guard, and Active Profile Ambiguity Elimination) have been fully implemented, integrated, verified against live infrastructure, and validated with complete regression testing.

PHASE 12 COMPLETE
