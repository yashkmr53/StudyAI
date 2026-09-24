# Phase 10B — Frontend CRUD API and Store Integration Report

## 1. Executive Summary

Phase 10B connects the backend CRUD capabilities established in Phase 10A (`Document.title`, `Document.notebook`, PATCH, DELETE, `Subject` DELETE/PATCH, `ChatSession` active-profile scoping) to the frontend API clients and Zustand/IndexedDB stores.

All store actions and API clients strictly preserve profile isolation, guarantee no optimistic mutations before server confirmation, synchronize with local IndexedDB caches, and handle cascade operations cleanly.

Strict boundaries were maintained:
- No UI menus, dialogs, or delete buttons were created (strictly deferred to Phase 10C).
- No backend models, migrations, or endpoints were altered.
- All 52 frontend tests in the Vitest suite passed (100%).
- Frontend production build (`tsc -b && vite build`) succeeded with zero errors.

---

## 2. Updated API Clients

### A. Documents API (`frontend/src/services/api/documents.ts`)
- **`documentsApi.update(id, payload)`**:
  - Endpoint: `PATCH /api/v1/documents/{id}`
  - Payload: `{ title?: string; subject?: string | null; notebook?: string | null }`
  - Returns: `Promise<DocumentInfo>`
- **`documentsApi.rename(id, title)`**:
  - Calls `update(id, { title })`
  - Returns: `Promise<DocumentInfo>`
- **`documentsApi.move(id, notebookId)`**:
  - Calls `update(id, { notebook: notebookId })` (sending `null` unfiles note)
  - Returns: `Promise<DocumentInfo>`
- **`documentsApi.remove(id)`**:
  - Endpoint: `DELETE /api/v1/documents/{id}`
  - Returns: `Promise<void>`
- **`documentsApi.create(...)`**:
  - Updated to accept optional `notebookId?: string | null` and `title?: string`.

### B. Subjects API (`frontend/src/services/api/subjects.ts`)
- **`subjectsApi.rename(id, name)`**:
  - Endpoint: `PATCH /api/v1/subjects/{id}` with `{ name }`
  - Returns: `Promise<Subject>`
- **`subjectsApi.remove(id)`**:
  - Endpoint: `DELETE /api/v1/subjects/{id}`
  - Returns: `Promise<void>`

### C. Notebooks API (`frontend/src/services/api/notebooks.ts`)
- **`notebooksApi.rename(id, title)`**:
  - Endpoint: `PATCH /api/v1/notebooks/{id}` with `{ title }`
  - Returns: `Promise<void>`
- **`notebooksApi.remove(id)`**:
  - Endpoint: `DELETE /api/v1/notebooks/{id}`
  - Returns: `Promise<void>`

### D. Profiles API (`frontend/src/services/api/profiles.ts`)
- **`profilesApi.rename(id, name)`**:
  - Endpoint: `PATCH /api/v1/profiles/{id}` with `{ name }`
  - Returns: `Promise<Profile>`
- **`profilesApi.remove(id)`**:
  - Endpoint: `DELETE /api/v1/profiles/{id}`
  - Returns: `Promise<void>`

---

## 3. Store Action Implementations and Execution Sequences

### A. Note Actions (`frontend/src/state/workspaceStore.ts`)

#### 1. `renameNote(noteId, title)`
1. Trims title; if empty, aborts.
2. Checks local note record. If `source !== "canvas"`, calls `await documentsApi.rename(noteId, clean)`.
3. If the backend API call fails, the exception is thrown immediately. No local mutations occur.
4. On success, persists updated note with new title and timestamp to IndexedDB via `putNote(updated)`.
5. Updates Zustand `notes` state slice.

#### 2. `moveNote(noteId, folderId)`
1. Resolves `folderId`: empty or `"__unfiled__"` normalizes to `UNFILED_FOLDER_ID`, sending `null` to backend.
2. If `source !== "canvas"`, calls `await documentsApi.move(noteId, targetNotebook)`.
3. If the backend API call fails, the exception bubbles up without mutating local state.
4. On success, writes updated note record to IndexedDB via `putNote(updated)`.
5. Updates Zustand `notes` state slice.

#### 3. `removeNote(noteId)`
1. Checks local note record. If `source !== "canvas"`, calls `await documentsApi.remove(noteId)`.
2. On failure, throws and preserves local state and IndexedDB record.
3. On success, deletes note record from IndexedDB via `deleteNote(noteId)`.
4. Removes note from Zustand `notes` state array.
5. Recalculates subject `noteCount` via `bumpSubjectCounters`.

---

### B. Subject Actions (`frontend/src/state/workspaceStore.ts`)

#### 1. `renameSubject(id, name)`
1. Calls `await subjectsApi.rename(id, name)`.
2. On failure, throws without mutating state.
3. On success, updates matching subject in Zustand `subjects`.

