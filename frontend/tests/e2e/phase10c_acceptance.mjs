import puppeteer from "puppeteer-core";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, "screenshots", "phase10c");
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP_URL = "http://localhost:5173";
const NOTE_IMAGE_PATH = path.join(__dirname, "fixtures", "handwritten_dsa_note.png");

// Telemetry & metrics
const consoleLogs = [];
const networkRequests = [];
const failedRequests = [];
const enrichmentProgression = [];

function log(msg) {
  const ts = new Date().toISOString().substring(11, 23);
  console.log(`[${ts}] ${msg}`);
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function clearAndType(page, selector, text) {
  await page.waitForSelector(selector, { timeout: 5000 });
  await page.$eval(selector, (el) => {
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.type(selector, text);
}

async function runE2E() {
  log("==============================================================");
  log("=== Starting Phase 10C Browser E2E Acceptance Test ===");
  log("==============================================================");

  const results = {
    startedAt: new Date().toISOString(),
    steps: {},
    metrics: {},
    checklist: {},
  };

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    defaultViewport: { width: 1366, height: 900 },
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage();

  page.on("console", (msg) => {
    const text = msg.text();
    const type = msg.type();
    consoleLogs.push({ type, text, time: new Date().toISOString() });
    if (type === "error") {
      log(`[Browser Console Error] ${text}`);
    }
  });

  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/api/")) {
      networkRequests.push({
        method: req.method(),
        url,
        time: new Date().toISOString(),
      });
    }
  });

  page.on("response", async (res) => {
    const url = res.url();
    const status = res.status();
    if (url.includes("/api/")) {
      if (status >= 400 && !url.includes("/enrichment")) {
        failedRequests.push({
          status,
          url,
          time: new Date().toISOString(),
        });
        log(`[Network Error] ${status} ${url}`);
      }
      if (url.includes("/enrichment")) {
        enrichmentProgression.push({
          status,
          time: new Date().toISOString(),
        });
      }
    }
  });

  try {
    // -------------------------------------------------------------
    // Step 1: Clean Session & Authenticate as admin@studyai.dev
    // -------------------------------------------------------------
    log("Step 1: Clean session & Authenticate as admin@studyai.dev");
    await page.goto(`${APP_URL}/login`, { waitUntil: "networkidle2" });

    // Set AI_CLASSROOM as the desired initial module
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
      localStorage.setItem("studyai.module", "AI_CLASSROOM");
    });
    await page.reload({ waitUntil: "networkidle2" });

    await page.waitForSelector("#login-email", { timeout: 10000 });
    await page.type("#login-email", "admin@studyai.dev");
    await page.type("#login-password", "AdminPass123!");
    await page.click('button[type="submit"]');

    await page.waitForFunction(
      () => window.location.pathname.startsWith("/subjects"),
      { timeout: 15000 }
    );
    await page.waitForSelector(".sidebar", { timeout: 10000 });

    // Verify session
    let session = await page.evaluate(() => {
      const auth = JSON.parse(localStorage.getItem("studyai.auth") || "{}");
      const currentModule = localStorage.getItem("studyai.module");
      const profileName = document.querySelector(".profile-button__name")?.textContent?.trim();
      return { profileId: auth.profileId, email: auth.email, module: currentModule, profileName };
    });

    log(`Initial session state: profile=${session.profileName}, module=${session.module}`);

    if (session.profileName !== "YashAI") {
      log("Switching to YashAI in AI_CLASSROOM...");
      await page.click(".profile-button");
      await page.waitForSelector(".popover", { timeout: 5000 });

      // Click AI Classroom tab in switcher
      await page.evaluate(() => {
        const tabs = Array.from(document.querySelectorAll('.segmented button[role="tab"]'));
        const classroomTab = tabs.find((t) => t.textContent?.includes("AI Classroom"));
        classroomTab?.click();
      });
      await sleep(600);

      // Click the YashAI menuitemradio
      await page.waitForSelector('.popover [role="menuitemradio"]', { timeout: 5000 });
      await page.evaluate(() => {
        const radios = Array.from(document.querySelectorAll('.popover [role="menuitemradio"]'));
        const yashAi = radios.find((r) => r.textContent?.includes("YashAI"));
        yashAi?.click();
      });

      await page.waitForFunction(
        () => document.querySelector(".profile-button__name")?.textContent?.trim() === "YashAI",
        { timeout: 10000 }
      );
      log("Successfully switched active profile to YashAI.");
    }

    session = await page.evaluate(() => {
      const auth = JSON.parse(localStorage.getItem("studyai.auth") || "{}");
      const currentModule = localStorage.getItem("studyai.module");
      const profileName = document.querySelector(".profile-button__name")?.textContent?.trim();
      return { profileId: auth.profileId, email: auth.email, module: currentModule, profileName };
    });
    log(`Confirmed active profile: ${session.profileName} (module: ${session.module})`);
    results.checklist.authenticatedClassroomProfile = session.module === "AI_CLASSROOM";

    // -------------------------------------------------------------
    // Step 2: Open Subject Workspace (DSA AI)
    // -------------------------------------------------------------
    log("Step 2: Navigate to DSA AI Subject");
    await page.waitForSelector(".sidebar__item", { timeout: 10000 });
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".sidebar__item"));
      const dsa = items.find((i) => i.textContent?.includes("DSA"));
      dsa?.click();
    });

    await page.waitForFunction(
      () => window.location.pathname.startsWith("/subjects/"),
      { timeout: 10000 }
    );
    await page.waitForSelector(".page-heading h1", { timeout: 10000 });
    const currentSubjectName = await page.evaluate(() => document.querySelector(".page-heading h1")?.textContent?.trim());
    const subjectUrl = await page.evaluate(() => window.location.href);
    log(`Opened subject workspace: "${currentSubjectName}" at ${subjectUrl}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_subject_workspace.png") });
    results.checklist.subjectWorkspaceLoaded = true;

    // -------------------------------------------------------------
    // Step 3: Upload Note & Note CRUD (Rename)
    // -------------------------------------------------------------
    log("Step 3: Upload handwritten note (handwritten_dsa_note.png)");
    const fileInput = await page.waitForSelector('input[type="file"][accept*="image"]', { timeout: 5000 });

    const [uploadRequest] = await Promise.all([
      page.waitForRequest((req) => req.url().includes("/api/v1/documents") && req.method() === "POST", { timeout: 15000 }),
      fileInput.uploadFile(NOTE_IMAGE_PATH),
    ]);

    log(`Document upload requested: ${uploadRequest.url()}`);
    await page.waitForFunction(
      () => window.location.pathname.includes("/notes/"),
      { timeout: 20000 }
    );

    const noteDetailUrl = await page.evaluate(() => window.location.href);
    const activeNoteId = noteDetailUrl.split("/notes/")[1].split("/")[0].split("?")[0];
    log(`Navigated to note detail URL: ${noteDetailUrl} (Note ID: ${activeNoteId})`);
    await page.waitForSelector(".page-heading h1", { timeout: 10000 });

    let initialTitle = await page.evaluate(() => document.querySelector(".page-heading h1")?.textContent?.trim());
    log(`Initial note title: "${initialTitle}"`);

    // --- TEST NOTE RENAME ---
    log("Testing Note Rename via ActionMenu...");
    await sleep(500);
    await page.waitForSelector('.page-heading .action-menu button[aria-label="Note actions"]', { timeout: 5000 });
    await page.click('.page-heading .action-menu button[aria-label="Note actions"]');
    await page.waitForSelector(".action-menu__dropdown", { timeout: 3000 });

    // Click "Rename"
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const renameBtn = items.find((i) => i.textContent?.toLowerCase().includes("rename"));
      renameBtn?.click();
    });

    const testNoteTitle = "Binary Search Trees Master Note";
    await clearAndType(page, ".dialog input.input", testNoteTitle);

    // Save
    await page.click(".dialog .btn--primary");
    await page.waitForFunction(
      (expected) => document.querySelector(".page-heading h1")?.textContent?.trim() === expected,
      { timeout: 5000 },
      testNoteTitle
    );
    log(`Note renamed in UI to: "${testNoteTitle}"`);

    // Reload page to verify persistence
    log("Reloading page to verify note rename persistence...");
    await page.reload({ waitUntil: "networkidle2" });
    await page.waitForSelector(".page-heading h1", { timeout: 10000 });
    const persistedNoteTitle = await page.evaluate(() => document.querySelector(".page-heading h1")?.textContent?.trim());
    log(`Title after reload: "${persistedNoteTitle}"`);

    if (persistedNoteTitle !== testNoteTitle) {
      throw new Error(`Note rename persistence failed. Expected "${testNoteTitle}", got "${persistedNoteTitle}"`);
    }
    results.checklist.noteRenamePersisted = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_note_renamed.png") });

    // -------------------------------------------------------------
    // Step 4: Folder CRUD & Move Note
    // -------------------------------------------------------------
    log("Step 4: Folder CRUD & Move Note");
    // Navigate back to subject workspace
    await page.goto(subjectUrl, { waitUntil: "networkidle2" });
    await page.waitForSelector(".panel-section__header", { timeout: 10000 });

    // Click "New folder" button
    const testFolderName = `Algorithmic Trees ${Date.now()}`;
    log(`Creating new folder: ${testFolderName}`);
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll(".panel-section__header button"));
      const newFolderBtn = buttons.find((b) => b.textContent?.toLowerCase().includes("folder"));
      newFolderBtn?.click();
    });

    await page.waitForSelector("#new-folder-name", { timeout: 5000 });
    await page.type("#new-folder-name", testFolderName);
    await page.click('button[form="new-folder-form"]');

    // Wait for folder to appear in list
    await page.waitForFunction(
      (name) => document.body.innerText.includes(name),
      { timeout: 10000 },
      testFolderName
    );
    log(`Folder '${testFolderName}' created successfully.`);
    results.checklist.folderCreated = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_folder_created.png") });

    // Navigate to Unfiled folder to move the note
    log("Opening Unfiled folder to move the note...");
    await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll(".folder-card"));
      const unfiledCard = cards.find((c) => c.textContent?.toLowerCase().includes("unfiled"));
      unfiledCard?.click();
    });

    await page.waitForFunction(
      () => window.location.pathname.includes("/folders/"),
      { timeout: 10000 }
    );

    // On NoteRow, click ActionMenu -> Move to folder…
    log(`Moving note ${activeNoteId} into '${testFolderName}'...`);
    await sleep(500);
    // Find note row corresponding to activeNoteId
    await page.evaluate((targetId) => {
      const rows = Array.from(document.querySelectorAll(".note-row"));
      const row = rows.find((r) => r.querySelector(`a[href*="${targetId}"]`)) || rows[0];
      const menuBtn = row?.querySelector('.action-menu button[aria-label="Note actions"]');
      menuBtn?.click();
    }, activeNoteId);

    await page.waitForSelector(".action-menu__dropdown", { timeout: 3000 });
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const moveBtn = items.find((i) => i.textContent?.toLowerCase().includes("move"));
      moveBtn?.click();
    });

    // In MoveNoteDialog, select testFolderName
    await page.waitForSelector(".dialog .popover__item", { timeout: 5000 });
    await page.evaluate((targetName) => {
      const options = Array.from(document.querySelectorAll(".dialog .popover__item"));
      const target = options.find((o) => o.textContent?.includes(targetName));
      target?.click();
    }, testFolderName);

    // Click Move button in dialog
    await page.click(".dialog .btn--primary");
    await sleep(1000);

    // Navigate back to subject workspace
    await page.goto(subjectUrl, { waitUntil: "networkidle2" });
    log("Reloaded subject workspace. Checking folder card...");

    // Click into newly created folder card
    await page.waitForFunction(
      (name) => {
        const cards = Array.from(document.querySelectorAll(".folder-card"));
        return cards.some((c) => c.textContent?.includes(name));
      },
      { timeout: 10000 },
      testFolderName
    );
    await page.evaluate((name) => {
      const cards = Array.from(document.querySelectorAll(".folder-card"));
      const fCard = cards.find((c) => c.textContent?.includes(name));
      fCard?.click();
    }, testFolderName);

    await page.waitForSelector(".page-heading h1", { timeout: 10000 });
    const insideFolderHeading = await page.evaluate(() => document.querySelector(".page-heading h1")?.textContent?.trim());
    log(`Inside folder heading: "${insideFolderHeading}"`);

    // Verify note is inside folder
    const hasNoteInsideFolder = await page.evaluate((targetId) => {
      return !!document.querySelector(`a[href*="${targetId}"]`);
    }, activeNoteId);

    log(`Note present inside folder: ${hasNoteInsideFolder}`);
    if (!hasNoteInsideFolder) {
      throw new Error(`Note ${activeNoteId} not found inside folder.`);
    }
    results.checklist.noteMovedToFolder = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_note_inside_folder.png") });

    // Rename Folder
    const renamedFolderTitle = `Advanced Trees ${Date.now()}`;
    log(`Renaming folder to: ${renamedFolderTitle}...`);
    await sleep(500);
    await page.waitForSelector('.page-heading .action-menu button[aria-label="Folder actions"]', { timeout: 5000 });
    await page.click('.page-heading .action-menu button[aria-label="Folder actions"]');
    await page.waitForSelector(".action-menu__dropdown", { timeout: 3000 });

    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const renameBtn = items.find((i) => i.textContent?.toLowerCase().includes("rename"));
      renameBtn?.click();
    });

    await clearAndType(page, ".dialog input.input", renamedFolderTitle);
    await page.click(".dialog .btn--primary");

    await page.waitForFunction(
      (expected) => document.querySelector(".page-heading h1")?.textContent?.trim() === expected,
      { timeout: 5000 },
      renamedFolderTitle
    );
    log(`Folder renamed to "${renamedFolderTitle}" in UI.`);

    await page.reload({ waitUntil: "networkidle2" });
    await page.waitForSelector(".page-heading h1", { timeout: 10000 });
    const persistedFolderHeading = await page.evaluate(() => document.querySelector(".page-heading h1")?.textContent?.trim());
    log(`Folder heading after reload: "${persistedFolderHeading}"`);
    if (persistedFolderHeading !== renamedFolderTitle) {
      throw new Error(`Folder rename persistence failed.`);
    }
    results.checklist.folderRenamePersisted = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_folder_renamed.png") });

    // Delete Folder -> Verify Child Notes Become Unfiled
    log("Deleting folder to verify child note unfiled behavior...");
    await sleep(500);
    await page.click('.page-heading .action-menu button[aria-label="Folder actions"]');
    await page.waitForSelector(".action-menu__dropdown", { timeout: 3000 });

    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const delBtn = items.find((i) => i.textContent?.toLowerCase().includes("delete"));
      delBtn?.click();
    });

    await page.waitForSelector(".dialog .btn--danger", { timeout: 5000 });
    await page.click(".dialog .btn--danger");

    // Navigates back to subject workspace
    await page.waitForFunction(
      () => !window.location.pathname.includes("/folders/"),
      { timeout: 10000 }
    );
    log("Navigated back to subject workspace after folder deletion.");

    // Click into Unfiled folder and verify note is safely preserved inside
    await page.waitForSelector(".folder-card", { timeout: 10000 });
    await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll(".folder-card"));
      const unfiledCard = cards.find((c) => c.textContent?.toLowerCase().includes("unfiled"));
      unfiledCard?.click();
    });
    await page.waitForSelector(".note-row", { timeout: 10000 });

    const notePreservedInUnfiled = await page.evaluate((targetId) => {
      return !!document.querySelector(`a[href*="${targetId}"]`);
    }, activeNoteId);

    log(`Child note ${activeNoteId} preserved in Unfiled: ${notePreservedInUnfiled}`);
    results.checklist.folderDeletedChildNoteUnfiled = notePreservedInUnfiled;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_folder_deleted_notes_unfiled.png") });

    // -------------------------------------------------------------
    // Step 5: Subject CRUD (Create, Rename, Delete)
    // -------------------------------------------------------------
    log("Step 5: Subject CRUD (Create, Rename, Delete)");
    const tempSubjectName = `Compiler Design ${Date.now()}`;
    await page.click(".sidebar__add");
    await page.waitForSelector("#new-subject-name", { timeout: 5000 });
    await page.type("#new-subject-name", tempSubjectName);
    await page.click('button[form="new-subject-form"]');

    // Wait for subject to appear in sidebar
    await page.waitForFunction(
      (name) => {
        const items = Array.from(document.querySelectorAll(".sidebar__item"));
        return items.some((i) => i.textContent?.includes(name));
      },
      { timeout: 10000 },
      tempSubjectName
    );
    log(`Subject "${tempSubjectName}" appeared in sidebar.`);

    // Click newly created subject in sidebar
    await page.evaluate((name) => {
      const items = Array.from(document.querySelectorAll(".sidebar__item"));
      const target = items.find((i) => i.textContent?.includes(name));
      target?.click();
    }, tempSubjectName);

    await page.waitForFunction(
      (name) => document.querySelector(".page-heading h1")?.textContent?.trim() === name,
      { timeout: 10000 },
      tempSubjectName
    );
    log(`Created and navigated to subject: "${tempSubjectName}"`);
    results.checklist.subjectCreated = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "07_subject_created.png") });

    // Rename Subject
    const renamedSubjectName = `Compiler Theory ${Date.now()}`;
    log(`Renaming subject to: ${renamedSubjectName}...`);
    await sleep(600);
    await page.waitForSelector('.page-heading .action-menu button[aria-label="Subject actions"]', { timeout: 5000 });
    await page.click('.page-heading .action-menu button[aria-label="Subject actions"]');
    await page.waitForSelector(".action-menu__dropdown", { timeout: 5000 });

    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const ren = items.find((i) => i.textContent?.toLowerCase().includes("rename"));
      ren?.click();
    });

    await clearAndType(page, ".dialog input.input", renamedSubjectName);
    await page.click(".dialog .btn--primary");

    await page.waitForFunction(
      (name) => document.querySelector(".page-heading h1")?.textContent?.trim() === name,
      { timeout: 5000 },
      renamedSubjectName
    );
    log(`Subject renamed to "${renamedSubjectName}" in UI.`);

    await page.reload({ waitUntil: "networkidle2" });
    await page.waitForSelector(".page-heading h1", { timeout: 10000 });
    const persistedSubHeading = await page.evaluate(() => document.querySelector(".page-heading h1")?.textContent?.trim());
    if (persistedSubHeading !== renamedSubjectName) {
      throw new Error(`Subject rename persistence failed.`);
    }
    results.checklist.subjectRenamePersisted = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "08_subject_renamed.png") });

    // Delete Subject
    log(`Deleting subject ${renamedSubjectName}...`);
    await sleep(600);
    await page.click('.page-heading .action-menu button[aria-label="Subject actions"]');
    await page.waitForSelector(".action-menu__dropdown", { timeout: 5000 });

    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const del = items.find((i) => i.textContent?.toLowerCase().includes("delete"));
      del?.click();
    });

    await page.waitForSelector(".dialog .btn--danger", { timeout: 5000 });
    await page.click(".dialog .btn--danger");

    // Navigates to /subjects
    await page.waitForFunction(
      () => window.location.pathname === "/subjects",
      { timeout: 10000 }
    );
    log("Navigated to /subjects after subject deletion.");

    // Verify deleted subject is gone from sidebar
    const subjectGone = await page.evaluate((name) => {
      const items = Array.from(document.querySelectorAll(".sidebar__item"));
      return !items.some((i) => i.textContent?.includes(name));
    }, renamedSubjectName);

    log(`Subject removed from sidebar: ${subjectGone}`);
    results.checklist.subjectDeleted = subjectGone;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "09_subject_deleted.png") });

    // -------------------------------------------------------------
    // Step 6: Profile CRUD & Single-Profile Guard
    // -------------------------------------------------------------
    log("Step 6: Profile CRUD & Single-Profile Guard");
    // Open profile switcher
    await page.click(".profile-button");
    await page.waitForSelector(".popover", { timeout: 5000 });

    // Handle prompt for New Profile
    const newProfileName = `E2E Profile ${Date.now()}`;
    const promptHandler = async (dialog) => {
      log(`Prompt detected: "${dialog.message()}"`);
      await dialog.accept(newProfileName);
    };
    page.on("dialog", promptHandler);

    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".popover .popover__item"));
      const newP = items.find((i) => i.textContent?.toLowerCase().includes("profile") && i.textContent?.toLowerCase().includes("new"));
      newP?.click();
    });

    await sleep(2000);
    page.off("dialog", promptHandler);

    // Open switcher again to check created profile
    await page.click(".profile-button");
    await page.waitForSelector(".popover", { timeout: 5000 });

    await page.waitForFunction(
      (name) => {
        const items = Array.from(document.querySelectorAll(".popover [role='menuitemradio']"));
        return items.some((i) => i.textContent?.includes(name));
      },
      { timeout: 10000 },
      newProfileName
    );
    log(`Profile "${newProfileName}" present in list.`);
    results.checklist.profileCreated = true;

    // Rename Profile
    const renamedProfileTarget = `E2E Renamed ${Date.now()}`;
    log(`Renaming profile to: ${renamedProfileTarget}...`);
    await page.evaluate((targetName) => {
      const rows = Array.from(document.querySelectorAll(".popover > div"));
      const row = rows.find((r) => r.textContent?.includes(targetName));
      const menuBtn = row?.querySelector(".action-menu button");
      menuBtn?.click();
    }, newProfileName);

    await page.waitForSelector(".action-menu__dropdown", { timeout: 3000 });
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const ren = items.find((i) => i.textContent?.toLowerCase().includes("rename"));
      ren?.click();
    });

    await clearAndType(page, ".dialog input.input", renamedProfileTarget);
    await page.click(".dialog .btn--primary");
    await sleep(1000);

    // Reopen popover and verify rename
    await page.click(".profile-button");
    await page.waitForSelector(".popover", { timeout: 5000 });
    await page.waitForFunction(
      (name) => {
        const items = Array.from(document.querySelectorAll(".popover [role='menuitemradio']"));
        return items.some((i) => i.textContent?.includes(name));
      },
      { timeout: 10000 },
      renamedProfileTarget
    );

    log(`Profile renamed to "${renamedProfileTarget}" confirmed.`);
    results.checklist.profileRenamed = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "10_profile_renamed.png") });

    // Delete Profile
    log(`Deleting profile '${renamedProfileTarget}'...`);
    await page.evaluate((targetName) => {
      const rows = Array.from(document.querySelectorAll(".popover > div"));
      const row = rows.find((r) => r.textContent?.includes(targetName));
      const menuBtn = row?.querySelector(".action-menu button");
      menuBtn?.click();
    }, renamedProfileTarget);

    await page.waitForSelector(".action-menu__dropdown", { timeout: 3000 });
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const del = items.find((i) => i.textContent?.toLowerCase().includes("delete"));
      del?.click();
    });

    await page.waitForSelector(".dialog .btn--danger", { timeout: 5000 });
    await page.click(".dialog .btn--danger");
    await sleep(1000);

    // Check popover: deleted profile should not be present
    await page.click(".profile-button");
    await page.waitForSelector(".popover", { timeout: 5000 });
    const profileGone = await page.evaluate((name) => {
      const items = Array.from(document.querySelectorAll(".popover [role='menuitemradio']"));
      return !items.some((i) => i.textContent?.includes(name));
    }, renamedProfileTarget);

    log(`Profile "${renamedProfileTarget}" successfully deleted: ${profileGone}`);
    results.checklist.profileDeleted = profileGone;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "11_profile_deleted.png") });

    // Close switcher
    await page.click("body");
    await sleep(500);

    // -------------------------------------------------------------
    // Step 7: AI Pipeline Regression Test (OCR + Enrichment)
    // -------------------------------------------------------------
    log("Step 7: AI Pipeline Regression Test (OCR + Enrichment)");
    // Navigate directly to active note detail page
    await page.goto(`${APP_URL}/subjects/befb6eeb-da4e-4c23-96f4-54c96650296e/notes/${activeNoteId}`, { waitUntil: "networkidle2" });
    await page.waitForSelector(".page-heading h1", { timeout: 10000 });
    log(`In note detail page for ${activeNoteId}. Checking OCR status...`);

    // Wait for OCR to complete (without manual refresh)
    const ocrStartTime = Date.now();
    await page.waitForFunction(
      () => {
        const lines = document.querySelectorAll(".transcript-line");
        const chip = document.querySelector(".source-page__header .chip")?.textContent?.toLowerCase() || "";
        return (
          lines.length > 0 ||
          chip.includes("completed") ||
          chip.includes("transcribed") ||
          chip.includes("review")
        );
      },
      { timeout: 90000, polling: 1000 }
    );

    const ocrDuration = Date.now() - ocrStartTime;
    results.metrics.ocrDurationMs = ocrDuration;
    log(`OCR ready in ${ocrDuration}ms`);

    const ocrResult = await page.evaluate(() => {
      const lines = Array.from(document.querySelectorAll(".transcript-line")).map((l) => l.textContent?.trim());
      const chip = document.querySelector(".source-page__header .chip")?.textContent?.trim();
      return { lines, chip };
    });
    log(`OCR Chip: "${ocrResult.chip}", Transcribed lines count: ${ocrResult.lines.length}`);
    results.checklist.ocrCompleted = ocrResult.lines.length > 0;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "12_ocr_completed.png") });

    // Enriched Tab & Trigger Enrichment
    log("Switching to Enriched Tab...");
    const enrichedTabBtn = await page.waitForSelector('button[role="tab"]:nth-child(2)', { timeout: 5000 });
    await enrichedTabBtn.click();

    // Wait for either empty-state, progress, or already enriched blocks
    await page.waitForFunction(
      () => {
        return (
          document.querySelector(".empty-state button.btn--primary") ||
          document.querySelector(".enrichment-progress") ||
          document.querySelector(".enriched-block")
        );
      },
      { timeout: 15000, polling: 500 }
    );

    const hasEmptyState = await page.evaluate(() => {
      const btn = document.querySelector(".empty-state button.btn--primary");
      return !!btn;
    });

    if (hasEmptyState) {
      log("Clicking 'Generate enrichment'...");
      const enrichStartTime = Date.now();
      await page.click(".empty-state button.btn--primary");

      // Verify progress pulse
      await page.waitForSelector(".enrichment-progress", { timeout: 10000 });
      log("Enrichment progress pulse active.");

      // Wait for enrichment completion
      await page.waitForFunction(
        () => {
          const blocks = document.querySelectorAll(".enriched-block");
          return blocks.length > 0;
        },
        { timeout: 180000, polling: 2000 }
      );

      const enrichDuration = Date.now() - enrichStartTime;
      results.metrics.enrichDurationMs = enrichDuration;
      log(`Enrichment finished in ${enrichDuration}ms`);
    } else {
      // If already in progress or completed, wait for blocks
      await page.waitForFunction(
        () => {
          const blocks = document.querySelectorAll(".enriched-block");
          return blocks.length > 0;
        },
        { timeout: 180000, polling: 2000 }
      );
      log("Enrichment blocks rendered.");
    }

    const enrichmentBlocks = await page.evaluate(() => {
      const blocks = Array.from(document.querySelectorAll(".enriched-block"));
      return blocks.map((b) => ({
        title: b.querySelector(".enriched-block__title")?.textContent?.trim(),
        citationCount: b.querySelectorAll(".citation-chip").length,
      }));
    });

    log(`Enriched blocks count: ${enrichmentBlocks.length}`);
    enrichmentBlocks.forEach((b, i) => {
      log(`  Block ${i + 1}: "${b.title}" (${b.citationCount} citations)`);
    });
    results.checklist.enrichmentRendered = enrichmentBlocks.length > 0;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "13_enrichment_completed.png") });

    // Inspect Citation Chip
    log("Inspecting Reference Citation Chip...");
    const clickedCitation = await page.evaluate(() => {
      const chips = Array.from(document.querySelectorAll(".citation-chip"));
      const refChip = chips.find((c) => c.textContent?.includes("Ref:"));
      if (refChip) {
        refChip.click();
        return true;
      }
      return false;
    });

    if (clickedCitation) {
      await page.waitForSelector(".citation-detail-card", { timeout: 5000 });
      const citationCard = await page.evaluate(() => {
        const card = document.querySelector(".citation-detail-card");
        return {
          header: card?.querySelector("span")?.textContent?.trim(),
          badge: card?.querySelector(".chip")?.textContent?.trim(),
          quote: card?.querySelector("blockquote")?.textContent?.trim()?.slice(0, 100),
        };
      });
      log(`Citation card verified: Header="${citationCard.header}", Quote="${citationCard.quote}..."`);
      results.checklist.citationCardInspected = !!citationCard.header;
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "14_citation_card.png") });
    }

    // -------------------------------------------------------------
    // Step 8: Delete Note & Clean Up
    // -------------------------------------------------------------
    log("Step 8: Testing Note Deletion via ActionMenu");
    await sleep(500);
    await page.waitForSelector('.page-heading .action-menu button[aria-label="Note actions"]', { timeout: 5000 });
    await page.click('.page-heading .action-menu button[aria-label="Note actions"]');
    await page.waitForSelector(".action-menu__dropdown", { timeout: 3000 });

    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".action-menu__item"));
      const del = items.find((i) => i.textContent?.toLowerCase().includes("delete"));
      del?.click();
    });

    await page.waitForSelector(".dialog .btn--danger", { timeout: 5000 });
    await page.click(".dialog .btn--danger");

    // Navigates back
    await page.waitForFunction(
      () => !window.location.pathname.includes("/notes/"),
      { timeout: 10000 }
    );
    log("Navigated back after note deletion.");

    await sleep(1000);
    const noteGone = await page.evaluate((targetId) => {
      return !document.querySelector(`a[href*="${targetId}"]`);
    }, activeNoteId);

    log(`Note ${activeNoteId} deleted and removed: ${noteGone}`);
    results.checklist.noteDeleted = noteGone;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "15_note_deleted.png") });

    // Summary
    results.finishedAt = new Date().toISOString();
    results.success = Object.values(results.checklist).every(Boolean);
    log("==============================================================");
    log(`Phase 10C Acceptance Run Complete: ALL PASSED = ${results.success}`);
    log(JSON.stringify(results.checklist, null, 2));
    log("==============================================================");

    fs.writeFileSync(
      path.join(__dirname, "phase10c_results.json"),
      JSON.stringify(results, null, 2)
    );
  } catch (err) {
    log(`FATAL ERROR DURING TEST EXECUTION: ${err.message}\n${err.stack}`);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "99_fatal_error.png") }).catch(() => {});
    results.error = err.message;
    fs.writeFileSync(
      path.join(__dirname, "phase10c_results.json"),
      JSON.stringify(results, null, 2)
    );
    throw err;
  } finally {
    await browser.close();
  }
}

runE2E()
  .then(() => process.exit(0))
  .catch(() => process.exit(1));
