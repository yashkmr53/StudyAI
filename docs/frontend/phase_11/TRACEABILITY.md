# Phase 11 — Traceability (UI Rules & Acceptance Criteria → Code)

Every rule from the implementation brief maps to a concrete artifact.

## Module matrix

| Criterion | Where enforced |
| --- | --- |
| NoteSpace has transcription | `MODULE_SERVICE_MATRIX.NOTE_SPACE.transcription = true` (`types/modules.ts`) |
| NoteSpace has writing | `.write = true`; Write button/flow available in both modules (`SubjectWorkspace`, `FolderDetailPage`, `WritingPage`) |
| NoteSpace has NO enrichment | `.enrichment = false`; Enriched tab not rendered (`NoteDetailPage`), enrichment chips never shown (`NoteRow`), no AI empty states in NoteSpace paths |
| NoteSpace has NO tests/QA/chat | matrix false; cards gated by `ServiceGate` (`SubjectWorkspace`); routes guarded by `ServiceRoute` (`routes/index.tsx`) |
| AI Classroom has transcription + writing | matrix true; shared Handwritten view + Write flow |
| AI Classroom has enrichment/tests/QA/chat | matrix all-true; asserted by `tests/moduleConfig.test.ts` |

## UI rules

| Rule | Implementation |
| --- | --- |
| 1 — No AI features in NoteSpace | Service gates render nothing when disabled; `ServiceRoute` redirects deep links; verified visually via toggle |
| 2 — AI features in AI Classroom | `ai-banner` cards for QA/Tests/Chat, each individually gated (`SubjectWorkspace.tsx`) |
| 3 — Both modules support transcription | Handwritten/transcription views module-independent (`HandwrittenView.tsx`) |
| 4 — Both modules support write | Write buttons outside any gate; `WritingPage` independent of module |
| 5 — Enriched tab conditional on EnrichmentService | `services.enrichment ? <tabs…/> : null` (`NoteDetailPage.tsx:~120`) |
| 6 — Tests conditional on TestsService | card gate + `ServiceRoute service="tests"` |
| 7 — Practice QA conditional on QAService | card gate + `ServiceRoute service="qa"` |
| 8 — Chat conditional on ChatService | card gate + `ServiceRoute service="chat"` |
| 9 — Handwritten default tab | `useState<"handwritten" | "enriched">("handwritten")` (`NoteDetailPage.tsx`) |
| 10 — Module switching client-side & instant | `ModuleToggle → uiStore.setActiveModule`; config cache guard `hydrateFor` early-return (`moduleConfigStore.ts`) |
| 11 — Folders nest arbitrarily | `FolderNode.parentId`, recursive utilities (`utils/folderTree.ts`), tested to depth 5 |
| 12 — Breadcrumbs arbitrary depth | `breadcrumbCrumbs` emits one crumb per ancestor; used by workspace/folder/note pages |
| 13 — Subject-level Write → Unfiled | launch omits `folderId` ⇒ `UNFILED_FOLDER_ID` (`SubjectWorkspace.tsx` → `WritingPage.boot`) |
| 14 — Unfiled looks like a normal folder | same `FolderCard` component, same folder route (`FolderDetailPage` handles `__unfiled__`) |
| 15 — Write returns to origin | `location.state.returnTo` captured at every launch site; `finishWriting()` navigates back (`WritingPage.tsx`) |
| 16 — No starter folders/notes created | Onboarding creates only Subjects (`SubjectsStep.tsx`); empty states invite first action instead |

## Acceptance criteria spot-checks

| Criterion | Evidence |
| --- | --- |
| Switching modules does not reload page / refetch config / lose subject | No route change; `hydrateFor` idempotent per session; subject stays mounted; unit-tested config caching semantics |
| Enriched shows in-progress state | `EnrichedView` enriching panel with animated indicator + polling |
| Enriched shows out-of-date state | stale banner + Regenerate over content, driven by `ai_stale` mapping |
| Citation chips navigate back to source | `onCitation(page)` → Handwritten tab, page set, highlight pulse (`source-page.highlighted`) |
| Tests/QA/Chat are not sidebar navigation items | Sidebar contains brand, subjects, add-subject, profile switcher only (`Sidebar.tsx`) |
| Only Subject records during onboarding | Step 4 calls `createSubject` exclusively (`SubjectsStep.tsx`) |

## Verification record (2026-08-23)

```
npx tsc -b          → 0 errors
npm run build       → built in ~0.7s (PWA precache generated)
npx vitest run      → 3 files, 14 tests passed
  smoke.test.ts        1 passed
  folderTree.test.ts   9 passed  (nesting, breadcrumbs, cycles, counts)
  moduleConfig.test.ts 4 passed  (acceptance-criteria matrix)
```

## Known limitations (documented in assumptions)

- Folder hierarchy + note placement are device-local until backend adds
  `Notebook.parent` / `Document.folder` (A1).
- Cross-device ink rendering awaits a server stroke-read endpoint (A2).
- Undo/eraser tombstones are local; server retains orphaned ink (A2).
- Test/QA screens degrade gracefully where backend contracts are still loose (A6/A7).
