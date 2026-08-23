# Phase 11 — Implementation Strategy (Frontend)

## Guiding principles

1. **Architecture first, screens second.** The module/service model
   (`types/modules.ts`, `ModuleContext`, `ServiceGate`) was built before any
   screen, so every later component consumed the same contract and no screen
   ever branched on module identity.
2. **Consume services; don't own them.** UI components render states; HTTP and
   IndexedDB live exclusively in `services/api/*`, `services/sync/*` and
   `db/indexeddb`.
3. **Backend gaps get seams, not hacks.** Missing backend fields (folder
   nesting, note placement) are isolated in the workspace store's
   reconciliation layer with a documented swap-in point.
4. **Honest states everywhere.** Every async surface has loading skeleton,
   empty state and error-with-retry. AI generation never shows a blank page.

## Build order (mirrors the brief §34)

| Phase | Delivered |
| --- | --- |
| 1 — Shell | Login/Register polish, AppShell + Sidebar (subjects + profile switcher only), Subjects grid, Subject workspace |
| 2 — Modules | `ModuleId`/`ModuleServiceConfig` matrix, once-per-session config store, `ModuleToggle`, `ServiceGate`/`useServices`/`useSubjectModule`, service-gated route guards |
| 3 — Folders | Folder grid/cards, arbitrary-depth tree utilities, full-depth breadcrumbs, New Folder dialog with parent picker + cycle guard, Unfiled as a normal folder |
| 4 — Notes | Note rows w/ module-aware status chips, Note detail (Handwritten default / Enriched gated), canvas ink replay + scan/transcription views, zoom + page nav, enrichment state machine, citation → source navigation with page highlight |
| 5 — Writing | Reused offline canvas engine (heartbeat, fencing, outbox), new toolbar: pen/highlighter/eraser, pressure-sensitive widths, color/size pickers, undo/redo, page tabs, Done → return to origin |
| 6 — AI Classroom | Tests list + runner (+ mastery bar, local-grading fallback), Practice QA session runner, Chat two-pane client with optimistic send |
| 7 — Polish | Skeletons, empty/error states, focus-visible rings, aria roles, tooltips (`data-tip`), keyboard shortcuts (⌘Z/⇧⌘Z/P/H/E), reduced-motion support, dialog focus management |

## Risk handling

- **Loose API contracts** (tests/enrichment/chat): defensive normalizers +
  graceful degradation to empty states; failures never crash a screen.
- **StrictMode double-mount**: writing session boot guarded by ref so only one
  canvas session/note is created per Write launch.
- **Deep links after module switch**: `ServiceRoute` bounces disabled-service
  routes back to the workspace rather than rendering dead features.

## Verification strategy

- `npx tsc -b` — strict type safety across the app (passes).
- `vite build` — production bundle + PWA precache (passes).
- `vitest` — unit coverage of the two highest-risk pure layers: folder-tree /
  breadcrumb engine (9 tests) and the acceptance-criteria service matrix
  (4 tests). 14/14 passing.
- Manual smoke via dev server for route transforms (all modules resolve).
