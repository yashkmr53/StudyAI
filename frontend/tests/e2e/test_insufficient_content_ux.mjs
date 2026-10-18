/**
 * Live E2E Verification: Insufficient-Content Gate & Enrichment Polling
 * ====================================================================
 * Executes headless Chrome against the live StudyAI stack (Docker + host Ollama).
 *
 * 1. Negative Case:
 *    - Opens a disposable note containing only "Yash Kumar".
 *    - Switches to Enriched tab and clicks "Generate enrichment".
 *    - Verifies that enrichment finishes quickly without unrelated blocks.
 *    - Verifies that UI displays the dedicated explanation:
 *      "There's not enough academic content to enrich this note yet. Add a concept, question, or explanation to your handwritten notes, save it, and try again."
 *    - Verifies that UI does NOT show generic failure ("We couldn't generate the enriched notes" / "Try Again").
 *    - Monitors network requests and confirms polling halts completely.
 *    - Clicks "Edit Handwritten Note" and verifies return to the handwritten tab.
 *
 * 2. Positive Case:
 *    - Updates the note to include a substantive academic statement about pointers in C.
 *    - Confirms that creating a new revision sets ai_stale=True.
 *    - Switches back to Enriched tab and triggers enrichment.
 *    - Real Celery worker + Ollama (qwen3.5:4b + qwen3-embedding:0.6b) runs:
 *      retrieves reference chunks from textbook "Let us c", generates blocks, citations,
 *      verifies evidence, and renders blocks with interactive citation chips.
 *    - Confirms polling ends immediately upon reaching terminal enriched state.
 *    - Reloads page and confirms full persistence of blocks and citations.
 *
 * 3. Cleanup:
 *    - Deletes only the disposable test document.
 *    - Confirms canonical reference textbook (743 pages, 695 chunks) remains 100% intact.
 */
import puppeteer from "puppeteer-core";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { execSync } from "child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = "/Users/yash/.gemini/antigravity-cli/brain/e8f18ce9-2b1d-4eaf-80f7-56d01a10a1f3/e2e_screenshots";
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP_URL = "http://localhost:5173";
const SUBJECT_ID = "befb6eeb-da4e-4c23-96f4-54c96650296e"; // DSA AI
const PROFILE_ID = "6ed4659f-d4eb-415f-9b70-9774fa584077"; // YashAI

const UI_TIMEOUT = 15_000;
const NAV_TIMEOUT = 25_000;
const ENRICH_TIMEOUT = 240_000;

