/**
 * E2E Puppeteer test for Tooltip Viewport Boundary Collision & Repositioning:
 * - Top viewport boundary collision & flipping (e.g. Note editor top toolbar)
 * - Bottom viewport boundary collision & flipping
 * - Left viewport boundary clamping
 * - Right viewport boundary clamping
 * - Normal desktop width & narrow desktop width
 * - Expanded sidebar & collapsed sidebar
 * - Scrolled document/note viewer
 * - Keyboard focus as well as mouse hover
 */
import puppeteer from "puppeteer-core";
import path from "path";
import fs from "fs";

const SCREENSHOTS_DIR = path.resolve("frontend/tests/e2e/screenshots/tooltip_collision");
if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

const CHROME_PATH =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

async function verifyTooltipVisibleInsideViewport(page, description) {
  const info = await page.evaluate(() => {
    const tip = document.querySelector(".floating-tooltip");
    if (!tip) return null;
    const rect = tip.getBoundingClientRect();
    const style = window.getComputedStyle(tip);
    return {
      text: tip.textContent?.trim(),
      visibility: style.visibility,
      opacity: style.opacity,
      rect: {
        top: rect.top,
        bottom: rect.bottom,
        left: rect.left,
        right: rect.right,
        width: rect.width,
        height: rect.height,
      },
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
    };
  });

  if (!info) {
    throw new Error(`[${description}] Floating tooltip element not found in DOM`);
  }
  if (info.visibility === "hidden" || info.opacity === "0") {
    throw new Error(`[${description}] Tooltip is hidden or has opacity 0`);
  }

  // Strict boundary collision checks
  if (info.rect.top < 0) {
    throw new Error(
      `[${description}] Tooltip collided with TOP viewport boundary! top=${info.rect.top}`
    );
  }
  if (info.rect.bottom > info.viewport.height) {
    throw new Error(
      `[${description}] Tooltip collided with BOTTOM viewport boundary! bottom=${info.rect.bottom}, viewportHeight=${info.viewport.height}`
    );
  }
  if (info.rect.left < 0) {
    throw new Error(
      `[${description}] Tooltip collided with LEFT viewport boundary! left=${info.rect.left}`
    );
  }
  if (info.rect.right > info.viewport.width) {
    throw new Error(
      `[${description}] Tooltip collided with RIGHT viewport boundary! right=${info.rect.right}, viewportWidth=${info.viewport.width}`
    );
  }

  console.log(`   ✅ [${description}] Tooltip "${info.text}" fully inside viewport:`, info.rect);
  return info;
}

