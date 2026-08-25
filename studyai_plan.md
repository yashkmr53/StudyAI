# StudyAI — Strategy Plan

## 1. Change Ask StudyAI Scope: Subject → Module Level

### Current State
- **Backend:** `ChatSession.subject` is nullable; `RetrievalService.search()` already supports `subject=None` (searches across all profile subjects). `ChatState.subject_id` / `AgentState.subject_id` are `Optional[str]`.
- **Frontend:** Ask StudyAI is only reachable at `/subjects/:subjectId/chat`. The module toggle (NOTE_SPACE ↔ AI_CLASSROOM) is per-subject UI state.

### Desired State
Ask StudyAI is **derived from the module (AI_CLASSROOM) level**, not a specific subject. Users access it from the module scope; retrieval searches across all subjects in the profile when no subject is selected.

### Backend Changes
No schema migration required. The backend already supports subject-less sessions and profile-wide retrieval.

| File | Change |
|---|---|
| `apps/chat/views.py` | Ensure `ChatSessionSerializer` and `create()` cleanly accept null `subject` (already do). No functional change needed; just verify the serializer returns `subject: null` for module-level sessions. |
| `apps/chat/langgraph_nodes.py:24-39` | Already passes `subject=subject` (which can be `None`) to `RetrievalService.search()`. No change needed. |
| `apps/chat/services.py:53-67` | Already builds `ChatState` with `subject_id=None` when `session.subject_id` is null. No change needed. |
| `apps/agents/services/agent.py:41-58` | Already builds `AgentState` with `subject_id=None` when session has no subject. No change needed. |

**Verdict:** Backend is already module-scope ready. Changes are minimal (mostly serializer/docs).

### Frontend Changes
| File | Change |
|---|---|
| `frontend/src/routes/index.tsx` | Add `<Route path="ai-classroom/chat" element={<ServiceRoute service="chat"><ChatPage /></ServiceRoute>} />`. Update legacy `/chat` redirect to `/ai-classroom/chat`. |
| `frontend/src/components/chat/ChatPage.tsx` | Make `subjectId` optional. When absent: show module-level breadcrumb (`AI Classroom > Ask StudyAI`), filter threads to include subject-less sessions, create sessions without subject. When present: retain current subject-scoped behavior. |
| `frontend/src/components/subjects/SubjectWorkspace.tsx:171-178` | Change Ask StudyAI `ServiceCard` link from `/subjects/${subjectId}/chat` to `/ai-classroom/chat` so it opens at module scope. |
| `frontend/src/services/api/chat.ts` | `createSession` should accept optional `subjectId` and send `null` when not provided (already supports it via `subjectId || null`). |
| `frontend/src/components/modules/ModuleContext.tsx` | No change needed; `useSubjectModule` already resolves module services. |

### Migration / Compatibility
- Keep `/subjects/:subjectId/chat` working for backward compatibility.
- New canonical entry point: `/ai-classroom/chat`.
- SubjectWorkspace card links to module-level chat.

---

## 2. Data Seeding Strategy

### Goal
Seed raw data to test: **enrichment → practice Q&A → tagging → test generation → Ask StudyAI (module-level)**.

### Approach
Create a Django management command: `python manage.py seed_test_data`.

### Seed Flow
1. **User + Profile** — create or reuse a test user/profile.
2. **Subjects** — create 3 subjects (e.g., `Mathematics`, `Physics`, `Computer Science`).
3. **Documents / Notes** — create source documents directly via models (avoid full upload/OCR pipeline for speed):
   - `Document` (source=`upload`, source_type=`image`)
   - `DocumentPage` + `DocumentPageRevision` with `ocr_status=completed`
   - `DocumentLine` rows with realistic text content
   - `NoteChunk` rows with embeddings + tsvector (mock or skip embedding for SQLite fallback)
4. **Enrichment** — create `EnrichedNote` + `EnrichedNoteBlock` + `CitationBlock` for a subset of documents.
5. **Tags** — create hierarchical `Tag` trees per subject (Subject → Unit → Topic).
6. **Questions** — create `Question` rows linked to revisions/chunks, with `QuestionTagLink`.
7. **Tests** — create `TestInstance` + `TestQuestion` + `Attempt` + `MasteryScore`.
8. **Chat Sessions** — create both:
   - Subject-scoped sessions (`/subjects/:subjectId/chat`)
   - Module-level sessions (`/ai-classroom/chat`, `subject=null`)

### Idempotency
- Use `get_or_create` / `update_or_create` for all records.
- Command should be safe to run multiple times.

### Execution
```bash
python manage.py seed_test_data
```

---

## 3. Verification
- Run `python manage.py makemigrations --check` (no new models, but verify).
- Run backend tests / lint if available.
- Frontend: `npm run typecheck` / `npm run lint`.
