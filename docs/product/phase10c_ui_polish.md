# Phase 10C — Focused UI Polish Verification

## Overview

Following the Phase 10C CRUD implementation, two focused UI defects were identified in the user experience:

1. **Issue 1 — CRUD `ActionMenu` overlaps the sidebar**:
   - On the Subject and Folder pages, the 3-dot `ActionMenu` opened to the left with `right: 0`, expanding directly across the boundary between the workspace and the permanent sidebar and overlapping the sidebar.
2. **Issue 2 — Note-page tooltips not visible**:
   - On the Note page document viewer, the navigation (`‹`, `›`) and zoom (`−`, `+`) controls had `data-tip` attributes defined, but tooltips failed to render on hover and keyboard focus due to parent container `overflow: hidden` clipping, missing `:focus-visible` pseudo-class selectors, and lack of downward positioning.

Both issues have been resolved without changing existing CRUD architecture, API clients, or backend models.

---

## 1. Issue 1 — ActionMenu Sidebar Overlap

### 1.1 Root Cause Analysis

In `frontend/src/app/styles.css`:
- `.action-menu__dropdown` was statically defined with `position: absolute; top: 100%; right: 0; min-width: 160px;`.
- Setting `right: 0` forces the dropdown's right edge to align with the trigger button's right edge, expanding leftward into negative x relative to the button.
- On the **Subject page** (`SubjectWorkspace.tsx`) and **Folder page** (`FolderDetailPage.tsx`), the 3-dots trigger button is positioned immediately adjacent to the `<h1>` title on the left side of the workspace.
- The sidebar right edge is situated at `x = 248px`. The button right edge for a short title is located at `x ≈ 390px`. Expanding 160px to the left placed the dropdown left edge at `x = 230.15px`.
- Because `230.15px < 248px`, the menu overlapped the permanent sidebar by **17.85px** (and significantly more on shorter titles).

### 1.2 Solution: Dynamic Bounds-Aware Positioning

