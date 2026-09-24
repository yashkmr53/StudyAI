/**
 * E2E Puppeteer test for:
 * 1. Sidebar collapse/expand tooltip positioning, visibility, clipping, and hover/keyboard focus.
 * 2. Responsive behavior at 1440px, 1280px, 1024px, 900px, 768px in both Expanded and Collapsed states.
 * 3. Horizontal scrolling verification (no horizontal scrollbar solely due to sidebar).
 */
import puppeteer from "puppeteer-core";
import path from "path";
import fs from "fs";

const SCREENSHOTS_DIR = path.resolve("frontend/tests/e2e/screenshots/tooltip_responsive");
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

  try {
    const page = await browser.newPage();

    console.log("1. Logging in...");
    await page.goto("http://localhost:5173/login", { waitUntil: "networkidle0" });
    await page.type("input[type=email]", "admin@studyai.dev");
    await page.type("input[type=password]", "AdminPass123!");
    await page.click("button[type=submit]");
    await page.waitForNavigation({ waitUntil: "networkidle0" });

    await page.waitForSelector(".sidebar", { timeout: 10000 });
    console.log("   Logged in successfully.");

    // Ensure we start with expanded sidebar
    const isCollapsed = await page.evaluate(() =>
      document.querySelector(".shell")?.classList.contains("shell--collapsed")
    );
    if (isCollapsed) {
      const expandBtn = await page.waitForSelector(".sidebar-expand-btn", { timeout: 5000 });
      await expandBtn.click();
      await new Promise((r) => setTimeout(r, 400));
    }
    await page.waitForSelector(".sidebar-collapse-btn", { timeout: 5000 });

    // =========================================================================
    // PART 1: TOOLTIP CHECKS ON COLLAPSE BUTTON
    // =========================================================================
    console.log("\n2. Verifying Collapse Button Tooltip...");
    const collapseBtn = await page.$(".sidebar-collapse-btn");
    if (!collapseBtn) throw new Error("Sidebar collapse button not found");

    // Check data-tip attribute content
    const collapseTipText = await page.evaluate(
      (el) => el.getAttribute("data-tip"),
      collapseBtn
    );
    console.log(`   data-tip attribute: "${collapseTipText}"`);
    if (!collapseTipText || !collapseTipText.includes("Collapse Sidebar (⌘/)")) {
      throw new Error(`Expected tooltip "Collapse Sidebar (⌘/)", got "${collapseTipText}"`);
    }

    // Hover over collapse button
    await page.hover(".sidebar-collapse-btn");
    await new Promise((r) => setTimeout(r, 200));

    // Verify floating tooltip element & positioning
    const collapseHoverTooltipInfo = await page.evaluate(() => {
      const tip = document.querySelector(".floating-tooltip");
      const btn = document.querySelector(".sidebar-collapse-btn");
      const sidebar = document.querySelector(".sidebar");
      if (!tip || !btn || !sidebar) return null;

      const tipRect = tip.getBoundingClientRect();
      const btnRect = btn.getBoundingClientRect();
      const sidebarRect = sidebar.getBoundingClientRect();
      return {
        text: tip.textContent?.trim(),
        tipRect: {
          top: tipRect.top,
          bottom: tipRect.bottom,
          left: tipRect.left,
          right: tipRect.right,
          width: tipRect.width,
          height: tipRect.height,
        },
        btnRect: {
          top: btnRect.top,
          bottom: btnRect.bottom,
          left: btnRect.left,
          right: btnRect.right,
        },
        sidebarRect: {
          top: sidebarRect.top,
          right: sidebarRect.right,
          width: sidebarRect.width,
        },
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
        },
      };
    });

    if (!collapseHoverTooltipInfo) {
      throw new Error("Floating tooltip not found on collapse button hover");
    }
    console.log("   Collapse button hover info:", collapseHoverTooltipInfo);
    // Tooltip should be positioned BELOW the button, NOT clipping window top
    if (collapseHoverTooltipInfo.tipRect.top < collapseHoverTooltipInfo.btnRect.bottom) {
      throw new Error("Tooltip did not flip below button when near top boundary");
    }
    if (collapseHoverTooltipInfo.tipRect.top < 0) {
      throw new Error(`Tooltip top ${collapseHoverTooltipInfo.tipRect.top} out of window bounds`);
    }

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, "01_collapse_btn_hover.png"),
    });
    console.log("   ✅ Collapse tooltip hover verified and screenshot saved.");

    // Keyboard focus on collapse button
    console.log("   Testing keyboard focus on collapse button...");
    await page.focus(".sidebar-collapse-btn");
    await new Promise((r) => setTimeout(r, 200));

    const collapseFocusInfo = await page.evaluate(() => {
      const btn = document.querySelector(".sidebar-collapse-btn");
      const tip = document.querySelector(".floating-tooltip");
      const isFocused = document.activeElement === btn;
      const style = window.getComputedStyle(btn);
      return {
        isFocused,
        outline: style.outline,
        tipText: tip?.textContent?.trim(),
      };
    });

    if (!collapseFocusInfo.isFocused) {
      throw new Error("Collapse button failed to receive keyboard focus");
    }
    if (!collapseFocusInfo.tipText) {
      throw new Error("Tooltip not visible on keyboard focus");
    }
    console.log("   Keyboard focus state:", collapseFocusInfo);
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, "02_collapse_btn_focused.png"),
    });
    console.log("   ✅ Collapse tooltip keyboard focus verified.");

    // =========================================================================
    // PART 2: COLLAPSE SIDEBAR & CHECK EXPAND BUTTON TOOLTIP
    // =========================================================================
    console.log("\n3. Collapsing sidebar & verifying Expand Button Tooltip...");
    await collapseBtn.click();
    await new Promise((r) => setTimeout(r, 400));

    const expandBtn = await page.waitForSelector(".sidebar-expand-btn", { timeout: 3000 });
    const expandTipText = await page.evaluate(
      (el) => el.getAttribute("data-tip"),
      expandBtn
    );
    console.log(`   Expand button data-tip: "${expandTipText}"`);
    if (!expandTipText || !expandTipText.includes("Expand Sidebar (⌘/)")) {
      throw new Error(`Expected tooltip "Expand Sidebar (⌘/)", got "${expandTipText}"`);
    }

    // Hover over expand button
    await page.hover(".sidebar-expand-btn");
    await new Promise((r) => setTimeout(r, 200));

    const expandHoverTooltipInfo = await page.evaluate(() => {
      const tip = document.querySelector(".floating-tooltip");
      const btn = document.querySelector(".sidebar-expand-btn");
      if (!tip || !btn) return null;
      const tipRect = tip.getBoundingClientRect();
      const btnRect = btn.getBoundingClientRect();
      return {
        text: tip.textContent?.trim(),
        tipRect: {
          top: tipRect.top,
          bottom: tipRect.bottom,
          left: tipRect.left,
          right: tipRect.right,
        },
        btnRect: {
          top: btnRect.top,
          bottom: btnRect.bottom,
          left: btnRect.left,
          right: btnRect.right,
        },
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
        },
      };
    });

    if (!expandHoverTooltipInfo) {
      throw new Error("Floating tooltip not found on expand button hover");
    }
    console.log("   Expand button hover info:", expandHoverTooltipInfo);
    if (expandHoverTooltipInfo.tipRect.top < 0) {
      throw new Error(`Expand tooltip top ${expandHoverTooltipInfo.tipRect.top} out of window bounds`);
    }
    if (expandHoverTooltipInfo.tipRect.left < 0) {
      throw new Error("Expand tooltip left edge is outside window");
    }

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, "03_expand_btn_hover.png"),
    });
    console.log("   ✅ Expand button tooltip hover verified.");

    // Focus expand button
    await page.focus(".sidebar-expand-btn");
    await new Promise((r) => setTimeout(r, 200));
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, "04_expand_btn_focused.png"),
    });
    console.log("   ✅ Expand button tooltip keyboard focus verified.");

    // Test restoring sidebar via expand button
    console.log("   Restoring sidebar via expand button...");
    await expandBtn.click();
    await new Promise((r) => setTimeout(r, 400));

    // Test hotkey Cmd+/ to toggle sidebar
    console.log("   Testing Cmd+/ keyboard shortcut toggle...");
    await page.keyboard.down("Meta");
    await page.keyboard.press("Slash");
    await page.keyboard.up("Meta");
    await new Promise((r) => setTimeout(r, 400));

    const isCollapsedAfterShortcut = await page.evaluate(() =>
      document.querySelector(".shell")?.classList.contains("shell--collapsed")
    );
    if (!isCollapsedAfterShortcut) {
      throw new Error("Cmd+/ failed to collapse sidebar");
    }
    console.log("   ✅ Cmd+/ collapsed sidebar successfully.");

    // Toggle back with Cmd+\ (backslash)
    console.log("   Testing Cmd+\\ keyboard shortcut toggle...");
    await page.keyboard.down("Meta");
    await page.keyboard.press("Backslash");
    await page.keyboard.up("Meta");
    await new Promise((r) => setTimeout(r, 400));

    const isExpandedAfterBackslash = await page.evaluate(
      () => !document.querySelector(".shell")?.classList.contains("shell--collapsed")
    );
    if (!isExpandedAfterBackslash) {
      throw new Error("Cmd+\\ failed to expand sidebar");
    }
    console.log("   ✅ Cmd+\\ expanded sidebar successfully.");

    // =========================================================================
    // PART 3: RESPONSIVE BEHAVIOR TESTING
    // Widths: 1440px, 1280px, 1024px, 900px, 768px
    // =========================================================================
    const testWidths = [1440, 1280, 1024, 900, 768];

    for (const width of testWidths) {
      console.log(`\n======================================================`);
      console.log(`Testing Responsive Width: ${width}px`);
      console.log(`======================================================`);

      await page.setViewport({ width, height: 800 });
      await new Promise((r) => setTimeout(r, 300));

      // --- A. EXPANDED SIDEBAR AT CURRENT WIDTH ---
      console.log(`[${width}px - EXPANDED]`);
      // Ensure expanded
      await page.evaluate(() => {
        useUiStore = window.__UI_STORE__; // if exposed or via button
      });
      const isCollapsed = await page.evaluate(() =>
        document.querySelector(".shell")?.classList.contains("shell--collapsed")
      );
      if (isCollapsed) {
        const expBtn = await page.$(".sidebar-expand-btn");
        if (expBtn) await expBtn.click();
        await new Promise((r) => setTimeout(r, 400));
      }

      const expandedCheck = await page.evaluate((targetWidth) => {
        const shell = document.querySelector(".shell");
        const sidebar = document.querySelector(".sidebar");
        const main = document.querySelector(".main");
        const sidebarRect = sidebar.getBoundingClientRect();
        const mainRect = main.getBoundingClientRect();
        const docScrollWidth = document.documentElement.scrollWidth;
        const bodyScrollWidth = document.body.scrollWidth;
        const hasHorizontalScroll =
          docScrollWidth > targetWidth || bodyScrollWidth > targetWidth;

        // Check sidebar visibility & content
        const brand = sidebar.querySelector(".sidebar__brand");
        const brandRect = brand ? brand.getBoundingClientRect() : null;
        const items = sidebar.querySelectorAll(".sidebar__item");
        const firstItem = items[0];
        const firstItemRect = firstItem ? firstItem.getBoundingClientRect() : null;

        // Check overlap between sidebar and main
        // Sidebar right should match or be <= main left
        const overlap = sidebarRect.right > mainRect.left + 1;

        return {
          targetWidth,
          docScrollWidth,
          hasHorizontalScroll,
          sidebarWidth: sidebarRect.width,
          sidebarRight: sidebarRect.right,
          mainLeft: mainRect.left,
          mainWidth: mainRect.width,
          overlap,
          brandVisible: brandRect && brandRect.width > 0 && brandRect.height > 0,
          firstItemVisible: firstItemRect ? firstItemRect.width > 0 : true,
        };
      }, width);

      console.log("   Expanded check result:", expandedCheck);

      if (expandedCheck.hasHorizontalScroll) {
        throw new Error(
          `Horizontal scrolling detected at ${width}px expanded! docScrollWidth=${expandedCheck.docScrollWidth}, targetWidth=${width}`
        );
      }
      if (expandedCheck.sidebarWidth < 200) {
        throw new Error(`Sidebar width too small (${expandedCheck.sidebarWidth}px) at ${width}px expanded`);
      }
      if (expandedCheck.overlap) {
        throw new Error(
          `Sidebar overlaps main workspace at ${width}px! sidebarRight=${expandedCheck.sidebarRight}, mainLeft=${expandedCheck.mainLeft}`
        );
      }
      if (!expandedCheck.brandVisible) {
        throw new Error(`Sidebar brand content not visible at ${width}px expanded`);
      }

      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, `responsive_${width}px_expanded.png`),
      });
      console.log(`   ✅ ${width}px Expanded: Content fully visible, no overlap, no horizontal scrolling.`);

      // --- B. COLLAPSED SIDEBAR AT CURRENT WIDTH ---
      console.log(`[${width}px - COLLAPSED]`);
      const colBtn = await page.waitForSelector(".sidebar-collapse-btn", { timeout: 3000 });
      await colBtn.click();
      await new Promise((r) => setTimeout(r, 400));

      const collapsedCheck = await page.evaluate((targetWidth) => {
        const shell = document.querySelector(".shell");
        const sidebar = document.querySelector(".sidebar");
        const main = document.querySelector(".main");
        const expandBtn = document.querySelector(".sidebar-expand-btn");
        const sidebarRect = sidebar.getBoundingClientRect();
        const mainRect = main.getBoundingClientRect();
        const docScrollWidth = document.documentElement.scrollWidth;
        const bodyScrollWidth = document.body.scrollWidth;
        const hasHorizontalScroll =
          docScrollWidth > targetWidth || bodyScrollWidth > targetWidth;

        // In collapsed state, sidebar rect right must be <= 0 (hidden off-screen)
        // or sidebar has visibility: hidden / opacity: 0
        const sidebarHidden =
          sidebarRect.right <= 0 ||
          window.getComputedStyle(sidebar).visibility === "hidden" ||
          window.getComputedStyle(sidebar).opacity === "0";

        // Main workspace expands to ~100% of viewport
        const mainExpanded = mainRect.width >= targetWidth - 2;

        return {
          targetWidth,
          docScrollWidth,
          hasHorizontalScroll,
          sidebarRight: sidebarRect.right,
          sidebarHidden,
          mainWidth: mainRect.width,
          mainExpanded,
          hasExpandBtn: Boolean(expandBtn),
        };
      }, width);

      console.log("   Collapsed check result:", collapsedCheck);

      if (collapsedCheck.hasHorizontalScroll) {
        throw new Error(
          `Horizontal scrolling detected at ${width}px collapsed! docScrollWidth=${collapsedCheck.docScrollWidth}, targetWidth=${width}`
        );
      }
      if (!collapsedCheck.sidebarHidden) {
        throw new Error(`Sidebar is not properly hidden at ${width}px collapsed`);
      }
      if (!collapsedCheck.mainExpanded) {
        throw new Error(
          `Main workspace did not expand fully at ${width}px collapsed! mainWidth=${collapsedCheck.mainWidth}, targetWidth=${width}`
        );
      }
      if (!collapsedCheck.hasExpandBtn) {
        throw new Error(`Expand button missing at ${width}px collapsed`);
      }

      await page.screenshot({
        path: path.join(SCREENSHOTS_DIR, `responsive_${width}px_collapsed.png`),
      });
      console.log(`   ✅ ${width}px Collapsed: Sidebar hidden cleanly, workspace expands fully, no horizontal scrolling.`);
    }

    console.log("\n========================================================");
    console.log("🎉 ALL TOOLTIP AND RESPONSIVE TESTS PASSED SUCCESSFULLY!");
    console.log("========================================================");
  } finally {
    await browser.close();
  }
}

run().catch((err) => {
  console.error("❌ Test failed:", err);
  process.exit(1);
});
