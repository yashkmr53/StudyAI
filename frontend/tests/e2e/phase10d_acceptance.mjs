/**
 * Phase 10D — Browser E2E Acceptance Test
 * ========================================
 * Multi-turn chat context: verifies that Ask StudyAI properly maintains
 * conversation history across turns, page reloads, and chat threads.
 *
 * Prerequisites:
 *   - All StudyAI Docker services running (api, worker, beat, frontend, db, redis, minio)
 *   - Ollama running on host with qwen3.5:4b pulled
 *   - Google Chrome installed at standard macOS path
 *   - admin@studyai.dev / AdminPass123! account exists
 *
 * Run:
 *   node frontend/tests/e2e/phase10d_acceptance.mjs
 */
import puppeteer from "puppeteer-core";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, "screenshots", "phase10d");
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP_URL = "http://localhost:5173";

// Timeouts — LLM responses can be slow
const LLM_TIMEOUT = 120_000;
const NAV_TIMEOUT = 15_000;
const UI_TIMEOUT = 10_000;

const consoleLogs = [];
const networkRequests = [];

function log(msg) {
  const ts = new Date().toISOString().substring(11, 23);
  console.log(`[${ts}] ${msg}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Wait for a new assistant message to appear after `existingCount` messages.
 * Returns the text content of the new assistant bubble.
 */
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

      // Ensure input is no longer disabled (meaning streaming & sending finished)
      const input = document.querySelector(".chat-composer input.input");
      if (input && input.disabled) return false;

      // Needs real content
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

/** Count visible message bubbles. */
async function countMessages(page) {
  return page.evaluate(() => document.querySelectorAll(".msg").length);
}

/** Send a message via the chat composer. */
async function sendMessage(page, text) {
  log(`  Sending: "${text}"`);
  await page.waitForSelector(".chat-composer input.input:not(:disabled)", { timeout: UI_TIMEOUT });
  await sleep(400);
  await page.focus(".chat-composer input.input");
  await page.$eval(".chat-composer input.input", (el) => {
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.type(".chat-composer input.input", text);
  await sleep(300);
  await page.waitForSelector('.chat-composer button[type="submit"]:not(:disabled)', { timeout: UI_TIMEOUT });
  await page.click('.chat-composer button[type="submit"]');

  // Verify that the user message was registered and is visible in DOM
  await page.waitForFunction(
    (msgText) => {
      const userBubbles = Array.from(document.querySelectorAll(".msg--user .msg__bubble"));
      return userBubbles.some((b) => b.textContent?.trim() === msgText);
    },
    { timeout: UI_TIMEOUT },
    text,
  );
  log(`  Message "${text}" sent and rendered.`);
}

async function runE2E() {
  log("==============================================================");
  log("=== Starting Phase 10D Browser E2E Acceptance Test ===");
  log("==============================================================");

  const results = {
    startedAt: new Date().toISOString(),
    steps: {},
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
    consoleLogs.push({ type: msg.type(), text: msg.text(), time: new Date().toISOString() });
    if (msg.type() === "error") log(`[Browser Console Error] ${msg.text()}`);
  });

  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/api/") && url.includes("/chat/")) {
      networkRequests.push({ method: req.method(), url, time: new Date().toISOString() });
    }
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

    // Ensure AI_CLASSROOM profile is active
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
    // Step 2: Navigate to Ask StudyAI (Chat Page)
    // ---------------------------------------------------------------
    log("Step 2: Navigate to Ask StudyAI");
    await page.goto(`${APP_URL}/ai-classroom/chat`, { waitUntil: "networkidle2" });
    await page.waitForSelector(".chat-sidebar", { timeout: UI_TIMEOUT });
    log("Chat page loaded.");
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_chat_page.png") });
    results.checklist.chatPageLoaded = true;

    // ---------------------------------------------------------------
    // Step 3: Create a new chat (Chat A) for multi-turn test
    // ---------------------------------------------------------------
    log("Step 3: Create Chat A for multi-turn test");
    await page.click(".btn--secondary.btn--block"); // "New Chat" button
    await sleep(1000);

    // Wait for chat panel to appear
    await page.waitForSelector(".chat-panel .chat-composer", { timeout: UI_TIMEOUT });
    const chatAUrl = await page.evaluate(() => window.location.search);
    log(`Chat A created. URL params: ${chatAUrl}`);
    results.checklist.chatACreated = true;

    // ---------------------------------------------------------------
    // Step 4: Multi-turn conversation — Turn 1
    // ---------------------------------------------------------------
    log("Step 4: Multi-turn conversation — Turn 1: 'Explain backpropagation.'");
    let msgCount = await countMessages(page);
    await sendMessage(page, "Explain backpropagation.");
    const turn1Reply = await waitForAssistantReply(page, msgCount);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_turn1_backprop.png") });
    results.steps.turn1 = { sent: "Explain backpropagation.", replyLength: turn1Reply.length };
    results.checklist.turn1Replied = turn1Reply.length > 20;

    // ---------------------------------------------------------------
    // Step 5: Multi-turn — Turn 2: contextual "yes"
    // ---------------------------------------------------------------
    log("Step 5: Multi-turn conversation — Turn 2: 'yes'");
    msgCount = await countMessages(page);
    await sendMessage(page, "yes");
    const turn2Reply = await waitForAssistantReply(page, msgCount);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_turn2_yes.png") });
    results.steps.turn2 = { sent: "yes", replyLength: turn2Reply.length };

    // Verify the reply is contextual — it should NOT be a generic "what do you want to study" response
    const genericPhrases = [
      "ready to dive into some study material",
      "what topic would you like",
      "what would you like to learn",
      "i can help you study",
    ];
    const isGeneric = genericPhrases.some((p) => turn2Reply.toLowerCase().includes(p));
    results.checklist.turn2IsContextual = !isGeneric;

    if (isGeneric) {
      log("❌ FAIL: Turn 2 reply is generic — multi-turn context NOT working!");
    } else {
      log("✅ Turn 2 reply is contextual — multi-turn context is working!");
    }

    // ---------------------------------------------------------------
    // Step 6: Multi-turn — Turn 3: explicit follow-up
    // ---------------------------------------------------------------
    log("Step 6: Multi-turn conversation — Turn 3: 'Can you give a concrete example with numbers?'");
    msgCount = await countMessages(page);
    await sendMessage(page, "Can you give a concrete example with numbers?");
    const turn3Reply = await waitForAssistantReply(page, msgCount);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_turn3_example.png") });
    results.steps.turn3 = { sent: "Can you give a concrete example with numbers?", replyLength: turn3Reply.length };
    results.checklist.turn3Replied = turn3Reply.length > 20;

    // ---------------------------------------------------------------
    // Step 7: Verify 6 message bubbles (3 user + 3 assistant)
    // ---------------------------------------------------------------
    const totalBubbles = await countMessages(page);
    log(`Total message bubbles visible: ${totalBubbles}`);
    results.checklist.allBubblesVisible = totalBubbles >= 6;

    // Capture the Chat A session ID from URL
    const chatASessionId = await page.evaluate(() => {
      const params = new URLSearchParams(window.location.search);
      return params.get("session");
    });
    log(`Chat A session ID: ${chatASessionId}`);

    // ---------------------------------------------------------------
    // Step 8: Page reload — verify persistence
    // ---------------------------------------------------------------
    log("Step 8: Reload page and verify conversation persistence");
    await page.reload({ waitUntil: "networkidle2" });
    await page.waitForSelector(".chat-messages", { timeout: UI_TIMEOUT });
    await page.waitForFunction(
      () => document.querySelectorAll(".msg").length >= 6,
      { timeout: UI_TIMEOUT },
    );

    const bubblesAfterReload = await countMessages(page);
    log(`Message bubbles after reload: ${bubblesAfterReload}`);
    results.checklist.messagesPersistedAfterReload = bubblesAfterReload >= 6;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_after_reload.png") });

    // Verify same session ID persisted
    const sessionIdAfterReload = await page.evaluate(() => {
      const params = new URLSearchParams(window.location.search);
      return params.get("session");
    });
    log(`Session ID after reload: ${sessionIdAfterReload}`);
    results.checklist.sessionIdPreserved = chatASessionId === sessionIdAfterReload;

    // ---------------------------------------------------------------
    // Step 9: Continue conversation after reload
    // ---------------------------------------------------------------
    log("Step 9: Continue conversation after reload — Turn 4: 'What about vanishing gradients?'");
    msgCount = await countMessages(page);
    await sendMessage(page, "What about vanishing gradients?");
    const turn4Reply = await waitForAssistantReply(page, msgCount);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "07_turn4_after_reload.png") });
    results.steps.turn4 = { sent: "What about vanishing gradients?", replyLength: turn4Reply.length };
    results.checklist.turn4AfterReloadReplied = turn4Reply.length > 20;

    // ---------------------------------------------------------------
    // Step 10: Create Chat B — verify isolation
    // ---------------------------------------------------------------
    log("Step 10: Create Chat B for isolation test");
    await page.click(".btn--secondary.btn--block");
    await sleep(1500);

    const chatBSessionId = await page.evaluate(() => {
      const params = new URLSearchParams(window.location.search);
      return params.get("session");
    });
    log(`Chat B session ID: ${chatBSessionId}`);
    results.checklist.chatBCreated = chatBSessionId !== chatASessionId;

    // Chat B should start empty
    await page.waitForFunction(
      () => document.querySelectorAll(".msg").length === 0,
      { timeout: UI_TIMEOUT },
    );
    const chatBBubbles = await countMessages(page);
    log(`Chat B bubbles (should be 0): ${chatBBubbles}`);
    results.checklist.chatBStartsEmpty = chatBBubbles === 0;

    // Send a message in Chat B about a different topic
    log("Sending message in Chat B: 'What is a SQL JOIN?'");
    msgCount = await countMessages(page);
    await sendMessage(page, "What is a SQL JOIN?");
    const chatBReply = await waitForAssistantReply(page, msgCount);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "08_chat_b.png") });
    results.steps.chatB = { sent: "What is a SQL JOIN?", replyLength: chatBReply.length };
    results.checklist.chatBReplied = chatBReply.length > 10;

    // ---------------------------------------------------------------
    // Step 11: Switch back to Chat A — verify history intact
    // ---------------------------------------------------------------
    log(`Step 11: Switch back to Chat A (${chatASessionId}) — verify history intact`);
    const chatASelector = `.chat-thread-item[data-session-id="${chatASessionId}"]`;
    await page.waitForSelector(chatASelector, { timeout: UI_TIMEOUT });
    await page.click(chatASelector);

    await page.waitForFunction(
      (targetId) => {
        const params = new URLSearchParams(window.location.search);
        return params.get("session") === targetId;
      },
      { timeout: UI_TIMEOUT },
      chatASessionId,
    );

    await page.waitForFunction(
      () => document.querySelectorAll(".msg").length >= 6,
      { timeout: UI_TIMEOUT },
    );
    const chatABubblesAfterSwitch = await countMessages(page);
    log(`Chat A bubbles after switch-back: ${chatABubblesAfterSwitch}`);
    results.checklist.chatAHistoryIntact = chatABubblesAfterSwitch >= 6;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "09_chat_a_restored.png") });

    // ---------------------------------------------------------------
    // Step 12: Verify network requests use correct session IDs
    // ---------------------------------------------------------------
    log("Step 12: Verify network requests");
    const chatARequests = networkRequests.filter(
      (r) => r.url.includes(chatASessionId) && r.method === "POST"
    );
    const chatBRequests = networkRequests.filter(
      (r) => r.url.includes(chatBSessionId) && r.method === "POST"
    );
    log(`Chat A POST requests: ${chatARequests.length}`);
    log(`Chat B POST requests: ${chatBRequests.length}`);
    results.checklist.correctSessionIds = chatARequests.length >= 3 && chatBRequests.length >= 1;

    // ---------------------------------------------------------------
    // Summary
    // ---------------------------------------------------------------
    results.completedAt = new Date().toISOString();
    results.networkRequestCount = networkRequests.length;
    results.consoleErrorCount = consoleLogs.filter((l) => l.type === "error").length;

    log("");
    log("==============================================================");
    log("=== Phase 10D E2E Acceptance Test — Results ===");
    log("==============================================================");

    const checklistEntries = Object.entries(results.checklist);
    let passed = 0;
    let failed = 0;
    for (const [key, value] of checklistEntries) {
      const icon = value ? "✅" : "❌";
      log(`  ${icon} ${key}: ${value}`);
      if (value) passed++;
      else failed++;
    }

    log("");
    log(`Passed: ${passed}/${checklistEntries.length}`);
    log(`Failed: ${failed}/${checklistEntries.length}`);
    log(`Screenshots: ${SCREENSHOTS_DIR}`);

    // Write results JSON
    const resultsPath = path.join(SCREENSHOTS_DIR, "results.json");
    fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));
    log(`Results written to: ${resultsPath}`);

    if (failed > 0) {
      log("");
      log("❌ PHASE 10D E2E: SOME CHECKS FAILED");
      process.exitCode = 1;
    } else {
      log("");
      log("✅ PHASE 10D E2E: ALL CHECKS PASSED");
    }

    await browser.close();
  } catch (err) {
    log(`\n❌ FATAL ERROR: ${err.message}`);
    log(err.stack);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "99_fatal_error.png") }).catch(() => {});
    results.fatalError = err.message;

    const resultsPath = path.join(SCREENSHOTS_DIR, "results.json");
    fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));

    await browser.close();
    process.exitCode = 1;
  }
}

runE2E();