We updated [ActionMenu.tsx](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/ui/ActionMenu.tsx) and [styles.css](file:///Users/yash/CV_Project/StudyAI/frontend/src/app/styles.css) with an intelligent, dynamic boundary calculation:

1. **Horizontal Alignment Logic**:
   - Measure `containerRef.current.getBoundingClientRect()`.
   - Detect distance to the permanent sidebar: `sidebarRight = sidebar.getBoundingClientRect().right` (if outside sidebar).
   - If opening to the left would cross into the sidebar (`rect.right - MENU_MIN_WIDTH < sidebarRight + padding`), alignment is strictly forced to `"left"` (`left: 0; right: auto`). The menu expands rightward into the spacious workspace.
   - If near the right edge of the viewport (such as in `NoteDetailPage` or table `NoteRow`), alignment switches to `"right"` (`right: 0; left: auto`), expanding leftward into the workspace.
2. **Vertical Placement Flipping**:
   - If viewport bottom space is below 160px and top space is greater, the menu flips upward (`placement: "top"`: `bottom: 100%; top: auto; margin-bottom: 4px;`).
3. **Viewport Clamping for Narrow/Mobile Viewports**:
   - When horizontal space in the workspace is tight (e.g., 375px mobile viewports with a 248px permanent sidebar), the menu calculates the exact safe boundary `[minAllowedLeft, maxAllowedRight]`.
   - Sets `style.maxWidth = Math.min(260, maxAvailableWidth)` and shifts left by `overflow` without crossing `minAllowedLeft`.
   - Adds responsive item wrapping (`@media (max-width: 600px) { .action-menu__item { white-space: normal; word-break: break-word; } }`).
   - Ensures the menu never overlaps the sidebar (`menuLeft >= sidebarRight`) AND never overflows the right viewport edge (`menuRight <= windowWidth`).
4. **Preserved Behaviors**:
   - Dimensions, animations (`pop-in 100ms`), icons, dangerous item styling, keyboard `Escape` dismissal, click-outside handling, and active states remain fully intact.
   - Added tooltip accessibility: `data-tip={open ? undefined : ariaLabel}` on the trigger button.

### 1.3 Verification Metrics

| Metric | Before Fix | After Fix (Desktop 1280px) | After Fix (Mobile 375px) | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sidebar Right Boundary** | `248px` | `248px` | `248px` | Baseline |
| **Subject Menu Left Edge** | `230.15px` | `360.16px` | `256.00px` | **No Overlap (+112px separation desktop, +8px mobile)** |
| **Subject Menu Right Edge**| `390.15px` | `520.16px` | `367.00px` | **Contained within viewport (<= 375px)** |
| **Folder Menu Left Edge**  | Overlapped | `435.72px` | N/A | **No Overlap (+187.7px separation)** |
| **Note Menu (Top Right)**  | `1088px`   | `1088px`   | N/A | **Contained (menuRight = 1248px <= 1280px)** |

---

## 2. Issue 2 — Note-Page Tooltips Visibility

### 2.1 Root Cause Analysis

In `HandwrittenView.tsx`, the document viewer controls were configured with `data-tip`:
- Previous page: `data-tip={t("notes.handwritten.prevPage")}`
- Next page: `data-tip={t("notes.handwritten.nextPage")}`
- Zoom out: `data-tip={t("notes.handwritten.zoomOut")}`
- Zoom in: `data-tip={t("notes.handwritten.zoomIn")}`

However, tooltips did not appear due to three compounding causes:
1. **Container Overflow Clipping**:
   - In `styles.css`, `.source-page` was styled with `overflow: hidden;`.
   - Tooltips were styled with `bottom: calc(100% + 7px); left: 50%; transform: translateX(-50%);`.
   - Because `.source-page__header` is the first element at `y = 0` inside `.source-page`, placing the tooltip 7px above the button located it at negative y coordinates relative to `.source-page`.
   - `overflow: hidden` on `.source-page` clipped the tooltip entirely.
2. **Missing Focus Selector**:
   - `[data-tip]` only matched `:hover::after` and `:hover::before`.
   - Keyboard navigation via `Tab` never triggered `:focus-visible` or `:focus`, preventing accessibility.
3. **No Downward Placement Support**:
   - Elements positioned in top header bars naturally benefit from downward tooltips to avoid colliding with top navigation tabs or headers.

### 2.2 Solution: Non-Clipping Hierarchy & Enhanced Tooltip Styling

1. **Removed Container Clipping**:
   - Changed `.source-page` overflow from `hidden` to `visible`.
   - Explicitly rounded top corners on `.source-page__header` (`border-top-left-radius: calc(var(--radius-lg) - 1px); border-top-right-radius: calc(var(--radius-lg) - 1px);`).
   - Explicitly rounded bottom corners on `.source-page > :last-child` (`border-bottom-left-radius` / `border-bottom-right-radius`).
   - Preserves card corner styling without clipping tooltips or dropdowns.
2. **Downward Tooltip Support for Header Controls**:
   - Added downward tooltip styling for header controls and elements with `[data-tip-pos="bottom"]`:
     ```css
     [data-tip][data-tip-pos="bottom"]:hover::after,
     [data-tip][data-tip-pos="bottom"]:focus-visible::after,
     .source-page__header [data-tip]:hover::after,
     .source-page__header [data-tip]:focus-visible::after {
       top: calc(100% + 7px);
       bottom: auto;
     }

     [data-tip][data-tip-pos="bottom"]:hover::before,
     [data-tip][data-tip-pos="bottom"]:focus-visible::before,
     .source-page__header [data-tip]:hover::before,
     .source-page__header [data-tip]:focus-visible::before {
       top: calc(100% + 3px);
       bottom: auto;
       transform: translateX(-50%) rotate(45deg);
     }
     ```
3. **Keyboard Focus Accessibility**:
   - Added `[data-tip]:focus-visible::after` and `[data-tip]:focus-visible::before`.
   - Tooltips appear cleanly on both mouse `:hover` and keyboard `:focus-visible`.
4. **Stacking Context & Z-Index Elevation**:
   - Set `position: relative; z-index: 10;` on `.source-page__header`.
   - Increased tooltip `z-index` to `120` (`119` for arrow), ensuring tooltips render cleanly over note canvas ink and document scan images.

### 2.3 Verification Metrics

| Control | Tooltip Text | Hover Display | Top Coordinate | Focus-Visible | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **‹ (Previous Page)** | `"Previous page"` | `block` | `top: 37px` | Supported | **Verified Visible** |
| **› (Next Page)**     | `"Next page"`     | `block` | `top: 37px` | Supported | **Verified Visible** |
| **− (Zoom Out)**      | `"Zoom out"`      | `block` | `top: 37px` | Supported | **Verified Visible** |
| **+ (Zoom In)**       | `"Zoom in"`       | `block` | `top: 37px` | Supported | **Verified Visible** |

---

## 3. Test Verification & Visual Artifacts

### 3.1 Automated E2E Suite (`frontend/tests/e2e/test_ui_polish.mjs`)
Run command:
```bash
node tests/e2e/test_ui_polish.mjs
```
Output:
```text
Navigating to login...
Initial profile: YashAI
Found subject ActionMenu button. Clicking it...
Subject Menu bounds: {
  sidebarRight: 248,
  menuLeft: 360.15625,
  menuRight: 520.15625,
  btnLeft: 360.15625,
  btnRight: 390.15625
}
✅ No overlap: Menu left (360.15625px) >= sidebar right (248px)
Creating a test folder 'Week 1 - Trees'...
Navigating into 'Week 1 - Trees' folder...
Testing folder ActionMenu positioning...
Folder Menu bounds: {
  sidebarRight: 248,
  menuLeft: 435.71875,
  menuRight: 595.71875,
  btnLeft: 435.71875
}
✅ Folder menu No overlap: menuLeft (435.71875px) >= sidebarRight (248px)
Navigating to Unfiled folder to open note...
Viewer controls found in .source-page__header: {
  sourcePageOverflow: 'visible',
  buttons: [
    { index: 0, text: '‹', ariaLabel: 'Previous page', dataTip: 'Previous page', disabled: true },
    { index: 1, text: '›', ariaLabel: 'Next page', dataTip: 'Next page', disabled: true },
    { index: 2, text: '−', ariaLabel: 'Zoom out', dataTip: 'Zoom out', disabled: false },
    { index: 3, text: '+', ariaLabel: 'Zoom in', dataTip: 'Zoom in', disabled: false }
  ]
}
Control [Previous page] hover tooltip: { content: '"Previous page"', display: 'block', top: '37px', zIndex: '120' }
Control [Next page] hover tooltip: { content: '"Next page"', display: 'block', top: '37px', zIndex: '120' }
Control [Zoom out] hover tooltip: { content: '"Zoom out"', display: 'block', top: '37px', zIndex: '120' }
Control [Zoom in] hover tooltip: { content: '"Zoom in"', display: 'block', top: '37px', zIndex: '120' }
Testing Note Detail page ActionMenu (top right)...
Note ActionMenu bounds: { windowWidth: 1280, menuLeft: 1088, menuRight: 1248, btnRight: 1248 }
✅ Note menu contained within viewport: menuRight (1248px) <= windowWidth (1280px)
Testing narrow mobile layout (375x667)...
Mobile ActionMenu bounds: { windowWidth: 375, menuLeft: 256, menuRight: 367 }
✅ Mobile ActionMenu fits cleanly inside viewport!
```

### 3.2 Visual Screenshots Generated
1. `02_subject_menu_opened.png`: Subject 3-dot dropdown opening cleanly to the right into the workspace, completely clear of the left sidebar.
2. `04_folder_menu_opened.png`: Folder 3-dot dropdown positioned cleanly in the workspace.
3. `06_note_zoom_in_hover.png`: Zoom in control showing the crisp dark tooltip badge with directional arrow pointing to the `+` button.
4. `08_note_menu_opened.png`: Note detail header ActionMenu opening cleanly to the left, inside the workspace.
5. `09_mobile_action_menu.png`: Mobile 375px viewport test showing ActionMenu contained between sidebar (248px) and viewport edge (375px) without overflowing either.

### 3.3 Unit Test Suite
Run command:
```bash
npm test
```
Result:
```text
✓ tests/moduleConfig.test.ts (4 tests)
✓ tests/db.test.ts (1 test)
✓ tests/folderTree.test.ts (9 tests)
✓ tests/phase9aProfileIsolation.test.ts (8 tests)
✓ tests/crudUIFlow.test.ts (4 tests)
✓ tests/phase9Flow.test.ts (11 tests)
✓ tests/crudStoreIntegration.test.ts (18 tests)
✓ tests/smoke.test.ts (1 test)

Test Files  8 passed (8)
Tests       56 passed (56)
Duration    483ms
```

### 3.4 Production Build
Run command:
```bash
npm run build
```
Result:
```text
✓ built in 809ms (0 errors)
```

## 4. Typography, Profile Switcher Layout & Universal Truncation

### 4.1 Profile Button Layout & Separation
- **Previous State**: `.profile-button__meta` was an inline `<span>` containing two child inline `<span>`s (`.profile-button__name` and `.profile-button__hint`), causing the profile name and "Switch profile" hint to collapse together into a single jammed string (`"YashAISwitch profile"`).
- **Fix**:
  - Configured `.profile-button__meta` as `display: flex; flex-direction: column; text-align: left; min-width: 0; flex: 1;`.
  - Configured `.profile-button__name` as `display: block; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;`.
  - Configured `.profile-button__hint` as `display: block; font-size: 11.5px; color: var(--text-tertiary); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;`.
  - Result: Profile name sits on the primary line with the subtitle "Switch profile" neatly stacked underneath.

### 4.2 Universal Truncation & Hover Disclosure
To prevent layout overflow on long titles and ensure full accessibility:
1. **Utility Class**: Added `.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }` in `styles.css`.
2. **Sidebar Subjects & Profiles**: Added `title={subject.name}` to sidebar subject navigation and `title={p.name}` to profile switcher items.
3. **Folder Cards**: Added `title={folder.name}` to `.folder-card__name`.
4. **Breadcrumbs**: Added `title={crumb.label}` to both `.breadcrumbs__current` and `.breadcrumbs__link`.
5. **Note Rows**: Added ellipsis truncation to `.note-row__title` and attached `title={note.title}`.
6. **Workspace & Detail Headings**: Applied `.truncate` and `title={...}` on `<h1>` headings across `SubjectWorkspace`, `FolderDetailPage`, and `NoteDetailPage`.
7. **Tooltip Gliding Fix**: Replaced keyframe property collision (`pop-in` overriding `translateX(-50%)`) with `tooltip-fade-in 80ms ease-out` on both `::after` and `::before`.

---

PHASE 10C UI POLISH COMPLETE
