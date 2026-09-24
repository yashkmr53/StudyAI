/**
 * E2E Puppeteer test for Dynamic Sidebar (open/collapse, keyboard shortcut, persistence).
 */
import puppeteer from "puppeteer-core";
import path from "path";
import fs from "fs";

const SCREENSHOTS_DIR = path.resolve("frontend/tests/e2e/screenshots/sidebar");
if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

const CHROME_PATH =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

async function run() {
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
    defaultViewport: { width: 1280, height: 800 },
  });

  const page = await browser.newPage();

  console.log("Navigating to login...");
  await page.goto("http://localhost:5173/login", { waitUntil: "networkidle0" });

  await page.type("input[type=email]", "admin@studyai.dev");
  await page.type("input[type=password]", "AdminPass123!");
  await page.click("button[type=submit]");
  await page.waitForNavigation({ waitUntil: "networkidle0" });

  console.log("Logged in. Checking initial sidebar state...");
  await page.waitForSelector(".sidebar", { timeout: 10000 });

  const initialSidebarBounds = await page.evaluate(() => {
    const sidebar = document.querySelector(".sidebar");
    const rect = sidebar.getBoundingClientRect();
    return { width: rect.width, right: rect.right, left: rect.left };
  });

  console.log("Initial sidebar bounds:", initialSidebarBounds);
  if (initialSidebarBounds.width < 200) {
    throw new Error(`Expected sidebar to be expanded initially, but width is ${initialSidebarBounds.width}`);
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_sidebar_expanded.png") });

  // 1. Click collapse button in sidebar header
  console.log("Testing collapse button click...");
  const collapseBtn = await page.waitForSelector(".sidebar-collapse-btn", { timeout: 5000 });
  await collapseBtn.click();
  await new Promise((r) => setTimeout(r, 400)); // wait for transition

  const collapsedState = await page.evaluate(() => {
    const shell = document.querySelector(".shell");
    const sidebar = document.querySelector(".sidebar");
    const expandBtn = document.querySelector(".sidebar-expand-btn");
    const sidebarRect = sidebar.getBoundingClientRect();
    const isShellCollapsed = shell.classList.contains("shell--collapsed");
    return {
      isShellCollapsed,
      sidebarRight: sidebarRect.right,
      hasExpandBtn: Boolean(expandBtn),
      storedPreference: localStorage.getItem("studyai.sidebar_collapsed"),
    };
  });

  console.log("Collapsed state:", collapsedState);
  if (!collapsedState.isShellCollapsed) {
    throw new Error("Expected shell to have shell--collapsed class");
  }
  if (!collapsedState.hasExpandBtn) {
    throw new Error("Expected sidebar-expand-btn to be present when collapsed");
  }
  if (collapsedState.storedPreference !== "true") {
    throw new Error(`Expected localStorage preference to be 'true', got '${collapsedState.storedPreference}'`);
  }
  console.log("✅ Sidebar collapsed cleanly, expand button rendered, and preference persisted.");
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_sidebar_collapsed.png") });

  // 2. Click expand button to restore
  console.log("Testing expand button click...");
  const expandBtn = await page.waitForSelector(".sidebar-expand-btn", { timeout: 5000 });
  await expandBtn.click();
  await new Promise((r) => setTimeout(r, 400)); // wait for transition

  const expandedState = await page.evaluate(() => {
    const shell = document.querySelector(".shell");
    const sidebar = document.querySelector(".sidebar");
    const expandBtn = document.querySelector(".sidebar-expand-btn");
    const sidebarRect = sidebar.getBoundingClientRect();
    return {
      isShellCollapsed: shell.classList.contains("shell--collapsed"),
      sidebarWidth: sidebarRect.width,
      hasExpandBtn: Boolean(expandBtn),
      storedPreference: localStorage.getItem("studyai.sidebar_collapsed"),
    };
  });

  console.log("Expanded state:", expandedState);
  if (expandedState.isShellCollapsed) {
    throw new Error("Expected shell not to have shell--collapsed class after clicking expand");
  }
  if (expandedState.hasExpandBtn) {
    throw new Error("Expected sidebar-expand-btn to be hidden when expanded");
  }
  if (expandedState.storedPreference !== "false") {
    throw new Error(`Expected localStorage preference to be 'false', got '${expandedState.storedPreference}'`);
  }
  console.log("✅ Sidebar expanded cleanly and preference updated.");
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_sidebar_re_expanded.png") });

  // 3. Test keyboard shortcut Cmd+\ / Ctrl+\
  console.log("Testing keyboard shortcut (Cmd+\\ / Ctrl+\\)...");
  await page.keyboard.down("Meta");
  await page.keyboard.press("Backslash");
  await page.keyboard.up("Meta");
  await new Promise((r) => setTimeout(r, 400));

  const hotkeyCollapsed = await page.evaluate(() => {
    return document.querySelector(".shell").classList.contains("shell--collapsed");
  });
  console.log("Hotkey toggled to collapsed:", hotkeyCollapsed);
  if (!hotkeyCollapsed) {
    throw new Error("Expected Cmd+\\ to collapse the sidebar");
  }

  // Toggle again via hotkey
  await page.keyboard.down("Meta");
  await page.keyboard.press("Backslash");
  await page.keyboard.up("Meta");
  await new Promise((r) => setTimeout(r, 400));

  const hotkeyExpanded = await page.evaluate(() => {
    return !document.querySelector(".shell").classList.contains("shell--collapsed");
  });
  console.log("Hotkey toggled to expanded:", hotkeyExpanded);
  if (!hotkeyExpanded) {
    throw new Error("Expected Cmd+\\ to expand the sidebar back");
  }
  console.log("✅ Keyboard shortcut Cmd+\\ toggles sidebar open and closed reliably.");

  // 4. Test page reload persistence
  console.log("Testing reload persistence while collapsed...");
  await page.keyboard.down("Meta");
  await page.keyboard.press("Backslash");
  await page.keyboard.up("Meta");
  await new Promise((r) => setTimeout(r, 200));

  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector(".shell", { timeout: 10000 });

  const persistedCollapsed = await page.evaluate(() => {
    return document.querySelector(".shell").classList.contains("shell--collapsed");
  });
  console.log("After reload, is collapsed:", persistedCollapsed);
  if (!persistedCollapsed) {
    throw new Error("Expected sidebar to remain collapsed after page reload");
  }
  console.log("✅ Persisted collapsed state restored on reload.");

  // Restore sidebar for normal state
  const finalExpandBtn = await page.waitForSelector(".sidebar-expand-btn", { timeout: 5000 });
  await finalExpandBtn.click();
  await new Promise((r) => setTimeout(r, 400));

  await browser.close();
  console.log("\n🎉 ALL DYNAMIC SIDEBAR TESTS PASSED SUCCESSFULLY!");
}

run().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
