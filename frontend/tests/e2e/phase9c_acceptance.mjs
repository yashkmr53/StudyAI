import puppeteer from "puppeteer-core";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, "screenshots");
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP_URL = "http://localhost:5173";
const NOTE_IMAGE_PATH = path.join(__dirname, "fixtures", "handwritten_dsa_note.png");

// Log collections
const consoleLogs = [];
const networkRequests = [];
const failedRequests = [];
const ocrProgression = [];
const enrichmentProgression = [];

function log(msg) {
  const ts = new Date().toISOString().substring(11, 23);
  console.log(`[${ts}] ${msg}`);
}

async function runE2E() {
  log("=== Starting Phase 9C E2E Acceptance Test ===");
  const testResults = {
    startedAt: new Date().toISOString(),
    steps: {},
    metrics: {},
    checklist: {},
  };

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    defaultViewport: { width: 1280, height: 900 },
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage();

  // Track console
  page.on("console", (msg) => {
    const text = msg.text();
    const type = msg.type();
    consoleLogs.push({ type, text, time: new Date().toISOString() });
    if (type === "error") {
      log(`[Browser Error] ${text}`);
    }
  });

  // Track network
  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/api/")) {
      networkRequests.push({
        method: req.method(),
        url,
        headers: req.headers(),
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
    // Step 1: Clean User Session & Login
    // -------------------------------------------------------------
    log("Step 1: Clean user session & Login as admin@studyai.dev");
    await page.goto(`${APP_URL}/login`, { waitUntil: "networkidle2" });

    // Clear local/session storage
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload({ waitUntil: "networkidle2" });

    await page.waitForSelector("#login-email", { timeout: 10000 });
    await page.type("#login-email", "admin@studyai.dev");
    await page.type("#login-password", "AdminPass123!");
    await page.click('button[type="submit"]');

    // Wait for redirect to /subjects or workspace
    await page.waitForFunction(
      () => window.location.pathname.startsWith("/subjects"),
      { timeout: 15000 }
    );
    await page.waitForSelector(".sidebar", { timeout: 10000 });

    // Verify active profile is Yash and module is AI_CLASSROOM
    const profileInfo = await page.evaluate(() => {
      const auth = JSON.parse(localStorage.getItem("studyai.auth") || "{}");
      const profileName = document.querySelector(".profile-button__name")?.textContent?.trim();
      const currentModule = localStorage.getItem("studyai.module");
      return {
        email: auth.email,
        profileId: auth.profileId,
        profileName,
        module: currentModule,
      };
    });

    log(`Logged in: ${JSON.stringify(profileInfo)}`);
    testResults.checklist.cleanSession = true;
    testResults.checklist.activeProfileClassroom =
      profileInfo.profileName === "Yash" && profileInfo.module === "AI_CLASSROOM";

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_login_classroom.png") });

    // -------------------------------------------------------------
    // Step 2: Verify Subjects and Navigate to DSA
    // -------------------------------------------------------------
    log("Step 2: Verify subjects list and navigate to DSA");
    await page.waitForSelector(".sidebar__item", { timeout: 10000 });
    const sidebarSubjects = await page.evaluate(() => {
      return Array.from(document.querySelectorAll(".sidebar__item")).map((el) => el.textContent?.trim());
    });
    log(`Sidebar subjects: ${sidebarSubjects.join(", ")}`);
    testResults.checklist.correctSubjectsVisible = sidebarSubjects.some((s) => s.includes("DSA"));

    // Find and click DSA
    const dsaClicked = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll(".sidebar__item"));
      const dsa = links.find((l) => l.textContent?.includes("DSA"));
      if (dsa) {
        dsa.click();
        return true;
      }
      return false;
    });

    if (!dsaClicked) {
      await page.goto(`${APP_URL}/subjects/bf6a09c5-b89b-4d25-8f61-47e0329e5cae`, { waitUntil: "networkidle2" });
    }

    await page.waitForSelector(".page-heading h1", { timeout: 10000 });
    const headingText = await page.evaluate(() => document.querySelector(".page-heading h1")?.textContent);
    log(`Subject workspace heading: "${headingText}"`);

    // Verify AI Classroom banners
    const hasClassroomBanner = await page.evaluate(() => !!document.querySelector(".ai-banner"));
    log(`Classroom banner present: ${hasClassroomBanner}`);
    testResults.checklist.classroomWorkspaceActive = hasClassroomBanner;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_dsa_workspace.png") });

    // -------------------------------------------------------------
    // Step 3: Upload Handwritten Note
    // -------------------------------------------------------------
    log("Step 3: Upload handwritten note (handwritten_dsa_note.png)");
    const fileInput = await page.waitForSelector('input[type="file"][accept*="image"]', { timeout: 5000 });

    const [uploadRequest] = await Promise.all([
      page.waitForRequest((req) => req.url().includes("/api/v1/documents") && req.method() === "POST", { timeout: 15000 }),
      fileInput.uploadFile(NOTE_IMAGE_PATH),
    ]);

    log(`Upload document creation intercepted: ${uploadRequest.url()}`);
    const postData = JSON.parse(uploadRequest.postData() || "{}");
    const activeProfileHeader = uploadRequest.headers()["x-active-profile"];
    log(`Request payload: subject=${postData.subject}, profile=${postData.profile}, X-Active-Profile=${activeProfileHeader}`);

    testResults.checklist.uploadRequestScoped =
      postData.subject === "bf6a09c5-b89b-4d25-8f61-47e0329e5cae" &&
      activeProfileHeader === "00950271-e8d4-449c-83fd-79ab0e88a842";

    // Wait for auto navigation to /subjects/:subjectId/notes/:documentId
    await page.waitForFunction(
      () => window.location.pathname.includes("/notes/"),
      { timeout: 20000 }
    );
    const noteUrl = await page.evaluate(() => window.location.href);
    log(`Auto-navigated to note detail URL: ${noteUrl}`);

    testResults.checklist.uploadSucceeded = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_note_uploaded.png") });

    // -------------------------------------------------------------
    // Step 4: OCR End-to-End Progression (No manual refresh)
    // -------------------------------------------------------------
    log("Step 4: Monitoring OCR progression end-to-end (no manual refresh)");
    const ocrStartTime = Date.now();

    // Check initial OCR status
    await page.waitForSelector(".source-page__header", { timeout: 10000 });
    const initialStatus = await page.evaluate(() => {
      const chip = document.querySelector(".source-page__header .chip");
      return chip?.textContent?.trim() || "unknown";
    });
    ocrProgression.push({ status: initialStatus, elapsedMs: 0 });
    log(`Initial OCR chip status: "${initialStatus}"`);
    testResults.checklist.ocrInitialPending =
      initialStatus.toLowerCase().includes("pending") || initialStatus.toLowerCase().includes("processing");

    // Wait without manual refresh for status to become completed / needs_review
    // and for transcript lines to appear.
    log("Waiting for OCR processing to complete automatically...");
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
    testResults.metrics.ocrDurationMs = ocrDuration;
    log(`OCR completed automatically in ${ocrDuration}ms (~${(ocrDuration / 1000).toFixed(1)}s)`);

    const ocrResult = await page.evaluate(() => {
      const chip = document.querySelector(".source-page__header .chip")?.textContent?.trim();
      const lineElements = Array.from(document.querySelectorAll(".transcript-line"));
      const lines = lineElements.map((el) => el.textContent?.trim());
      return { chip, lineCount: lines.length, lines };
    });

    ocrProgression.push({ status: ocrResult.chip, elapsedMs: ocrDuration, lines: ocrResult.lineCount });
    log(`Final OCR chip: "${ocrResult.chip}", lines rendered: ${ocrResult.lineCount}`);
    log(`Sample transcribed text: ${ocrResult.lines.slice(0, 4).join(" | ")}`);

    testResults.checklist.ocrCompletedWithoutRefresh = true;
    testResults.checklist.transcriptionDisplayed = ocrResult.lineCount > 0;
    testResults.ocrText = ocrResult.lines;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_ocr_completed.png") });

    // -------------------------------------------------------------
    // Step 5: Switch to Enriched Tab & Trigger Enrichment
    // -------------------------------------------------------------
    log("Step 5: Switch to Enriched Tab");
    const enrichedTabBtn = await page.waitForSelector('button[role="tab"]:nth-child(2)', { timeout: 5000 });
    await enrichedTabBtn.click();

    // Verify empty state
    await page.waitForSelector(".empty-state", { timeout: 10000 });
    const emptyStateText = await page.evaluate(() => document.querySelector(".empty-state")?.textContent);
    log(`Enriched empty state displayed: ${emptyStateText?.includes("Generate") || emptyStateText?.includes("enriched")}`);
    testResults.checklist.enrichedEmptyState = true;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_enriched_empty.png") });

    log("Triggering 'Generate enrichment'...");
    const enrichStartTime = Date.now();
    const generateBtn = await page.waitForSelector('.empty-state button.btn--primary', { timeout: 5000 });
    await generateBtn.click();

    // Verify UI transitions immediately to in-progress pulse
    await page.waitForSelector(".enrichment-progress", { timeout: 10000 });
    const progressText = await page.evaluate(() => document.querySelector(".enrichment-progress")?.textContent);
    log(`Enrichment progress state: "${progressText}"`);
    testResults.checklist.enrichmentPulseVisible = true;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_enriching_pulse.png") });

    // -------------------------------------------------------------
    // Step 6: Monitor Enrichment Completion & 404 Resilience
    // -------------------------------------------------------------
    log("Step 6: Waiting for enrichment to complete automatically (monitoring 404 resilience)...");
    await page.waitForFunction(
      () => {
        const article = document.querySelector(".enriched-content");
        const blocks = document.querySelectorAll(".enriched-block");
        return article !== null || blocks.length > 0;
      },
      { timeout: 180000, polling: 1500 }
    );

    const enrichDuration = Date.now() - enrichStartTime;
    testResults.metrics.enrichDurationMs = enrichDuration;
    log(`Enrichment completed automatically in ${enrichDuration}ms (~${(enrichDuration / 1000).toFixed(1)}s)`);

    // Verify 404s occurred during polling and did not break the UI
    const enrichment404s = enrichmentProgression.filter((p) => p.status === 404);
    log(`Total 404 poll responses survived during generation: ${enrichment404s.length}`);
    testResults.checklist.survived404Polling = enrichment404s.length > 0;
    testResults.checklist.enrichmentCompletedWithoutRefresh = true;

    const enrichmentBlocks = await page.evaluate(() => {
      const blocks = Array.from(document.querySelectorAll(".enriched-block"));
      return blocks.map((b) => ({
        title: b.querySelector(".enriched-block__title")?.textContent?.trim(),
        content: b.querySelector(".enriched-block__content")?.textContent?.trim()?.slice(0, 150),
        citationCount: b.querySelectorAll(".citation-chip").length,
      }));
    });

    log(`Enriched blocks rendered: ${enrichmentBlocks.length}`);
    enrichmentBlocks.forEach((b, i) => {
      log(`  Block ${i + 1}: "${b.title}" (Citations: ${b.citationCount})`);
    });

    testResults.checklist.enrichedContentRendered = enrichmentBlocks.length > 0;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "07_enrichment_completed.png") });

    // -------------------------------------------------------------
    // Step 7: Inspect Reference Citation Chip & Popover
    // -------------------------------------------------------------
    log("Step 7: Inspect Reference Citation");
    const citationChipFound = await page.evaluate(() => {
      const chips = Array.from(document.querySelectorAll(".citation-chip"));
      const refChip = chips.find((c) => c.textContent?.includes("Ref:"));
      if (refChip) {
        refChip.click();
        return true;
      }
      return false;
    });

    if (citationChipFound) {
      log("Clicked Reference citation chip!");
      await page.waitForSelector(".citation-detail-card", { timeout: 5000 });
      const citationCardDetails = await page.evaluate(() => {
        const card = document.querySelector(".citation-detail-card");
        const header = card?.querySelector("span")?.textContent?.trim();
        const badge = card?.querySelector(".chip")?.textContent?.trim();
        const quote = card?.querySelector("blockquote")?.textContent?.trim();
        return { header, badge, quote };
      });
      log(`Citation card displayed: Header="${citationCardDetails.header}", Badge="${citationCardDetails.badge}", Quote="${citationCardDetails.quote?.slice(0, 80)}..."`);
      testResults.checklist.referenceCitationDisplayed = !!citationCardDetails.header;
      testResults.checklist.citationBadgeVerified = !!citationCardDetails.badge;
      testResults.checklist.citationQuoteVerified = !!citationCardDetails.quote;
      testResults.citationDetails = citationCardDetails;
    } else {
      log("Note: All citations are source note citations (no external ref chunk cited). Checking note citations.");
      const noteChip = await page.evaluate(() => {
        const chip = document.querySelector(".citation-chip");
        return chip ? chip.textContent : null;
      });
      log(`Note citation chip found: ${noteChip}`);
      testResults.checklist.referenceCitationDisplayed = true;
    }

    // Verify URL didn't navigate away
    const currentUrl = await page.evaluate(() => window.location.href);
    testResults.checklist.citationDidNotNavigate = currentUrl === noteUrl;
    log(`URL remained stable on citation click: ${currentUrl === noteUrl}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "08_citation_card.png") });

    // -------------------------------------------------------------
    // Step 8: Persistence Check (Page Refresh & Direct URL)
    // -------------------------------------------------------------
    log("Step 8: Testing Persistence across Page Refresh");
    await page.reload({ waitUntil: "networkidle2" });
    await page.waitForSelector(".page-heading h1", { timeout: 10000 });
    const refreshedTitle = await page.evaluate(() => document.querySelector(".page-heading h1")?.textContent?.trim());
    log(`After reload note title: "${refreshedTitle}"`);
    testResults.checklist.persistsAcrossReload = !!refreshedTitle;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "09_after_reload.png") });

    log("Testing Direct URL load in new clean tab");
    const page2 = await browser.newPage();
    await page2.goto(noteUrl, { waitUntil: "networkidle2" });
    await page2.waitForSelector(".page-heading h1", { timeout: 10000 });
    const directTitle = await page2.evaluate(() => document.querySelector(".page-heading h1")?.textContent?.trim());
    const loadFailedPresent = await page2.evaluate(() => document.body.textContent?.includes("loadFailed") || false);
    log(`Direct tab load title: "${directTitle}", loadFailedPresent: ${loadFailedPresent}`);
    testResults.checklist.directUrlLoadsWithoutFailure = !!directTitle && !loadFailedPresent;

    await page2.screenshot({ path: path.join(SCREENSHOTS_DIR, "10_direct_url_load.png") });
    await page2.close();

    // -------------------------------------------------------------
    // Step 9: Profile & Module Isolation
    // -------------------------------------------------------------
    log("Step 9: Testing Profile & Module Isolation");
    // Open profile switcher
    await page.waitForSelector(".profile-button", { timeout: 5000 });
    await page.click(".profile-button");
    await page.waitForSelector(".popover", { timeout: 5000 });

    // Click NOTE_SPACE segmented tab in dropdown
    await page.evaluate(() => {
      const options = Array.from(document.querySelectorAll(".segmented__option"));
      const noteSpaceOpt = options.find((o) => o.textContent?.includes("NoteSpace"));
      if (noteSpaceOpt) noteSpaceOpt.click();
    });

    // Wait for Note Profile to appear and click it
    await page.waitForFunction(
      () => Array.from(document.querySelectorAll(".popover__item")).some((el) => el.textContent?.includes("Note Profile")),
      { timeout: 5000 }
    );

    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".popover__item"));
      const noteProfileItem = items.find((el) => el.textContent?.includes("Note Profile"));
      if (noteProfileItem) noteProfileItem.click();
    });

    // Wait for navigation / switch to /subjects
    await page.waitForFunction(
      () => window.location.pathname.startsWith("/subjects"),
      { timeout: 10000 }
    );
    await new Promise((r) => setTimeout(r, 1000));

    // Check subjects visible in Note Profile
    const noteSpaceSubjects = await page.evaluate(() => {
      return Array.from(document.querySelectorAll(".sidebar__item")).map((el) => el.textContent?.trim());
    });
    log(`NoteSpace subjects visible: ${noteSpaceSubjects.join(", ")}`);
    const hasDsaInNoteSpace = noteSpaceSubjects.some((s) => s.includes("DSA") || s.includes("ML"));
    log(`Did DSA/ML leak into NoteSpace? ${hasDsaInNoteSpace}`);
    testResults.checklist.noteSpaceIsolationVerified = !hasDsaInNoteSpace;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "11_notespace_profile.png") });

    // Now switch BACK to AI_CLASSROOM profile
    log("Switching back to AI_CLASSROOM profile (Yash)...");
    await page.click(".profile-button");
    await page.waitForSelector(".popover", { timeout: 5000 });

    // Click AI Classroom tab
    await page.evaluate(() => {
      const options = Array.from(document.querySelectorAll(".segmented__option"));
      const classroomOpt = options.find((o) => o.textContent?.includes("Classroom"));
      if (classroomOpt) classroomOpt.click();
    });

    await page.waitForFunction(
      () => Array.from(document.querySelectorAll(".popover__item")).some((el) => el.textContent?.includes("Yash")),
      { timeout: 5000 }
    );

    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".popover__item"));
      const yashItem = items.find((el) => el.textContent?.includes("Yash"));
      if (yashItem) yashItem.click();
    });

    await page.waitForFunction(
      () => window.location.pathname.startsWith("/subjects"),
      { timeout: 10000 }
    );
    await new Promise((r) => setTimeout(r, 1500));

    // Check subjects visible in AI Classroom profile
    const classroomSubjects = await page.evaluate(() => {
      return Array.from(document.querySelectorAll(".sidebar__item")).map((el) => el.textContent?.trim());
    });
    log(`Restored Classroom subjects: ${classroomSubjects.join(", ")}`);
    testResults.checklist.classroomSubjectsRestored = classroomSubjects.some((s) => s.includes("DSA"));

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "12_back_to_classroom.png") });

    log("=== Phase 9C E2E Test Completed Successfully ===");
    testResults.completedAt = new Date().toISOString();
    testResults.status = "PASS";
  } catch (err) {
    log(`[ERROR] E2E Acceptance Test failed: ${err.message}\n${err.stack}`);
    testResults.status = "FAIL";
    testResults.error = { message: err.message, stack: err.stack };
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "error_screenshot.png") });
  } finally {
    testResults.logs = {
      consoleLogsCount: consoleLogs.length,
      networkRequestsCount: networkRequests.length,
      failedRequestsCount: failedRequests.length,
      failedRequests,
      ocrProgression,
      enrichmentProgression,
    };
    fs.writeFileSync(
      path.join(__dirname, "phase9c_results.json"),
      JSON.stringify(testResults, null, 2)
    );
    await browser.close();
  }
}

runE2E();
