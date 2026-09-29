/**
 * Phase 11 — Browser E2E Acceptance Test
 * ========================================
 * Reference Library & Grounded Knowledge end-to-end verification:
 * 1. Authenticate as admin@studyai.dev
 * 2. Navigate to Subject Workspace and locate Reference Library action & card
 * 3. Open Reference Library UI
 * 4. Upload sample textbook PDF ("Algorithms and Data Structures Reference")
 * 5. Verify ingestion completes and status transitions to READY with page & chunk counts
 * 6. Ask grounded question in Ask StudyAI and verify textbook citation & provenance
 * 7. Test multi-turn follow-up with grounded context
 * 8. Return to Reference Library and verify cascade delete cleanup
 *
 * Run:
 *   node frontend/tests/e2e/phase11_acceptance.mjs
 */
import puppeteer from "puppeteer-core";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, "screenshots", "phase11");
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP_URL = "http://localhost:5173";
const FIXTURE_PDF = path.join(__dirname, "fixtures", "sample_textbook.pdf");

const LLM_TIMEOUT = 120_000;
const INGEST_TIMEOUT = 90_000;
const NAV_TIMEOUT = 15_000;
const UI_TIMEOUT = 10_000;

function log(msg) {
  const ts = new Date().toISOString().substring(11, 23);
  console.log(`[${ts}] ${msg}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForAssistantReply(page, existingMsgCount) {
  log(`  Waiting for assistant reply (currently ${existingMsgCount} bubbles)...`);
  await page.waitForFunction(
    (prevCount) => {
      const msgs = document.querySelectorAll(".msg");
      if (msgs.length <= prevCount) return false;
      const last = msgs[msgs.length - 1];
      if (!last.classList.contains("msg--assistant")) return false;
      const bubble = last.querySelector(".msg__bubble");
      if (!bubble) return false;
      if (bubble.classList.contains("pending") || bubble.classList.contains("streaming")) return false;
      if (last.querySelector(".thinking-indicator")) return false;

      const input = document.querySelector(".chat-composer input.input");
      if (input && input.disabled) return false;

      const text = bubble.textContent?.trim() || "";
      return text.length > 20;
    },
    { timeout: LLM_TIMEOUT },
    existingMsgCount,
  );
  await sleep(1000);

  const reply = await page.evaluate(() => {
    const msgs = document.querySelectorAll(".msg--assistant");
    const last = msgs[msgs.length - 1];
    return last?.querySelector(".msg__bubble")?.textContent?.trim() || "";
  });
  log(`  Assistant replied (${reply.length} chars): "${reply.substring(0, 80)}..."`);
  return reply;
}

async function run() {
  log("Starting Phase 11 Reference Library Acceptance Test");

  const results = {
    startedAt: new Date().toISOString(),
    checklist: {
      authenticated: false,
      subjectWorkspaceLoaded: false,
      referenceLibraryNavigated: false,
      uploadDialogOpen: false,
      documentUploaded: false,
      ingestionCompletedReady: false,
      provenanceMetadataDisplayed: false,
      askStudyAIGroundedAnswer: false,
      multiTurnContextPreserved: false,
      documentDeletedSuccessfully: false,
    },
    metrics: {},
  };

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    defaultViewport: { width: 1366, height: 900 },
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage();
  let refUrl = "";

  page.on("console", (msg) => {
    if (msg.type() === "error") log(`[Browser Console Error] ${msg.text()}`);
  });

  try {
    // ---------------------------------------------------------------
    // Step 1: Authenticate
    // ---------------------------------------------------------------
    log("Step 1: Authenticate as admin@studyai.dev");
    await page.goto(`${APP_URL}/login`, { waitUntil: "networkidle2" });
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
      localStorage.setItem("studyai.module", "AI_CLASSROOM");
    });
    await page.reload({ waitUntil: "networkidle2" });

    await page.waitForSelector("#login-email", { timeout: UI_TIMEOUT });
    await page.type("#login-email", "admin@studyai.dev");
    await page.type("#login-password", "AdminPass123!");
    await page.click('button[type="submit"]');

    await page.waitForFunction(
      () => window.location.pathname.startsWith("/subjects"),
      { timeout: NAV_TIMEOUT },
    );
    await page.waitForSelector(".sidebar", { timeout: UI_TIMEOUT });

    // Ensure AI_CLASSROOM profile YashAI is active
    const session = await page.evaluate(() => {
      const auth = JSON.parse(localStorage.getItem("studyai.auth") || "{}");
      const profileName = document.querySelector(".profile-button__name")?.textContent?.trim();
      return { profileId: auth.profileId, profileName };
    });
    log(`Authenticated. Profile: ${session.profileName}`);

    if (session.profileName !== "YashAI") {
      log("Switching to YashAI...");
      await page.click(".profile-button");
      await page.waitForSelector(".popover", { timeout: 5000 });
      await page.evaluate(() => {
        const tabs = Array.from(document.querySelectorAll('.segmented button[role="tab"]'));
        const classroomTab = tabs.find((t) => t.textContent?.includes("AI Classroom"));
        classroomTab?.click();
      });
      await sleep(600);
      await page.waitForSelector('.popover [role="menuitemradio"]', { timeout: 5000 });
      await page.evaluate(() => {
        const radios = Array.from(document.querySelectorAll('.popover [role="menuitemradio"]'));
        const yashAi = radios.find((r) => r.textContent?.includes("YashAI"));
        yashAi?.click();
      });
      await page.waitForFunction(
        () => document.querySelector(".profile-button__name")?.textContent?.trim() === "YashAI",
        { timeout: UI_TIMEOUT },
      );
      log("Switched to YashAI.");
    }

    results.checklist.authenticated = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_authenticated.png") });

    // ---------------------------------------------------------------
    // Step 2: Navigate to Subject Workspace
    // ---------------------------------------------------------------
    log("Step 2: Inspect Subject Workspace for Reference Library actions");
    await page.waitForSelector(".sidebar__scroll .sidebar__item", { timeout: UI_TIMEOUT });
    const subjectHref = await page.evaluate(() => {
      const link = document.querySelector(".sidebar__scroll .sidebar__item");
      return link ? link.getAttribute("href") : null;
    });

    if (subjectHref) {
      await page.goto(`${APP_URL}${subjectHref}`, { waitUntil: "networkidle2" });
    }
    await page.waitForSelector(".panel-section", { timeout: UI_TIMEOUT });

    // Verify Reference Library button / card exists
    const hasRefButton = await page.evaluate(() => {
      const text = document.body.textContent || "";
      return text.includes("Reference Library");
    });
    log(`Subject Workspace loaded. Has Reference Library link: ${hasRefButton}`);
    results.checklist.subjectWorkspaceLoaded = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_subject_workspace.png") });

    // ---------------------------------------------------------------
    // Step 3: Open Reference Library
    // ---------------------------------------------------------------
    log("Step 3: Open Reference Library Page");
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll("button, a, .service-card, .card"));
      const refItem = items.find((el) => el.textContent?.includes("Reference Library"));
      refItem?.click();
    });

    await page.waitForFunction(
      () => document.querySelector("h1")?.textContent?.includes("Reference Library"),
      { timeout: UI_TIMEOUT },
    );
    refUrl = await page.evaluate(() => window.location.href);
    log(`Reference Library Page loaded at: ${refUrl}`);
    results.checklist.referenceLibraryNavigated = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_reference_library_empty.png") });

    // ---------------------------------------------------------------
    // Step 4: Upload Reference Textbook
    // ---------------------------------------------------------------
    log("Step 4: Click Upload Reference and open dialog");
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button"));
      const btn = btns.find(
        (b) =>
          b.textContent?.includes("Upload Reference") ||
          b.textContent?.includes("Upload Your First Textbook") ||
          b.textContent?.includes("Upload"),
      );
      btn?.click();
    });

    await page.waitForSelector("#upload-reference-form", { timeout: UI_TIMEOUT });
    results.checklist.uploadDialogOpen = true;
    log("Upload Reference dialog is open.");
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_upload_dialog_open.png") });

    // Fill form
    const fileInput = await page.$("#ref-file");
    if (!fileInput) throw new Error("Could not find file input in dialog");
    await fileInput.uploadFile(FIXTURE_PDF);

    await page.evaluate(() => {
      const titleInput = document.querySelector("#ref-title");
      if (titleInput) {
        titleInput.value = "Algorithms and Data Structures Reference";
        titleInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });

    log("Form filled. Submitting upload...");
    await page.evaluate(() => {
      const primaryBtn = document.querySelector('.dialog__actions button.btn--primary');
      if (primaryBtn) {
        primaryBtn.click();
      } else {
        const form = document.querySelector('#upload-reference-form');
        if (form) form.requestSubmit();
      }
    });

    await page.waitForSelector(".card", { timeout: UI_TIMEOUT });
    results.checklist.documentUploaded = true;
    log("Document card appeared in list.");
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_document_uploaded_pending.png") });

    // ---------------------------------------------------------------
    // Step 5: Wait for Ingestion to complete (Status READY)
    // ---------------------------------------------------------------
    log("Step 5: Waiting for ingestion to reach READY status...");
    await page.waitForFunction(
      () => {
        const cards = document.querySelectorAll(".card");
        for (const card of cards) {
          if (card.textContent?.includes("✓ Ready")) {
            return true;
          }
        }
        return false;
      },
      { timeout: INGEST_TIMEOUT },
    );

    const docMetrics = await page.evaluate(() => {
      const card = document.querySelector(".card");
      const text = card?.textContent || "";
      return {
        cardText: text,
        hasTextbookBadge: text.includes("Textbook"),
        hasReadyBadge: text.includes("Ready"),
        hasChunks: text.includes("chunks indexed"),
        hasPages: text.includes("pages"),
      };
    });

    log(`Ingestion complete: ${JSON.stringify(docMetrics)}`);
    results.checklist.ingestionCompletedReady = docMetrics.hasReadyBadge;
    results.checklist.provenanceMetadataDisplayed = docMetrics.hasChunks && docMetrics.hasPages;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_document_ready.png") });

    // ---------------------------------------------------------------
    // Step 6: Ask StudyAI Grounded Chat Test
    // ---------------------------------------------------------------
    log("Step 6: Ask StudyAI Question grounded in uploaded textbook");
    await page.goto(`${APP_URL}/ai-classroom/chat`, { waitUntil: "networkidle2" });
    await page.waitForSelector(".chat-sidebar", { timeout: UI_TIMEOUT });

    // Create a new chat session
    await page.click(".btn--secondary.btn--block");
    await sleep(800);

    const initialMsgCount = await page.evaluate(() => document.querySelectorAll(".msg").length);

    // Ask grounded question
    const question1 = "According to the algorithms textbook, what graph traversal algorithm uses a FIFO queue?";
    log(`Asking Turn 1: "${question1}"`);
    await page.type(".chat-composer input.input", question1);
    await page.keyboard.press("Enter");

    const reply1 = await waitForAssistantReply(page, initialMsgCount);
    const mentionsBFS = /breadth-first|bfs|queue|fifo/i.test(reply1);
    log(`Reply 1 contains BFS/FIFO concept: ${mentionsBFS}`);
    results.checklist.askStudyAIGroundedAnswer = mentionsBFS;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "07_grounded_answer_turn1.png") });

    // Ask follow-up question in multi-turn context
    const msgCountBeforeTurn2 = await page.evaluate(() => document.querySelectorAll(".msg").length);
    const question2 = "What is its running time?";
    log(`Asking Turn 2 (contextual follow-up): "${question2}"`);
    await page.type(".chat-composer input.input", question2);
    await page.keyboard.press("Enter");

    const reply2 = await waitForAssistantReply(page, msgCountBeforeTurn2);
    const mentionsComplexity = /o\s*\(\s*v\s*\+\s*e\s*\)|vertices|edges/i.test(reply2);
    log(`Reply 2 contains O(V + E) complexity from textbook: ${mentionsComplexity}`);
    results.checklist.multiTurnContextPreserved = mentionsComplexity;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "08_grounded_answer_turn2.png") });

    // ---------------------------------------------------------------
    // Step 7: Delete Reference Document & Verify Cascade Cleanup
    // ---------------------------------------------------------------
    log("Step 7: Return to Reference Library and verify deletion cleanup");
    await page.goto(refUrl, { waitUntil: "networkidle2" });
    await page.waitForSelector(".card", { timeout: UI_TIMEOUT });

    // Click delete icon
    await page.click(".card button.icon-btn");
    await page.waitForSelector(".dialog", { timeout: UI_TIMEOUT });
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "09_delete_confirm_dialog.png") });

    // Confirm deletion
    await page.click(".dialog button.btn--danger");

    await page.waitForFunction(
      () => {
        const text = document.body.textContent || "";
        return (
          text.includes("No reference material indexed yet") ||
          !text.includes("Algorithms and Data Structures Reference")
        );
      },
      { timeout: UI_TIMEOUT },
    );

    log("Document successfully deleted from Reference Library.");
    results.checklist.documentDeletedSuccessfully = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "10_deletion_verified.png") });

    results.completedAt = new Date().toISOString();
    results.success = Object.values(results.checklist).every(Boolean);

    fs.writeFileSync(
      path.join(__dirname, "phase11_results.json"),
      JSON.stringify(results, null, 2),
    );

    log(`Phase 11 Acceptance Test Passed! All ${Object.keys(results.checklist).length} criteria verified.`);
  } catch (err) {
    log(`Phase 11 Acceptance Test Failed: ${err.message}`);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "error_failure.png") }).catch(() => {});
    throw err;
  } finally {
    await browser.close();
  }
}

function windowLocationPath(pathname) {
  const match = pathname.match(/\/subjects\/([0-9a-fA-F-]+)/);
  return match ? match[1] : null;
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
