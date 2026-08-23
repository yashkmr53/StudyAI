# Phase 11 — Technical Design (Frontend)

## 1. Layered architecture

```
┌────────────────────────────────────────────────────────────┐
│ Screens / Components                                       │
│ subjects · folders · notes · writing · tests · practice    │
│ consume services via context; zero module-name branching   │
├────────────────────────────────────────────────────────────┤
│ State (zustand)                                            │
│ authStore      session, profiles, active profile           │
│ moduleConfigStore  ProfileModuleConfig, once-per-session   │
│ uiStore        activeModuleBySubject (client-side toggle)  │
│ workspaceStore subjects, folders, notes + actions          │
│ canvasStore    writing sessions, pages, lock fencing       │
│ outboxStore    offline sync counters                       │
├────────────────────────────────────────────────────────────┤
│ Services                                                   │
│ api/: profiles subjects notebooks documents canvas         │
│       enrichment questions chat tests (+pagination utils)  │
│ repositories seam: workspaceStore reconciles remote        │
│ records with local hierarchy/placement (A1)                │
│ sync/: outbox engine (strokes.append, fenced)              │
├────────────────────────────────────────────────────────────┤
│ Persistence                                                │
│ IndexedDB "studyai" v2: strokes · outbox · folders ·       │
│ notes · kv          localStorage: tokens, module config,   │
│ onboarding flags, device id                         │
└────────────────────────────────────────────────────────────┘
```

## 2. Module service model

```ts
// types/modules.ts — single source of truth
MODULE_SERVICE_MATRIX: Record<ModuleId, ModuleServiceConfig>
NOTE_SPACE:    { transcription ✓, write ✓, everything else ✗ }
AI_CLASSROOM:  { all ✓ }

// state/moduleConfigStore.ts
hydrateFor(profileId)     // once per profile session (A3/A4)
configFor(profileId)      // selector used by useSubjectModule
servicesFor / hasService  // pure helpers
```

Consumption patterns:

- `SubjectWorkspace` wraps its tree in `ModuleProvider` → descendants call
  `useServices()` and `ServiceGate service="qa"`.
- Route-level pages (note detail, tests, practice, chat) call
  `useSubjectModule(subjectId)` which merges the profile default with the
  client-side override in `uiStore`.

## 3. Routing & guards (`routes/index.tsx`)

| Guard | Behavior |
| --- | --- |
| `RequireAuth` | restores JWT session, loads workspace for active profile, resets it on sign-out |
| `RequireOnboarding` | routes fresh accounts through steps; resumable via progress record |
| `RootRedirect` | `/` → next onboarding step or `/subjects` based on per-profile flag |
| `ServiceRoute` | deep links to tests/practice/chat resolve against the **active** module's services; disabled → redirect to workspace |

Module toggle is *not* routed: `ModuleToggle` writes `uiStore`, the workspace
re-renders instantly. No fetch, no reload, no loading screen (§8).

## 4. Workspace data model

- `NoteMeta { id, refId, subjectId, folderId|null, source: canvas|upload, … }`
  — `folderId === null || "__unfiled__"` ⇒ Unfiled bucket.
- `FolderNode { id (= notebook id), subjectId, parentId|null, name }`.
- Reconciliation on load: backend subjects+notebooks ⊕ local hierarchy
  records → store; offline-created folders survive until backend sync exists.
- Pure tree utilities (`utils/folderTree.ts`): `folderPath`,
  `breadcrumbCrumbs`, `childrenOf`, `descendantIds`, `wouldCycle`,
  `countNotesRecursive` — unit-tested.

## 5. Note detail state machine

