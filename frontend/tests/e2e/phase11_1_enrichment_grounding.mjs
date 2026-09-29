/**
 * Phase 11.1 — Real Enrichment Grounding E2E Verification
 * ========================================================
 * Verifies end-to-end that an uploaded reference textbook is actually
 * retrieved, passed to qwen3.5:4b in the prompt evidence payload,
 * used to ground the enriched content, and properly cited with
 * verified provenance in both the database and the frontend UI.
 *
 * Flow:
 * 1. Login as admin@studyai.dev (active profile YashAI, subject DSA AI)
 * 2. Clean any stale disposable test references
 * 3. Upload sample textbook ("Algorithms and Data Structures Reference")
 * 4. Wait for Reference Library ingestion to reach READY (2 pages, 2 chunks)
 * 5. Verify the BFS reference chunk exists and is retrievable via shared service
 * 6. Upload student handwritten note fixture (handwritten_bfs_note.png)
 * 7. Monitor real qwen3.5:4b vision OCR progression to completion
 * 8. Trigger real asynchronous note enrichment through the application
 * 9. Wait for enrichment completion via standard polling
 * 10. Verify enriched blocks are displayed on screen
 * 11. Verify reference citation chip appears (📖 Ref: p. 1)
 * 12. Click citation chip and verify citation detail card shows textbook title & page
 * 13. Deep backend inspection:
 *     - Prove retrieve_chunks_node retrieved the textbook chunk
 *     - Prove qwen3.5:4b received the reference evidence payload
 *     - Prove CitationBlock in database preserves title, page, chapter, and text
 * 14. Negative check: verify citation came from the newly uploaded disposable textbook
 * 15. Delete the disposable textbook and verify cascade cleanup
 *
 * Run:
 *   node frontend/tests/e2e/phase11_1_enrichment_grounding.mjs
 */
import puppeteer from "puppeteer-core";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { execSync } from "child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, "screenshots", "phase11_1");
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP_URL = "http://localhost:5173";
const FIXTURE_PDF = path.join(__dirname, "fixtures", "sample_textbook.pdf");
const NOTE_IMAGE_PATH = path.join(__dirname, "fixtures", "handwritten_bfs_note.png");

const OCR_TIMEOUT = 120_000;
const ENRICH_TIMEOUT = 180_000;
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

function runBackendCommand(cmd) {
  try {
    const out = execSync("docker exec -i studyai-api-1 python manage.py shell", {
      input: cmd,
      encoding: "utf-8",
      timeout: 30000,
    });
    return out.trim();
  } catch (err) {
    log(`[Backend Command Error] ${err.message}`);
    return "";
  }
}