#### 2. `removeSubject(id)`
1. Calls `await subjectsApi.remove(id)`.
2. Backend deletes subject, cascades to delete associated notebooks, and sets `subject = NULL` on documents.
3. On frontend, notes under this subject are preserved: their `subjectId` is set to `""` and updated in IndexedDB via `putNote`.
4. Associated folders are removed from IndexedDB via `deleteFolderTree`.
5. Zustand state removes the subject, removes all folders belonging to the subject, and updates notes to have `subjectId: ""`.

---

### C. Folder (Notebook) Actions (`frontend/src/state/workspaceStore.ts`)

#### 1. `renameFolder(id, name)`
1. Calls `await notebooksApi.rename(id, name)`.
2. On failure, throws without mutating state.
3. On success, updates folder in IndexedDB (`putFolder`) and Zustand `folders`.

#### 2. `removeFolder(id)`
1. Calls `await notebooksApi.remove(id)`.
2. On failure, throws without mutating state.
3. On success, removes folder tree from IndexedDB (`deleteFolderTree`).
4. Any child notes inside the folder are demoted to `UNFILED_FOLDER_ID` (never deleted) both in IndexedDB (`putNote`) and in Zustand.
5. Subject `folderCount` is updated.

---

### D. Profile Actions (`frontend/src/features/auth/authStore.ts`)

#### 1. `renameProfile(id, name)`
1. Calls `await profilesApi.rename(id, name)`.
2. On failure, throws.
3. On success, updates `profiles` array and active `profile` object in Zustand.

#### 2. `deleteProfile(id)`
1. Calls `await profilesApi.remove(id)`.
2. Cleans up module-specific remembered IDs (`studyai.profile.NOTE_SPACE`, `studyai.profile.AI_CLASSROOM`).
3. If the profile was active:
   - Removes `studyai.profile` from `localStorage`.
   - Clears workspace store via `useWorkspaceStore.getState().resetWorkspace()`.
   - Re-runs `refreshProfiles()` using Phase 9A active profile resolution to automatically switch to the next valid profile within the module or default.
4. If the profile was not active:
   - Removes profile from `profiles` array.

---

## 4. Local State and Cache Synchronization Strategy

### Non-Mutation Guarantee
In accordance with local-first and API integrity principles:
- **No optimistic mutations**: State changes are applied only after backend promises resolve.
- **Fail-safe error propagation**: If any HTTP request fails (4xx/5xx, network error), an error is thrown, leaving IndexedDB and Zustand in their pre-mutation state.

### Authoritative Reconciliation in `loadWorkspace`
During workspace loading:
- Backend `d.title` takes precedence over local IndexedDB title.
- Backend `d.notebook` takes precedence over local folder assignment:
  - If backend reports `notebook: null`, note is mapped to `UNFILED_FOLDER_ID`.
  - If backend reports `notebook: "<uuid>"`, note is placed in that folder.
- Authoritative remote notes are synchronized to IndexedDB in the background (`putNote`).

---

## 5. Test Suite Verification

### Vitest Test Results
```text
 ✓ tests/smoke.test.ts (1 test)
 ✓ tests/db.test.ts (1 test)
 ✓ tests/moduleConfig.test.ts (4 tests)
 ✓ tests/folderTree.test.ts (9 tests)
 ✓ tests/phase9aProfileIsolation.test.ts (8 tests)
 ✓ tests/phase9Flow.test.ts (11 tests)
 ✓ tests/crudStoreIntegration.test.ts (18 tests)

Test Files  7 passed (7)
     Tests  52 passed (52)
  Duration  488ms
```

### Production Build Verification
```text
> tsc -b && vite build
✓ built in 726ms
dist/index.html                                    0.51 kB │ gzip:   0.31 kB
dist/assets/index-sdj9EycC.css                    34.10 kB │ gzip:   6.79 kB
dist/assets/workbox-window.prod.es5-BBnX5xw4.js    5.75 kB │ gzip:   2.36 kB
dist/assets/index-Nk9TZAtF.js                    428.64 kB │ gzip: 131.48 kB
```

### Backend Regressions
- `backend/tests/api/test_crud_phase10a.py`: 24 passed out of 24 (100%).

---

## 6. Scope Remaining for Phase 10C

Phase 10B intentionally contained no presentation changes. Phase 10C will build the user-facing CRUD interactions:
1. **Note UI**:
   - Rename action (inline title edit or modal).
   - Move note modal / folder picker.
   - Delete note confirmation dialog.
2. **Folder UI**:
   - Rename folder dialog/popover.
   - Delete folder confirmation dialog (informing user that notes will become unfiled).
3. **Subject UI**:
   - Rename subject inline or modal.
   - Delete subject confirmation dialog (with warning about cascading folder deletion and unfiled notes).
4. **Profile UI**:
   - Rename profile option in profile switcher.
   - Delete profile option with safety guard (e.g., prevent deleting if only one profile remains).
5. **Toast/Feedback Notifications**:
   - Success and failure notifications for CRUD operations.

---

PHASE 10B COMPLETE
