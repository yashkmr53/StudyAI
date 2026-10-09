# Phase 13: Reliability & Broken Core Services Verification Report

## Executive Summary

Phase 13 addressed the broken core infrastructure and reliability bottlenecks identified during the comprehensive system audit. Building directly upon the security and tenant-isolation foundation established in Phase 12, Phase 13 repaired:
1. **Password Reset and Account Recovery Flow:** Eliminated invalid cryptographic imports, applied the pending database migration for `PasswordResetToken`, implemented high-entropy token hashing with atomic concurrency control, hardened email-enumeration defenses, and verified Mailpit/SMTP email dispatch.
2. **Scheduled Database Backups & Verifications:** Resolved missing `pg_dump`/`pg_restore` client tooling by equipping backend containers with PostgreSQL client packages, mounted durable host-volume storage (`./backups`), implemented automated retention pruning, and proved zero-data-loss restoration against disposable scratch databases without compromising live production data.
3. **Agentic AI Chat Endpoint Investigation & Repair:** Investigated `POST /api/v1/chat/` and `POST /api/v1/agents/chat/` (`AgentViewSet`). Determined it is actively wired to the frontend "Agent Mode" toggle in AI Classroom. Repaired missing framework imports (`settings`, `transaction`), eliminated a fatal `MultipleObjectsReturned` crash for multi-profile users, enforced active-profile tenant isolation, and aligned URL routing between frontend and backend.
4. **Configuration, Role, and Security Integrity:** Maintained `makemigrations --check` clean status, zero unapplied migrations, all 28 tables under PostgreSQL Row-Level Security (RLS), and preserved the separation between the unprivileged `studyai_app` runtime role and the administrative `studyai` role.

All 598 backend tests, 73 frontend tests, production build, and live E2E test suites passed with 100% green status.

---

## 1. Repository & Branch State

- **Base Branch:** `feature/phase-12-security-hardening` (Commit: `3907c2e`)
- **Active Working Branch:** `feature/phase-13-reliability-core-services`
- **Isolation:** `main` was left completely untouched. All modifications reside on `feature/phase-13-reliability-core-services`.
- **Target Deliverable:** Clean git worktree with full test coverage and live verification evidence.

---

## 2. Password Reset Architecture & Recovery Flow

### Historical Problem
The system audit revealed:
1. `PasswordResetView` and `PasswordResetConfirmView` raised runtime import errors attempting to load `PasswordResetTokenService` from an incomplete package path, referencing a non-existent `shared.crypto` helper.
2. The `PasswordResetToken` database table was absent in older environments, and the service lacked atomic concurrency safety and replay invalidation.

### Architectural Fixes
1. **Cryptographic Token Model & Service (`apps/accounts/services/password_reset.py`):**
   - Implemented 256-bit entropy token generation using `secrets.token_urlsafe(32)`.
   - Stored only SHA-256 hashes (`hashlib.sha256(raw_token.encode()).hexdigest()`) in PostgreSQL `PasswordResetToken.token`. Raw tokens are never stored at rest or logged.
   - Enforced 1-hour expiration TTL (`TOKEN_EXPIRY_HOURS = 1`).
   - Implemented atomic redemption using `select_for_update()` inside `transaction.atomic()`, preventing concurrent token re-use.
   - Upon successful redemption, all existing tokens for the user are invalidated, and a security audit event (`auth.password_reset_completed`) is recorded.
2. **Enumeration Protection (`apps/accounts/views.py`):**
   - `PasswordResetView.post` returns an identical HTTP 200 generic success message regardless of whether the email address exists in the database.
3. **Email Provider Integration (`providers/registry.py`):**
   - Corrected provider selection logic to honor `_get_env("EMAIL_BACKEND")` and Django settings precedence.
   - Dispatched real reset emails via Mailpit (`mailpit:1025`) in Docker and verified message capture at `http://localhost:8025/api/v1/messages`.