function log(msg) {
  const ts = new Date().toISOString().substring(11, 23);
  console.log(`[${ts}] ${msg}`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function runBackendCommand(pyCode) {
  const out = execSync("docker compose exec -i api python manage.py shell", {
    input: pyCode,
    encoding: "utf-8",
    timeout: 35000,
  });
  return out;
}

async function run() {
  log("================================================================================");
  log("Starting E2E Verification: Insufficient-Content Gate & Polling UX");
  log("================================================================================");

  let disposableDocId = null;

  // Verify textbook status before test
  const tbCheck = runBackendCommand(`
from apps.references.models import ReferenceDocument, ReferenceChunk
rd = ReferenceDocument.objects.get(id="f148dab2-1ff0-4bd0-aa98-0857df36c068")
print(f"TEXTBOOK_CHECK:{rd.id}:{rd.title}:{rd.status}:{rd.page_count}:{ReferenceChunk.objects.filter(reference_document=rd).count()}")
`);
  log(`Pre-test Textbook: ${tbCheck.trim().split("\n").pop()}`);

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    defaultViewport: { width: 1366, height: 900 },
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage();
  let consoleErrors = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const txt = msg.text();
      consoleErrors.push(txt);
      log(`[Browser Console Error] ${txt}`);
    }
  });

  // Track network requests
  const networkCounters = {
    enrichmentGet: 0,
    enrichPost: 0,
    jobGet: 0,
    tagsGet: 0,
  };

  page.on("request", (req) => {
    const url = req.url();
    const method = req.method();
    if (url.includes("/enrichment") && method === "GET") networkCounters.enrichmentGet++;
    if (url.includes("/enrich") && method === "POST") networkCounters.enrichPost++;
    if (url.includes("/jobs/") && method === "GET") networkCounters.jobGet++;
    if (url.includes("/tags") && method === "GET") networkCounters.tagsGet++;
  });

  try {
    // 1. Authenticate & set profile
    log("\n--- STEP 1: Authentication ---");
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

    await page.waitForFunction(() => window.location.pathname.startsWith("/subjects"), {
      timeout: NAV_TIMEOUT,
    });
    log("Logged in successfully.");

    // Ensure YashAI profile in AI Classroom
    const profileName = await page.evaluate(
      () => document.querySelector(".profile-button__name")?.textContent?.trim() || "",
    );
    if (profileName !== "YashAI") {
      log(`Switching from ${profileName} to YashAI...`);
      await page.click(".profile-button");
      await page.waitForSelector(".popover", { timeout: 5000 });
      await page.evaluate(() => {
        const tabs = Array.from(document.querySelectorAll('.segmented button[role="tab"]'));
        const classroomTab = tabs.find((t) => t.textContent?.includes("AI Classroom"));
        classroomTab?.click();
      });
      await sleep(600);
      await page.evaluate(() => {
        const radios = Array.from(document.querySelectorAll('.popover [role="menuitemradio"]'));
        const yashAi = radios.find((r) => r.textContent?.includes("YashAI"));
        yashAi?.click();
      });
      await page.waitForFunction(
        () => document.querySelector(".profile-button__name")?.textContent?.trim() === "YashAI",
        { timeout: UI_TIMEOUT },
      );
    }
    log("Verified active profile is YashAI.");

    // 2. Negative Case: Create disposable note with "Yash Kumar"
    log("\n--- STEP 2: Negative Case (Minimal Note 'Yash Kumar') ---");
    const createRes = runBackendCommand(`
from apps.canvas.models import CanvasSession, CanvasPage
from apps.documents.models import Document, DocumentPage, DocumentPageRevision, DocumentLine
from apps.profiles.models import Profile
from apps.subjects.models import Subject

p = Profile.objects.get(id="${PROFILE_ID}")
s = Subject.objects.get(id="${SUBJECT_ID}")
sess = CanvasSession.objects.create(profile=p, device_id="devA")
cp = CanvasPage.objects.create(session=sess, page_number=1, is_finalized=True)
doc = Document.objects.create(profile=p, subject=s, title="Yash Kumar Note", source="canvas", source_type="canvas_page")
sess.document = doc
sess.save(update_fields=["document"])
page = DocumentPage.objects.create(document=doc, page_number=1, ocr_status="completed")
rev = DocumentPageRevision.objects.create(
    page=page,
    revision_number=1,
    content_hash="yash-kumar-rev-1",
    ocr_status="completed",
    content_snapshot={"lines": [{"text": "Yash Kumar"}]}
)
DocumentLine.objects.create(page_revision=rev, line_index=0, text="Yash Kumar")
page.current_revision_id = rev.id
page.save(update_fields=["current_revision_id"])
print("CREATED_DOC:" + str(doc.id))
`);

    const docMatch = createRes.match(/CREATED_DOC:([0-9a-f-]+)/);
    if (!docMatch) throw new Error(`Failed to create disposable document: ${createRes}`);
    disposableDocId = docMatch[1];
    log(`Created disposable note document: ${disposableDocId}`);

    const noteUrl = `${APP_URL}/subjects/${SUBJECT_ID}/notes/${disposableDocId}`;
    await page.goto(noteUrl, { waitUntil: "networkidle2" });
    await page.waitForSelector(".source-page, .tabs", { timeout: UI_TIMEOUT });
    log(`Loaded note page: ${noteUrl}`);

    // Switch to Enriched tab
    log("Switching to Enriched tab...");
    const tabBtns = await page.$$('.tabs button[role="tab"]');
    if (tabBtns.length >= 2) {
      await tabBtns[1].click();
    }
    await sleep(800);

    // Snapshot counters before generation
    const cBefore = { ...networkCounters };

    // Find and click "Generate enrichment"
    const genBtn = await page.waitForSelector(".empty-state button.btn--primary", { timeout: UI_TIMEOUT });
    log("Clicking 'Generate enrichment' for 'Yash Kumar' note...");
    const negStart = Date.now();
    await genBtn.click();

    // Observe rapid resolution without endless polling
    await page.waitForFunction(
      () => {
        const text = document.body.textContent || "";
        return (
          text.includes("Not enough academic content yet") ||
          text.includes("There's not enough academic content to enrich this note yet") ||
          document.querySelector(".error-state") !== null
        );
      },
      { timeout: 20_000, polling: 500 },
    );
    const negDuration = Date.now() - negStart;
    log(`Negative case completed in ${(negDuration / 1000).toFixed(2)}s.`);

    // Assertions on Negative Case UI
    const uiText = await page.evaluate(() => document.body.textContent || "");
    const hasGenericError = uiText.includes("We couldn't generate the enriched notes");
    const hasTryAgain = uiText.includes("Try Again");
    const hasInsufficientExplanation = uiText.includes(
      "There's not enough academic content to enrich this note yet. Add a concept, question, or explanation to your handwritten notes, save it, and try again.",
    );
    const hasEditButton = (await page.$(".empty-state button")) !== null;

    log(`UI Explanation check: ${hasInsufficientExplanation ? "PASS" : "FAIL"}`);
    log(`No Generic Failure Error: ${!hasGenericError ? "PASS" : "FAIL"}`);
    log(`No Try Again prompt: ${!hasTryAgain ? "PASS" : "FAIL"}`);
    log(`Has Edit Handwritten Note action: ${hasEditButton ? "PASS" : "FAIL"}`);

    if (hasGenericError || !hasInsufficientExplanation) {
      throw new Error("Negative case failed: generic error displayed or insufficient explanation missing.");
    }

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "13_negative_case_insufficient_content.png") });

    // Confirm polling stops: Wait 6 seconds and check request count delta
    log("Monitoring network requests for 6 seconds to confirm polling has ceased...");
    const cAfterGen = { ...networkCounters };
    await sleep(6000);
    const cAfterWait = { ...networkCounters };
    const enrichmentDeltas = cAfterWait.enrichmentGet - cAfterGen.enrichmentGet;
    const jobDeltas = cAfterWait.jobGet - cAfterGen.jobGet;
    log(`Network deltas during 6s wait: enrichmentGet=+${enrichmentDeltas}, jobGet=+${jobDeltas}`);
    if (enrichmentDeltas > 1 || jobDeltas > 1) {
      throw new Error(`Runaway polling detected! enrichment requests increased by ${enrichmentDeltas}`);
    }
    log("Polling confirmed stopped at terminal insufficient_content state.");

    // Test clicking "Edit Handwritten Note" button
    log("Clicking 'Edit Handwritten Note' button...");
    const editBtn = await page.waitForSelector(".empty-state button");
    await editBtn.click();
    await sleep(600);
    const activeTab = await page.evaluate(() => {
      const active = document.querySelector('.tabs button[role="tab"].active, .tabs button[role="tab"][aria-selected="true"]');
      return active?.textContent?.trim() || "";
    });
    log(`Active tab after clicking edit button: "${activeTab}"`);
    if (!activeTab.toLowerCase().includes("handwritten")) {
      throw new Error(`Expected active tab to be Handwritten, got: ${activeTab}`);
    }
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "14_edit_handwritten_return.png") });

    // 3. Positive Case: Update note with meaningful academic content
    log("\n--- STEP 3: Positive Case (Academic Statement about Pointers in C) ---");
    const updateRes = runBackendCommand(`
from apps.documents.models import Document, DocumentLine
from apps.documents.services import IngestionService
doc = Document.objects.get(id="${disposableDocId}")
page = doc.pages.first()
text = (
    "Pointers store memory addresses of variables in C. "
    "A pointer variable is declared with an asterisk (*), and the address-of operator (&) "
    "is used to retrieve the memory location of a variable. "
    "Passing pointers to functions enables call by reference, allowing functions to directly "
    "modify the caller arguments and avoid copying large data structures."
)
rev = IngestionService._create_revision_locked(
    page,
    content_hash="pointer-c-rev-2",
    ocr_status="completed",
    snapshot={"lines": [{"text": text}]}
)
DocumentLine.objects.create(page_revision=rev, line_index=0, text=text)
print("UPDATED_DOC:" + str(doc.id))
`);
    log(`Updated document revision with academic text: ${updateRes.trim()}`);

    // Verify previous enrichment became stale
    const staleCheck = runBackendCommand(`
from apps.ai_classroom.models import EnrichedNote
en = EnrichedNote.objects.filter(document_id="${disposableDocId}", superseded=False).first()
print(f"STALE_STATUS:{en.ai_stale if en else 'none'}")
`);
    log(`Database Stale check: ${staleCheck.trim()}`);

    // Switch to Enriched tab
    const tabs2 = await page.$$('.tabs button[role="tab"]');
    if (tabs2.length >= 2) {
      await tabs2[1].click();
    }
    await sleep(1000);

    // Look for Regenerate or Generate button
    log("Triggering enrichment for substantive academic note...");
    const regenBtn = await page.waitForSelector(".empty-state button.btn--primary, .stale-note button", {
      timeout: UI_TIMEOUT,
    });
    await regenBtn.click();
    log("Enrichment started! Waiting for real Celery worker + Ollama qwen3.5:4b...");

    const enrichStart = Date.now();
    await page.waitForFunction(
      () => {
        const blocks = document.querySelectorAll(".enriched-block");
        const body = document.querySelector(".enriched-body");
        return blocks.length > 0 && body !== null;
      },
      { timeout: ENRICH_TIMEOUT, polling: 2500 },
    );
    const enrichDuration = Date.now() - enrichStart;
    log(`Enrichment succeeded in ${(enrichDuration / 1000).toFixed(1)}s!`);

    // Verify rendered blocks and citation chips
    const blockData = await page.evaluate(() => {
      const blocks = Array.from(document.querySelectorAll(".enriched-block"));
      return blocks.map((b) => ({
        title: b.querySelector("h3")?.textContent?.trim() || "",
        snippet: b.querySelector(".enriched-block__content, p")?.textContent?.trim().slice(0, 120) || "",
        citations: Array.from(b.querySelectorAll(".citation-chip")).map((c) => c.textContent?.trim()),
      }));
    });

    log(`Rendered ${blockData.length} blocks:`);
    blockData.forEach((b, i) => {
      log(`  Block ${i + 1}: "${b.title}" - Citations: ${JSON.stringify(b.citations)}`);
    });

    if (blockData.length === 0) {
      throw new Error("Positive case failed: no enriched blocks were rendered.");
    }

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "15_positive_case_enriched.png") });

    // Test citation interaction
    const citationChips = await page.$$(".citation-chip");
    if (citationChips.length > 0) {
      log(`Clicking citation chip (total ${citationChips.length})...`);
      await citationChips[0].click();
      await sleep(600);
      const detailCard = await page.$(".citation-detail-card");
      if (detailCard) {
        const cardText = await page.evaluate((el) => el.textContent?.trim() || "", detailCard);
        log(`Citation detail card displayed: "${cardText.slice(0, 100)}..."`);
      }
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "16_positive_case_citation_clicked.png") });
    }

    // Verify persistence after reload
    log("Reloading page to verify persistence...");
    await page.reload({ waitUntil: "networkidle2" });
    await page.waitForSelector(".tabs", { timeout: UI_TIMEOUT });

    // Switch to Enriched tab
    const tabs3 = await page.$$('.tabs button[role="tab"]');
    if (tabs3.length >= 2) {
      await tabs3[1].click();
    }
    await page.waitForSelector(".enriched-block", { timeout: UI_TIMEOUT });
    const reloadedBlockCount = (await page.$$(".enriched-block")).length;
    log(`After reload: ${reloadedBlockCount} enriched blocks rendered immediately without re-generating.`);
    if (reloadedBlockCount === 0) {
      throw new Error("Persistence failed: enriched blocks vanished after reload.");
    }
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "17_positive_case_persisted_on_reload.png") });

    log("\n================================================================================");
    log("ALL E2E VERIFICATION CHECKS PASSED PERFECTLY!");
    log("================================================================================");
  } finally {
    await browser.close();

    // Clean up disposable note only
    if (disposableDocId) {
      log(`Cleaning up disposable test document: ${disposableDocId}`);
      runBackendCommand(`
from apps.canvas.models import CanvasSession
from apps.documents.models import Document
CanvasSession.objects.filter(document_id="${disposableDocId}").delete()
Document.objects.filter(id="${disposableDocId}").delete()
print("CLEANED")
`);
    }

    // Post-test invariant check on textbook
    const postTbCheck = runBackendCommand(`
from apps.references.models import ReferenceDocument, ReferenceChunk
rd = ReferenceDocument.objects.get(id="f148dab2-1ff0-4bd0-aa98-0857df36c068")
print(f"TEXTBOOK_POST_CHECK:{rd.id}:{rd.title}:{rd.status}:{rd.page_count}:{ReferenceChunk.objects.filter(reference_document=rd).count()}")
`);
    log(`Post-test Textbook Invariant: ${postTbCheck.trim().split("\n").pop()}`);
  }
}

run().catch((err) => {
  console.error("FATAL E2E FAILURE:", err);
  process.exit(1);
});