```
landing ──► Handwritten tab (always; Rule 9)
              ├ canvas note  → ink replay from IDB (zoom, page nav)
              └ upload note  → page image (image_ref if present)
                              + faithful transcription lines
Enriched tab rendered iff services.enrichment (Rule 5)
  states (§19): not_enriched → [Generate]
                enriching    → progress panel + poll (2.5s, bounded)
                enriched     → blocks + citation chips
                out_of_date  → stale banner + [Regenerate] over content
                failed       → friendly error + [Try Again]
Citation chip (§18): setTab(handwritten) + setPage(n) + highlight pulse
Module switch while viewing Enriched (§20):
  effect falls back to Handwritten silently when enrichment turns off
```

## 6. Writing flow

- Launch sites pass `{ returnTo, folderId? }`; subject-level ⇒ Unfiled
  (Rule 13), folder-level ⇒ that folder.
- Boot: ensureDevice → create canvas session → register local NoteMeta;
  StrictMode double-mount guarded by ref (D6).
- Ink: pointer events with pressure; strokes persisted to IndexedDB first,
  outbox queues fenced `strokes.append` batches (existing §4/§5 engine kept).
- Tools: pen (pressure-modulated width), highlighter (translucent), eraser
  (segment hit-test tombstoning), undo/redo as op stacks over tombstones,
  per-page tabs, finalize-on-Done.
- Completion: flush outbox → `reset()` → `navigate(returnTo)` (Rule 15).

## 7. Design system (`app/styles.css`)

Token-driven single stylesheet: color/radius/shadow/motion custom properties;
component classes prefixed by domain (`.sidebar__*`, `.subject-card*`,
`.enriched-*`, `.writer-*`). Subtle elevation only; 130–160ms transitions;
`prefers-reduced-motion` honored; focus-visible rings; CSS-only tooltips via
`[data-tip]`. Light sidebar shell per Apple Notes/Notion feel.

## 8. Accessibility

Semantic landmarks (`nav aria-label`), `role=tablist/tab/tabpanel` for module
toggle and note tabs, `aria-checked` radio groups for options, dialog focus
trapping basics (initial focus, Escape), disabled states carried to inputs,
icon-only buttons labeled via `aria-label` + tooltip.

## 9. File map (new or rewritten)

```
src/
├── app/styles.css                        design system (rewritten)
├── routes/index.tsx                      full route overhaul
├── types/{modules,domain}.ts             service matrix + UI domain model
├── db/indexeddb/db.ts                    v2 stores + stroke metadata/tombstones
├── state/
│   ├── moduleConfigStore.ts              once-per-session profile config
│   ├── uiStore.ts                        active module per subject
│   └── workspaceStore.ts                 subjects/folders/notes + reconciliation
├── services/api/
│   ├── pagination.ts  profiles.ts  subjects.ts  notebooks.ts
│   ├── enrichment.ts  questions.ts chat.ts      tests.ts
├── components/
│   ├── layout/{AppShell,Sidebar,Breadcrumbs}.tsx
│   ├── ui/{icons,primitives}.tsx         dialogs, empty/error/skeletons, chips
│   ├── modules/{ModuleContext,ModuleToggle,ServiceCard}.tsx
│   ├── subjects/{SubjectsPage,SubjectCard,NewSubjectDialog,SubjectWorkspace}.tsx
│   ├── folders/{FolderCard,NewFolderDialog,FolderDetailPage}.tsx
│   ├── notes/{NoteRow,HandwrittenView,EnrichedView,NoteDetailPage}.tsx
│   ├── tests/TestsPage.tsx  practice/PracticePage.tsx  chat/ChatPage.tsx
├── features/
│   ├── auth/{LoginPage,RegisterPage,authStore}   polished + multi-profile
│   ├── onboarding/*                      4-step flow + progress persistence
│   └── writing/{WritingPage,WritingToolbar,ink}.ts*
└── utils/folderTree.ts                   pure tree/breadcrumb helpers
tests/
├── smoke.test.ts                          (kept, passing)
├── folderTree.test.ts                     nesting/breadcrumbs/cycles
└── moduleConfig.test.ts                   acceptance-criteria matrix
```
