# Phase 11 — Frontend UI Implementation (StudyAI Desktop Web)

Status: **Implemented** · Date: 2026-08-23 · Scope: `frontend/`

Phase 11 rebuilds the StudyAI frontend around the decided module architecture:

```
                 TRANSCRIPTION   WRITE   ENRICHMENT   TESTS   QA   CHAT
NoteSpace             ✓            ✓         ✗         ✗      ✗     ✗
AI Classroom          ✓            ✓         ✓         ✓      ✓     ✓
```

The UI consumes a per-profile **module service configuration**; components ask
"is this service enabled?" (`services.enrichment`) and never branch on "which
module am I in". Module switching (NoteSpace ↔ AI Classroom) is instant,
client-side state inside the subject workspace — no route change, no fetch,
no reload.

## Documents

| Document | Contents |
| --- | --- |
| [ASSUMPTIONS_AND_DECISIONS.md](./ASSUMPTIONS_AND_DECISIONS.md) | Assumptions (incl. backend gaps), decisions, rejected alternatives |
| [STRATEGY.md](./STRATEGY.md) | Implementation strategy, phase order, risk handling |
| [TECHNICAL_DESIGN.md](./TECHNICAL_DESIGN.md) | Architecture: types, stores, data layer, routing, components, styling |
| [TRACEABILITY.md](./TRACEABILITY.md) | Every UI rule / acceptance criterion mapped to code |

## Quick facts

- Stack: React 19 + TypeScript (strict) + Vite 7 + zustand 5 + react-router 7 + idb 8. No new runtime dependencies.
- Design system: hand-written token-based CSS (`src/app/styles.css`); visual target = Apple Notes × Notion × Linear (calm, academic, spacious).
- Verification: `npm run build` (tsc -b + vite build) and `npx vitest run` — both green; unit tests cover the folder-tree/breadcrumb engine and the module service matrix.

## New routes

```
/login  /register
/onboarding/profile   /onboarding/module   /onboarding/subjects
/subjects
/subjects/:subjectId                       (workspace, in-page module toggle)
/subjects/:subjectId/folders/:folderId     (arbitrary depth incl. __unfiled__)
/subjects/:subjectId/notes/:noteId         (Handwritten default; Enriched if service on)
/subjects/:subjectId/write                 (returns to origin on completion)
/subjects/:subjectId/tests|practice|chat   (service-gated)
```