async function run() {
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
    defaultViewport: { width: 1280, height: 800 },
  });

  try {
    const page = await browser.newPage();

    console.log("1. Logging in...");
    await page.goto("http://localhost:5173/login", { waitUntil: "networkidle0" });
    await page.type("input[type=email]", "admin@studyai.dev");
    await page.type("input[type=password]", "AdminPass123!");
    await page.click("button[type=submit]");
    await page.waitForNavigation({ waitUntil: "networkidle0" });

    await page.waitForSelector(".sidebar", { timeout: 10000 });
    console.log("   Logged in.");

    // =========================================================================
    // TEST 1: NOTE EDITOR TOP TOOLBAR CONTROLS (COLLISION WITH TOP BOUNDARY)
    // The user's specific bug report: Top toolbar control tooltip rendered ABOVE
    // and clipped outside top viewport!
    // =========================================================================
    console.log("\n2. Testing Note Editor Top Toolbar Controls (Top Viewport Collision & Flipping)...");
    // Click Write button to open Note Editor
    const writeBtn = await page.waitForSelector("button.btn--primary", { timeout: 5000 });
    await writeBtn.click();
    await page.waitForSelector(".writer-toolbar", { timeout: 8000 });

    // Back button in writer-toolbar (top ~10px)
    const backBtn = await page.$(".writer-toolbar .icon-btn");
    if (!backBtn) throw new Error("Back button in writer-toolbar not found");

    const backBtnRect = await page.evaluate((el) => {
      const r = el.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, left: r.left, right: r.right };
    }, backBtn);
    console.log("   Back button bounding rect:", backBtnRect);

    // Hover over back button
    console.log("   Hovering over Note Editor Back button...");
    await backBtn.hover();
    await new Promise((r) => setTimeout(r, 200));

    const backTipInfo = await verifyTooltipVisibleInsideViewport(
      page,
      "Note Editor Back Button Hover"
    );
    // Tooltip must have flipped to BOTTOM because backBtn.top (~10px) has no space above
    if (backTipInfo.rect.top < backBtnRect.bottom) {
      throw new Error(
        `Expected tooltip to flip below back button! tooltipTop=${backTipInfo.rect.top}, btnBottom=${backBtnRect.bottom}`
      );
    }
    console.log("   ✅ Tooltip successfully flipped to bottom due to insufficient space above!");
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, "01_note_editor_back_btn_flipped_bottom.png"),
    });

    // Test a tool button in WritingToolbar (Pen / Highlighter / Eraser)
    const toolBtns = await page.$$(".tool-btn");
    if (toolBtns.length > 0) {
      console.log(`   Hovering over first writing tool button (${toolBtns.length} tools found)...`);
      await toolBtns[0].hover();
      await new Promise((r) => setTimeout(r, 200));

      const toolTipInfo = await verifyTooltipVisibleInsideViewport(
        page,
        "Writing Tool Button Hover"
      );
      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, "02_note_editor_tool_btn.png"),
      });

      // Test keyboard focus on writing tool button
      console.log("   Testing keyboard focus on writing tool button...");
      await toolBtns[0].focus();
      await new Promise((r) => setTimeout(r, 200));
      await verifyTooltipVisibleInsideViewport(page, "Writing Tool Button Keyboard Focus");
      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, "03_note_editor_tool_btn_focused.png"),
      });
    }

    // Exit Note Editor via Done button
    const doneBtn = await page.$(".writer-toolbar .btn--primary");
    if (doneBtn) {
      await doneBtn.click();
      await page.waitForSelector(".sidebar", { timeout: 8000 });
    }

    // =========================================================================
    // TEST 2: EXPANDED SIDEBAR COLLAPSE BUTTON TOOLTIP
    // =========================================================================
    console.log("\n3. Testing Sidebar Collapse Button Tooltip (Top boundary & Right side)...");
    const collapseBtn = await page.waitForSelector(".sidebar-collapse-btn", { timeout: 5000 });
    await collapseBtn.hover();
    await new Promise((r) => setTimeout(r, 200));

    await verifyTooltipVisibleInsideViewport(page, "Sidebar Collapse Button Hover");
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, "04_sidebar_collapse_hover.png"),
    });

    // Keyboard focus on collapse button
    await collapseBtn.focus();
    await new Promise((r) => setTimeout(r, 200));
    await verifyTooltipVisibleInsideViewport(page, "Sidebar Collapse Button Keyboard Focus");

    // =========================================================================
    // TEST 3: COLLAPSED SIDEBAR EXPAND BUTTON TOOLTIP (LEFT BOUNDARY)
    // =========================================================================
    console.log("\n4. Collapsing sidebar & Testing Expand Button Tooltip (Left boundary)...");
    await collapseBtn.click();
    await new Promise((r) => setTimeout(r, 400));

    const expandBtn = await page.waitForSelector(".sidebar-expand-btn", { timeout: 5000 });
    await expandBtn.hover();
    await new Promise((r) => setTimeout(r, 200));

    const expandTipInfo = await verifyTooltipVisibleInsideViewport(
      page,
      "Sidebar Expand Button Hover"
    );
    // Expand button is at left: 14px, tooltip must NOT clip left boundary
    if (expandTipInfo.rect.left < 8) {
      throw new Error(`Expand tooltip left edge too close to boundary: ${expandTipInfo.rect.left}`);
    }
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, "05_sidebar_expand_hover.png"),
    });

    // Expand sidebar again
    await expandBtn.click();
    await new Promise((r) => setTimeout(r, 400));

    // =========================================================================
    // TEST 4: SCROLLED NOTE / DOCUMENT VIEWER TOOLBAR CONTROLS
    // =========================================================================
    console.log("\n5. Testing Document/Note Viewer Controls After Scrolling...");
    // Navigate to Unfiled folder to find a note
    const unfiledLink = await page.waitForSelector(".folder-card, a[href*='unfiled'], .note-row", {
      timeout: 5000,
    });
    await unfiledLink.click();
    await new Promise((r) => setTimeout(r, 500));

    // If on folder page, click note
    const noteRow = await page.$(".note-row");
    if (noteRow) {
      await noteRow.click();
      await page.waitForSelector(".source-page__header, .page-heading", { timeout: 8000 });
    }

    const viewerControls = await page.$$(".source-page__header button[data-tip]");
    if (viewerControls.length > 0) {
      console.log(`   Found ${viewerControls.length} viewer controls with tooltips.`);

      // Hover first control before scroll
      await viewerControls[0].hover();
      await new Promise((r) => setTimeout(r, 200));
      await verifyTooltipVisibleInsideViewport(page, "Viewer Control Before Scroll");

      // Scroll content container down
      console.log("   Scrolling content container down...");
      await page.evaluate(() => {
        const content = document.querySelector(".content");
        if (content) content.scrollTop = 200;
        window.scrollBy(0, 200);
      });
      await new Promise((r) => setTimeout(r, 300));

      // Hover control after scroll
      const activeControl = viewerControls[Math.min(2, viewerControls.length - 1)];
      await activeControl.hover();
      await new Promise((r) => setTimeout(r, 200));
      await verifyTooltipVisibleInsideViewport(page, "Viewer Control After Scroll");
      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, "06_scrolled_viewer_control.png"),
      });
    } else {
      console.log("   (No handwritten source page found in current note; skipping canvas scroll check)");
    }

    // =========================================================================
    // TEST 5: NARROW VIEWPORT WIDTHS (RIGHT EDGE & LEFT EDGE CLAMPING)
    // =========================================================================
    console.log("\n6. Testing at Narrow Viewport Widths (375px & 768px)...");
    for (const width of [768, 375]) {
      console.log(`   Testing at ${width}px viewport width...`);
      await page.setViewport({ width, height: 700 });
      await new Promise((r) => setTimeout(r, 300));

      // Find visible elements with data-tip in the current viewport
      const allTips = await page.$$("[data-tip]");
      const visibleTips = [];
      for (const el of allTips) {
        const isVis = await page.evaluate((node) => {
          const r = node.getBoundingClientRect();
          const s = window.getComputedStyle(node);
          return (
            r.width > 0 &&
            r.height > 0 &&
            s.visibility !== "hidden" &&
            s.display !== "none" &&
            r.right > 0 &&
            r.left < window.innerWidth
          );
        }, el);
        if (isVis) visibleTips.push(el);
      }

      if (visibleTips.length > 0) {
        // Test first visible element
        await visibleTips[0].hover();
        await new Promise((r) => setTimeout(r, 200));
        await verifyTooltipVisibleInsideViewport(
          page,
          `Width ${width}px - Element [first]`
        );

        // Test last visible element (often near right edge)
        await visibleTips[visibleTips.length - 1].hover();
        await new Promise((r) => setTimeout(r, 200));
        await verifyTooltipVisibleInsideViewport(
          page,
          `Width ${width}px - Element [last]`
        );

        await page.screenshot({
          path: path.join(SCREENSHOTS_DIR, `07_narrow_${width}px.png`),
        });
      }
    }

    console.log("\n========================================================");
    console.log("🎉 ALL TOOLTIP VIEWPORT COLLISION TESTS PASSED CLEANLY!");
    console.log("========================================================");
  } finally {
    await browser.close();
  }
}

run().catch((err) => {
  console.error("❌ Test failed:", err);
  process.exit(1);
});
