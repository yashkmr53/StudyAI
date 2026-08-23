# Phase 11 — Assumptions & Decisions (Frontend)

## 1. Assumptions

### A1. Backend gaps in the folder model (accepted, sealed behind a seam)
The UI spec requires folders (`Notebook` entities) that **nest to arbitrary
depth** and notes that can be **placed** into a folder or into the subject's
Unfiled bucket. The current backend has neither:

- `Notebook` (`backend/apps/notebooks/models.py`) has no `parent` field.
- `Document` has no folder/notebook linkage.

**Assumption:** Phase 11 is frontend-only. Hierarchy metadata
(`parentId`) and note placement (`NoteMeta.folderId`) persist locally in
IndexedDB (v2 stores `folders` / `notes`) while the authoritative *records*
remain real backend entities: creating a folder calls `POST /notebooks`;
subjects are always `POST /subjects`. When the backend adds `Notebook.parent`
and `Document.folder`, only `workspaceStore.loadWorkspace` reconciliation and
the create actions change — no UI component changes.

Consequence: folder hierarchy and note placement are per-device until the
backend seam is filled. This is recorded as a known limitation.

### A2. Canvas strokes are append-only server-side
`/canvas/pages/{id}/strokes` supports append; there is no read API for strokes.
Handwritten rendering therefore replays ink from local IndexedDB on the device
that wrote it. Cross-device ink rendering requires a future `GET strokes`
endpoint (backend gap, not addressed here).

Undo/eraser use **local tombstones** (`StrokeRecord.deleted_at`). The server
retains orphaned ink; rendering always filters tombstoned strokes locally.

### A3. Module/service configuration lives client-side today
There is no backend endpoint exposing `ProfileModuleConfig`. It is derived
from the fixed matrix in `types/modules.ts`, seeded by the onboarding module
choice, persisted per profile in `localStorage`
(`studyai.moduleconfig.v1`), and hydrated **once per profile session**
(`hydrateFor`). Swapping to a real endpoint later touches only
`moduleConfigStore.hydrateFor`.

### A4. "Fetched once" semantics
Module switching must not re-fetch configuration (§8). `hydrateFor` early-returns
when the active profile's config is already cached in memory for this session;
toggles write only `uiStore.activeModuleBySubject`.

### A5. Enrichment wire format parsed defensively
`GET /documents/{id}/enrichment` is loosely specified in OpenAPI. The client
(`services/api/enrichment.ts`) normalizes several plausible shapes and maps:
job running → `enriching`; `ai_stale` → `out_of_date`; blocks present →
`enriched`; else `not_enriched`. Missing/404 → `not_enriched` (never an error).

### A6. Tests/QA contracts are still loose
`/tests`, `/tests/{id}/attempts` return undocumented bodies. Clients normalize
aggressively and every screen renders honest empty/error states instead of
assuming fields exist. Test submission falls back to local grading when the
attempts endpoint does not return a score.

### A7. Practice QA aggregates per-document questions
Questions are generated per document (`/documents/{id}/questions`). The
practice page unions question sets across the subject's upload-sourced notes,
skipping failures silently. Canvas-source notes contribute once ingestion
bridges canvas sessions to documents (existing architecture §6).

### A8. Chat citations render but do not deep-link yet
Chat answers may carry citation refs; they render as chips. Deep-linking into
note pages from chat is deferred until retrieval responses consistently expose
document ids + page numbers.

### A9. Desktop-first
Per the platform brief, layout targets ≥1024px viewports with keyboard/mouse
and Apple Pencil pointer events (`pointerdown/move/up`, pressure). No mobile
bottom navigation exists anywhere.

### A10. Onboarding progress is resumable, completion is per-profile
Mid-flow refresh resumes at the last step (localStorage progress); completing
step 4 marks `studyai.onboarded.<profileId>` so returning users land directly
in `/subjects`. Switching profiles re-checks the flag per profile.

## 2. Decisions

| # | Decision | Rationale |
| --- | --- | --- |
| D1 | Service gating via context + `ServiceGate` (`components/modules/ModuleContext.tsx`) | Implements §2 literally: components ask `services.qa`, never `module === "AI_CLASSROOM"` |
| D2 | Active module = zustand `uiStore.activeModuleBySubject` | Module switching must be instant client state shared between workspace and note-detail routes, but never a route/fetch |
| D3 | Hand-crafted CSS design system instead of Tailwind | Zero new dependencies, deterministic premium aesthetic, existing codebase already plain-CSS; tokens documented in `styles.css` header |
| D4 | Folders are real `Notebook` records; hierarchy stored locally | Honors "folders are represented by the Notebook entity" while tolerating the missing parent column (A1) |
| D5 | Unfiled = virtual id `__unfiled__` rendered by the same `FolderCard`/folder route | Rule 14: looks like a normal folder because it *is* one in the UI model |
| D6 | Writing auto-creates the note record at session start; empty abandoned sessions clean up locally | Guarantees "source revision exists ⇒ handwritten view available"; avoids phantom notes |
| D7 | Return-to-origin via `location.state.returnTo` captured at Write launch | Rule 15 / §22 without extra storage or global state |
| D8 | Legacy routes (`/notespace`, `/canvas`, `/tests`, …) redirect to `/subjects` | Old links keep working; no dead feature screens |
| D9 | `ServiceRoute` guard redirects deep links to disabled services back to the workspace | Prevents landing on nonexistent features after a module switch |

## 3. Rejected alternatives

- **Tailwind CSS v4** — faster bulk styling but adds build config + dependency churn mid-phase; rejected for D3 reasons.
- **Server-side nesting via a client-maintained `parent` payload sent to `description` field** — corrupts data semantics; rejected outright in favor of A1's honest local store.
- **Persisting active module per subject across reloads** — spec treats module as session-local workspace state; persistence would surprise users who toggled temporarily. Only the profile default (from onboarding) persists.
- **Rendering Enriched tab disabled-but-visible in NoteSpace** — violates Rule 5 ("do not render the Enriched tab at all").