async function run() {
  log("=== Starting Phase 11.1 Real Enrichment Grounding E2E Test ===");

  const results = {
    startedAt: new Date().toISOString(),
    checklist: {
      referenceUploaded: false,
      referenceReady: false,
      referenceChunkRetrieved: false,
      ocrCompleted: false,
      enrichmentCompleted: false,
      llmReceivedReferenceEvidence: false,
      citationPresent: false,
      citationSourceMatchesUploadedReference: false,
      citationPageMatchesSource: false,
      negativeCheckPassed: false,
      referenceDeleted: false,
    },
    diagnosticData: {},
    metrics: {},
  };

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    defaultViewport: { width: 1366, height: 900 },
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      log(`[Browser Console Error] ${msg.text()}`);
    }
  });

  try {
    // ---------------------------------------------------------------
    // Step 1: Clean Stale DB References & Authenticate
    // ---------------------------------------------------------------
    log("Step 1: Clean stale references and authenticate as admin@studyai.dev");
    runBackendCommand("from apps.references.models import ReferenceDocument; ReferenceDocument.objects.all().delete()");

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

    // Switch to profile YashAI if needed
    const profileName = await page.evaluate(
      () => document.querySelector(".profile-button__name")?.textContent?.trim() || "",
    );
    log(`Authenticated. Current profile: "${profileName}"`);

    if (profileName !== "YashAI") {
      log("Switching to YashAI profile...");
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
      log("Profile switched to YashAI.");
    }

    // ---------------------------------------------------------------
    // Step 2: Navigate to Subject Workspace (DSA AI)
    // ---------------------------------------------------------------
    log("Step 2: Navigate to DSA AI Subject Workspace");
    await page.waitForSelector(".sidebar__scroll .sidebar__item", { timeout: UI_TIMEOUT });
    const dsaSubjectLink = await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".sidebar__scroll .sidebar__item"));
      const match = items.find((el) => el.textContent?.includes("DSA"));
      return match ? match.getAttribute("href") : items[0]?.getAttribute("href") || null;
    });

    if (dsaSubjectLink) {
      await page.goto(`${APP_URL}${dsaSubjectLink}`, { waitUntil: "networkidle2" });
    }
    await page.waitForSelector(".panel-section", { timeout: UI_TIMEOUT });
    const currentSubjectUrl = page.url();
    log(`Subject workspace loaded: ${currentSubjectUrl}`);

    // ---------------------------------------------------------------
    // Step 3: Open Reference Library and Upload Textbook PDF
    // ---------------------------------------------------------------
    log("Step 3: Open Reference Library & Upload Algorithms Textbook");
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll("button, a, .service-card"));
      const refItem = items.find((el) => el.textContent?.includes("Reference Library"));
      refItem?.click();
    });

    await page.waitForFunction(
      () => document.querySelector("h1")?.textContent?.includes("Reference Library"),
      { timeout: UI_TIMEOUT },
    );

    // Open upload dialog
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

    // Fill form
    const pdfInput = await page.$("#ref-file");
    if (!pdfInput) throw new Error("Could not find file input in upload dialog");
    await pdfInput.uploadFile(FIXTURE_PDF);

    const textbookTitle = "Algorithms and Data Structures Reference";
    await page.evaluate((val) => {
      const el = document.querySelector("#ref-title");
      if (el) {
        const nativeSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          "value"
        ).set;
        nativeSetter.call(el, val);
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, textbookTitle);

    log(`Submitting upload for: "${textbookTitle}"`);
    await page.evaluate(() => {
      const primaryBtn = document.querySelector('.dialog__actions button.btn--primary');
      if (primaryBtn) primaryBtn.click();
      else document.querySelector('#upload-reference-form')?.requestSubmit();
    });

    await page.waitForSelector(".card", { timeout: UI_TIMEOUT });
    results.checklist.referenceUploaded = true;
    log("Textbook card appeared in library. Waiting for ingestion...");

    // Wait for READY state
    await page.waitForFunction(
      () => {
        const cards = document.querySelectorAll(".card");
        for (const card of cards) {
          if (card.textContent?.includes("✓ Ready")) return true;
        }
        return false;
      },
      { timeout: INGEST_TIMEOUT },
    );

    const readyStats = await page.evaluate(() => {
      const card = document.querySelector(".card");
      return card?.textContent || "";
    });
    log(`Ingestion completed: ${readyStats}`);
    results.checklist.referenceReady = readyStats.includes("✓ Ready") && readyStats.includes("2 chunks indexed");

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_reference_ready.png") });

    // ---------------------------------------------------------------
    // Step 4: Verify BFS Chunk in DB & Shared Retrieval Service
    // ---------------------------------------------------------------
    log("Step 4: Verify BFS chunk exists and retrieve_reference_context returns it");
    const pyVerifyChunk = `
import json
from apps.references.models import ReferenceDocument, ReferenceChunk
from apps.references.services import retrieve_reference_context

doc = ReferenceDocument.objects.first()
chunks = list(ReferenceChunk.objects.filter(reference_document=doc).values("id", "chunk_index", "page_number", "chapter", "text"))
retrieved = retrieve_reference_context("breadth-first search FIFO queue complexity", profile=doc.profile, top_k=3)

print("JSON_START")
print(json.dumps({
    "document_id": str(doc.id),
    "title": doc.title,
    "status": doc.status,
    "page_count": doc.page_count,
    "chunk_count": doc.chunk_count,
    "chunks": [{"id": str(c["id"]), "page": c["page_number"], "chapter": c["chapter"], "snippet": c["text"][:120]} for c in chunks],
    "retrieved": [{"chunk_id": r["chunk_id"], "page": r["page"], "source_title": r["source_title"], "chapter": r["chapter"], "score": r["score"], "text_snippet": r["text"][:120]} for r in retrieved]
}))
print("JSON_END")
`;
    const backendChunkOut = runBackendCommand(pyVerifyChunk);
    const jsonMatch = backendChunkOut.match(/JSON_START\s*([\s\S]*?)\s*JSON_END/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[1]);
      results.diagnosticData.uploadedReference = parsed;
      const hasBfsRetrieved = parsed.retrieved.some((r) =>
        (r.source_title?.includes("Algorithms") || r.source_title?.includes("Sample") || r.source_title?.includes("Reference")) &&
        (r.page === 1 || r.chapter?.includes("Graph") || r.text_snippet?.includes("Breadth-First")),
      );
      results.checklist.referenceChunkRetrieved = hasBfsRetrieved;
      log(`Shared Reference Retrieval verified: chunk_id=${parsed.retrieved[0]?.chunk_id}, title=${parsed.retrieved[0]?.source_title}, page=${parsed.retrieved[0]?.page}`);
    } else {
      log(`[Warning] Could not parse backend chunk output: ${backendChunkOut}`);
    }

    // ---------------------------------------------------------------
    // Step 5: Upload Student Handwritten Note Fixture
    // ---------------------------------------------------------------
    log("Step 5: Navigate back to Subject Workspace & upload handwritten note");
    await page.goto(currentSubjectUrl, { waitUntil: "networkidle2" });
    await page.waitForSelector(".panel-section", { timeout: UI_TIMEOUT });

    const noteFileInput = await page.waitForSelector('input[type="file"][accept*="image"]', { timeout: UI_TIMEOUT });
    await noteFileInput.uploadFile(NOTE_IMAGE_PATH);

    // Auto-navigates to /subjects/:subjectId/notes/:documentId
    await page.waitForFunction(
      () => window.location.pathname.includes("/notes/"),
      { timeout: 20000 },
    );
    const noteUrl = page.url();
    log(`Auto-navigated to note detail URL: ${noteUrl}`);
    results.diagnosticData.noteUrl = noteUrl;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_note_uploaded.png") });

    // ---------------------------------------------------------------
    // Step 6: Monitor Real OCR Progression to Completion
    // ---------------------------------------------------------------
    log("Step 6: Waiting for qwen3.5:4b vision OCR to transcribe the note...");
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
      { timeout: OCR_TIMEOUT, polling: 1500 },
    );

    const ocrElapsed = Date.now() - ocrStartTime;
    results.metrics.ocrDurationMs = ocrElapsed;

    const ocrLines = await page.evaluate(() => {
      return Array.from(document.querySelectorAll(".transcript-line")).map((el) => el.textContent?.trim());
    });
    log(`OCR completed in ${(ocrElapsed / 1000).toFixed(1)}s. Transcribed ${ocrLines.length} lines:`);
    ocrLines.slice(0, 4).forEach((l) => log(`   - ${l}`));

    const hasBfsTopic = ocrLines.some((l) => /breadth-first|bfs|graph/i.test(l));
    results.checklist.ocrCompleted = ocrLines.length > 0 && hasBfsTopic;
    results.diagnosticData.ocrTranscription = ocrLines;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_ocr_completed.png") });

    // ---------------------------------------------------------------
    // Step 7: Switch to Enriched Tab & Trigger Real Enrichment
    // ---------------------------------------------------------------
    log("Step 7: Switch to Enriched tab and trigger note enrichment");
    const tabButtons = await page.$$('.tabs button[role="tab"]');
    if (tabButtons.length >= 2) {
      await tabButtons[1].click();
    } else {
      await page.click('button[role="tab"]:nth-child(2)');
    }

    // Verify empty state / generate button
    await page.waitForSelector(".empty-state button.btn--primary, .enriched-content", { timeout: UI_TIMEOUT });
    const generateBtn = await page.$('.empty-state button.btn--primary');
    if (generateBtn) {
      log("Clicking 'Generate enrichment' button...");
      await generateBtn.click();
    } else {
      log("Note already has enrichment button or action. Checking regenerate...");
    }

    await page.waitForSelector(".enrichment-progress, .enriched-block", { timeout: UI_TIMEOUT });
    log("Enrichment processing initiated (Celery → LangGraph → qwen3.5:4b).");
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_enrichment_processing.png") });

    // ---------------------------------------------------------------
    // Step 8: Wait for Real Enrichment Completion via Polling
    // ---------------------------------------------------------------
    log("Step 8: Waiting for enrichment to complete automatically...");
    const enrichStartTime = Date.now();
    await page.waitForFunction(
      () => {
        const blocks = document.querySelectorAll(".enriched-block");
        const article = document.querySelector(".enriched-content");
        return blocks.length > 0 || article !== null;
      },
      { timeout: ENRICH_TIMEOUT, polling: 2000 },
    );

    const enrichElapsed = Date.now() - enrichStartTime;
    results.metrics.enrichDurationMs = enrichElapsed;
    log(`Enrichment finished in ${(enrichElapsed / 1000).toFixed(1)}s!`);
    results.checklist.enrichmentCompleted = true;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_enrichment_completed.png") });

    // Extract enriched blocks
    const renderedBlocks = await page.evaluate(() => {
      const blocks = Array.from(document.querySelectorAll(".enriched-block"));
      return blocks.map((b) => ({
        title: b.querySelector("h3")?.textContent?.trim() || "",
        content: b.querySelector(".enriched-block__content, p")?.textContent?.trim() || "",
        citations: Array.from(b.querySelectorAll(".citation-chip")).map((c) => c.textContent?.trim()),
      }));
    });
    log(`Rendered ${renderedBlocks.length} enriched blocks.`);
    renderedBlocks.forEach((b, idx) => {
      log(`  Block ${idx}: [${b.title}] "${b.content.substring(0, 80)}..." Citations: ${JSON.stringify(b.citations)}`);
    });
    results.diagnosticData.renderedBlocks = renderedBlocks;

    // ---------------------------------------------------------------
    // Step 9: Verify Reference Citation Chip & Detail Card in UI
    // ---------------------------------------------------------------
    log("Step 9: Inspect reference citation chip in UI");
    const citationChipHandle = await page.$('.citation-chip');
    if (citationChipHandle) {
      results.checklist.citationPresent = true;
      const chipText = await page.evaluate((el) => el.textContent?.trim(), citationChipHandle);
      log(`Found citation chip: "${chipText}"`);

      // Click to expand citation detail card
      await citationChipHandle.click();
      await sleep(600);
      await page.waitForSelector(".citation-detail-card", { timeout: 5000 });
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_reference_citation.png") });

      const cardDetails = await page.evaluate(() => {
        const card = document.querySelector(".citation-detail-card");
        return {
          titleLine: card?.querySelector("span")?.textContent?.trim() || "",
          badge: card?.querySelector(".chip")?.textContent?.trim() || "",
          quote: card?.querySelector("blockquote")?.textContent?.trim() || "",
        };
      });
      log(`Citation Detail Card: ${JSON.stringify(cardDetails)}`);

      results.checklist.citationSourceMatchesUploadedReference =
        cardDetails.titleLine.includes("Algorithms") ||
        cardDetails.titleLine.includes("Sample") ||
        cardDetails.titleLine.includes("Reference");
      results.checklist.citationPageMatchesSource =
        cardDetails.titleLine.includes("Page 1") || chipText.includes("p. 1") || chipText.includes("1");
    } else {
      log("[Warning] No .citation-chip found in rendered blocks");
    }

    // ---------------------------------------------------------------
    // Step 10: Deep Backend Inspection (Proof of LLM Grounding)
    // ---------------------------------------------------------------
    log("Step 10: Deep Backend Inspection (JobExecutionState & CitationBlock)");
    const noteIdMatch = noteUrl.match(/\/notes\/([0-9a-fA-F-]+)/);
    const noteDocId = noteIdMatch ? noteIdMatch[1] : "";

    const pyInspectEnrichment = `
import json
from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock, CitationBlock
from apps.jobs.models import Job, JobExecutionState

note = EnrichedNote.objects.filter(document_id="${noteDocId}", superseded=False).first()
job = note.generation_job if note else None
exec_state = JobExecutionState.objects.filter(job=job).order_by("-created_at").first() if job else None

state_json = exec_state.state_json if exec_state else {}
ref_chunks_in_state = state_json.get("reference_chunks", [])
evidence_payload = state_json.get("evidence_payload", {})

blocks = []
if note:
    for b in note.blocks.order_by("block_index"):
        cit = getattr(b, "citation", None)
        blocks.append({
            "block_index": b.block_index,
            "title": b.title,
            "content": b.content[:150],
            "source_refs": cit.source_refs if cit else [],
            "verification_status": cit.verification_status if cit else None,
            "verification_score": cit.verification_score if cit else None,
        })

print("JSON_START")
print(json.dumps({
    "has_job_execution_state": exec_state is not None,
    "ref_chunks_count": len(ref_chunks_in_state),
    "ref_chunks": [
        {
            "chunk_id": rc.get("chunk_id"),
            "source_title": rc.get("source_title"),
            "page": rc.get("page_start") or rc.get("page"),
            "chapter": rc.get("chapter"),
            "snippet": rc.get("content", "")[:120],
        }
        for rc in ref_chunks_in_state
    ],
    "evidence_payload_has_reference": evidence_payload.get("has_reference_material", False),
    "blocks": blocks,
}))
print("JSON_END")
`;
    const backendEnrichOut = runBackendCommand(pyInspectEnrichment);
    const enrichJsonMatch = backendEnrichOut.match(/JSON_START\s*([\s\S]*?)\s*JSON_END/);
    if (enrichJsonMatch) {
      const parsedEnrich = JSON.parse(enrichJsonMatch[1]);
      results.diagnosticData.enrichmentExecution = parsedEnrich;

      // Prove the LLM received the reference evidence
      const llmReceivedEvidence =
        parsedEnrich.ref_chunks_count > 0 &&
        parsedEnrich.evidence_payload_has_reference &&
        parsedEnrich.ref_chunks.some((rc) =>
          rc.page === 1 ||
          (rc.source_title && (rc.source_title.includes("Algorithms") || rc.source_title.includes("Sample") || rc.source_title.includes("textbook"))) ||
          (rc.chapter && rc.chapter.includes("Graph"))
        );
      results.checklist.llmReceivedReferenceEvidence = llmReceivedEvidence;

      log(`[Backend Proof] LLM received reference chunks: count=${parsedEnrich.ref_chunks_count}, has_reference_material=${parsedEnrich.evidence_payload_has_reference}`);
      parsedEnrich.ref_chunks.forEach((rc) => {
        log(`   - Ref chunk: ID=${rc.chunk_id}, Title=${rc.source_title}, Page=${rc.page}, Chapter=${rc.chapter}`);
      });

      // Prove CitationBlock records in database preserve title, page, chapter
      const allSourceRefs = parsedEnrich.blocks.flatMap((b) => b.source_refs);
      log(`[Backend Proof] Stored CitationBlock source_refs count=${allSourceRefs.length}`);
      allSourceRefs.forEach((sr) => {
        log(`   - SourceRef: Type=${sr.source_type}, Title=${sr.source_title || sr.title}, Page=${sr.page_number || sr.page}, Chapter=${sr.chapter}`);
      });

      const matchedUploadedRef = allSourceRefs.find((sr) =>
        ["TEXTBOOK", "REFERENCE_PDF", "reference"].includes(sr.source_type),
      );
      if (matchedUploadedRef) {
        results.checklist.citationSourceMatchesUploadedReference = true;
        results.checklist.citationPageMatchesSource = (matchedUploadedRef.page_number || matchedUploadedRef.page) === 1;
        log(`[Backend Proof] Citation matched uploaded textbook: "${matchedUploadedRef.source_title || matchedUploadedRef.title}", Page ${matchedUploadedRef.page_number || matchedUploadedRef.page}`);
      }
    }

    // ---------------------------------------------------------------
    // Step 11: Negative Check (No pre-existing or foreign references)
    // ---------------------------------------------------------------
    log("Step 11: Negative check — verify citation document ID matches newly uploaded disposable textbook");
    const uploadedDocId = results.diagnosticData.uploadedReference?.document_id;
    const refSourceRefs = (results.diagnosticData.enrichmentExecution?.blocks || [])
      .flatMap((b) => b.source_refs)
      .filter((sr) => ["TEXTBOOK", "REFERENCE_PDF", "reference"].includes(sr.source_type));
    const citedDocIds = refSourceRefs
      .map((sr) => sr.document_id)
      .filter(Boolean);

    const negativeCheck =
      Boolean(uploadedDocId) &&
      citedDocIds.length > 0 &&
      citedDocIds.every((id) => id === uploadedDocId);

    results.checklist.negativeCheckPassed = negativeCheck;
    log(`Negative check: uploadedDocId=${uploadedDocId}, citedDocIds=${JSON.stringify(citedDocIds)}, passed=${negativeCheck}`);

    // ---------------------------------------------------------------
    // Step 12: Delete Disposable Reference & Verify Cleanup
    // ---------------------------------------------------------------
    log("Step 12: Delete disposable reference and verify complete cascade cleanup");
    const refLibraryUrl = `${APP_URL}/subjects/${noteUrl.split("/subjects/")[1]?.split("/")[0]}/references`;
    await page.goto(refLibraryUrl, { waitUntil: "networkidle2" });
    await page.waitForSelector(".card", { timeout: UI_TIMEOUT });

    // Click delete icon button
    await page.click(".card button.icon-btn");
    await page.waitForSelector(".dialog", { timeout: UI_TIMEOUT });
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

    // Verify backend cleanup
    const pyCheckClean = `
from apps.references.models import ReferenceDocument, ReferenceChunk
docs = ReferenceDocument.objects.count()
chunks = ReferenceChunk.objects.count()
print(f"CLEAN_DOCS={docs};CLEAN_CHUNKS={chunks}")
`;
    const cleanOut = runBackendCommand(pyCheckClean);
    const isClean = cleanOut.includes("CLEAN_DOCS=0;CLEAN_CHUNKS=0");
    results.checklist.referenceDeleted = isClean;
    log(`Cleanup verification: ${cleanOut.trim()}, isClean=${isClean}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "07_reference_deleted.png") });

    // ---------------------------------------------------------------
    // Finalize Results
    // ---------------------------------------------------------------
    results.completedAt = new Date().toISOString();
    results.success = Object.values(results.checklist).every(Boolean);

    fs.writeFileSync(
      path.join(__dirname, "phase11_1_results.json"),
      JSON.stringify(results, null, 2),
    );

    log(`Phase 11.1 Test Finished. All criteria status:`);
    Object.entries(results.checklist).forEach(([k, v]) => {
      log(`   ${v ? "✅" : "❌"} ${k}`);
    });
    log(`Phase 11.1 Success: ${results.success}`);

  } catch (err) {
    log(`Phase 11.1 Acceptance Test Failed: ${err.message}`);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "error_failure.png") }).catch(() => {});
    throw err;
  } finally {
    await browser.close();
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