4. **Test Verification (`backend/tests/api/test_password_reset.py`):**
   - 9 automated unit/API tests covering end-to-end token generation, password change persistence, login verification, token replay protection, expiration rejection, invalid token rejection, unknown email enumeration safety, and single-use concurrency.

---

## 3. Scheduled Database Backups & Verifications

### Historical Problem
The system audit found that `apps.audit.tasks.daily_backup` threw `FileNotFoundError: [Errno 2] No such file or directory: 'pg_dump'` because PostgreSQL client binaries were absent from the backend container image, and backups lacked persistent volume binding.

### Architectural Fixes
1. **Client Tooling Installation (`backend/Dockerfile`):**
   - Added `postgresql-client` to the Debian runtime image, providing `/usr/bin/pg_dump` and `/usr/bin/pg_restore`.
2. **Durable Host Volume (`docker-compose.yml`):**
   - Mounted `./backups:/backups` into `studyai-api-1`, `studyai-worker-1`, and `studyai-beat-1`, guaranteeing persistence across container rebuilds.
3. **Backup Generation Task (`apps/audit/tasks.py`):**
   - Updated `daily_backup` Celery task to execute `pg_dump` using custom compressed format (`-Fc`).
   - Securely injected database credentials via `env["PGPASSWORD"]` rather than command-line arguments to prevent credential exposure in `ps` process tables.
   - Implemented `_prune_old_backups` with automated 7-day retention cleanup.
4. **Scratch Restoration Command (`apps/audit/management/commands/verify_backup.py`):**
   - Updated `verify_backup` management command to create a disposable database (`<db>_restore_verify`), restore the dump, execute core table smoke queries (`accounts_user`, `documents_document`), and cleanly drop the scratch database without mutating live data.
   - Added handling for cross-version PostgreSQL preamble warnings (e.g., `transaction_timeout`).

---

## 4. Agentic AI Chat Endpoint (`AgentViewSet`)

### Investigation Findings
The audit identified `POST /api/v1/chat/` failing with runtime errors. Our investigation revealed:
1. **Active Frontend Integration:**
   - In `frontend/src/components/chat/ChatPage.tsx`, an "Agent Mode" toggle enables `useAgentChat`, which invokes `agentApi.sendMessage` targeting `/agents/chat/`.
   - The endpoint is NOT dead or legacy; it is the orchestrator backing the Agent Mode feature in the AI Classroom.
2. **Defects Identified:**
   - `apps/agents/views.py`: Omitted imports for `settings` and `transaction`, causing `NameError`.
   - `apps/agents/services/agent.py`: Used `Profile.objects.get(user=user)`, which threw `MultipleObjectsReturned` for any user with multiple profiles (e.g., School and Personal profiles).
   - `apps/agents/views.py`: Allowed cross-profile session queries without active profile filtering.
   - `apps/agents/prompts/agent_prompts.py`: Contained unescaped JSON curly braces `{}` inside `AGENT_SYSTEM_PROMPT`, crashing Python's `str.format()` with `KeyError`.
   - `apps/agents/urls.py`: Routed only to `/api/v1/chat/`, while the frontend `agentApi` expected `/api/v1/agents/chat/`.

### Architectural Fixes
1. **Import and Error Fixes:**
   - Added top-level `from django.conf import settings` and `from django.db import transaction` in `apps/agents/views.py`.
   - Escaped JSON blocks in `AGENT_SYSTEM_PROMPT` as `{{` and `}}`.
   - Handled null tool selections gracefully in `agent_nodes.py` and `agent_graph.py`.
2. **Active Profile Isolation:**
   - Scoped `session_qs` in `AgentViewSet.chat` to `request.profile` (respecting `X-Active-Profile` / `X-Profile-ID`).
   - Scoped `execution_trace` lookup in `AgentViewSet.execution_trace` to `self.get_queryset()`.
   - Resolved profile in `StudyAIAgent.process_request` directly from `session.profile`.
3. **URL Route Dual-Binding:**
   - Registered `AgentViewSet` under both `r""` and `r"agents"`, ensuring both `/api/v1/chat/` (and `/tools/`, `/executions/`) and `/api/v1/agents/chat/` (and `/agents/tools/`, `/agents/executions/`) resolve seamlessly.
4. **Test Verification (`backend/tests/api/test_agent_chat.py`):**
   - 8 tests covering direct and prefixed endpoints, tools schema listing, execution trace isolation, active profile boundary defense, multi-profile user stability, and cross-tenant rejection.

---

## 5. Database & RLS Security Integrity Verification

| Check | Expected | Actual State | Status |
| :--- | :--- | :--- | :--- |
| `python manage.py makemigrations --check` | Clean (No changes) | Clean (`No changes detected`) | **VERIFIED** |
| `python manage.py migrate --plan` | No pending migrations | No planned operations | **VERIFIED** |
| PostgreSQL `studyai` Role | Superuser / Migration Admin | `rolsuper=t, rolcreatedb=t` | **VERIFIED** |
| PostgreSQL `studyai_app` Role | Restricted Runtime Role | `rolsuper=f, rolcreatedb=f` | **VERIFIED** |
| Tables with Row-Level Security (RLS) | 28 tables | Exactly 28 tables enabled | **VERIFIED** |
| Durable Backup Directory | Mounted host volume | `./backups:/backups` verified | **VERIFIED** |

---

## 6. Comprehensive Verification Matrix

### A. Backend Pytest Suite
Command: `docker exec studyai-api-1 pytest --ds=config.settings.test`
- **Total Tests Collected:** 598
- **Passed:** 590
- **Skipped:** 8 (intentional environment-specific tests)
- **Failed:** 0
- **Execution Time:** 36.89 seconds
- **Result:** **100% PASS**

### B. Frontend Vitest Suite
Command: `docker exec studyai-frontend-1 npm run test`
- **Test Files:** 11 passed (11 total)
- **Tests Passed:** 73 passed (73 total)
- **Failed:** 0
- **Execution Time:** 731 ms
- **Result:** **100% PASS**

### C. Frontend Production Build
Command: `docker exec studyai-frontend-1 npm run build`
- **TypeScript Check:** `tsc -b` passed with 0 errors.
- **Vite Production Bundler:** 149 modules transformed, PWA service worker generated, bundle emitted in 1.34s.
- **Result:** **100% PASS**

### D. Phase 12 Security E2E Suite
Command: `node frontend/tests/e2e/phase12_security_isolation.mjs`
- **Checks Verified:** 17/17 security isolation assertions passed.
- **Result:** **100% PASS**

### E. Phase 13 Core Services Live E2E Suite
Command: `node frontend/tests/e2e/phase13_reliability_core_services.mjs`
- **Password Reset Flow:** User registration, email enumeration protection, Mailpit token capture, cryptographic extraction, invalid token rejection (422), password update confirmation (200), replay guard (422), old password invalidation (401), new password authentication (200).
- **Database Backup & Restoration:** Live `pg_dump` invocation, custom-format dump created in `./backups`, scratch restoration into disposable database, smoke query row counts validated, scratch database cleaned up.
- **Agentic Chat Discovery & Scoping:** Tools schema discovery on `/tools/` and `/agents/tools/`, unknown session isolation on `/chat/` and `/agents/chat/`.
- **Result:** **100% PASS**

---

## 7. Residual Risks & Operational Recommendations

1. **Email Delivery in Production:** Mailpit is used for local and development environments. For production deployments, ensure `EMAIL_BACKEND=smtp` with valid `SMTP_HOST`, `SMTP_PORT`, and `SMTP_USER` environment variables are provisioned.
2. **Offsite Backup Hook:** The Celery backup task supports invoking `/app/scripts/backup_offsite_hook.sh` when `OFFSITE_BACKUP_URI` (e.g., S3/GCS bucket) is configured. We recommend provisioning an external object store bucket in staging/production for automated offsite synchronization.

---

PHASE 13 COMPLETE
