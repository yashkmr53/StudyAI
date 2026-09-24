import puppeteer from "puppeteer-core";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, "screenshots", "polish");
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP_URL = "http://localhost:5173";

async function run() {
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--window-size=1280,800"],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  console.log("Navigating to login...");
  await page.goto(`${APP_URL}/login`, { waitUntil: "networkidle2" });
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

  await page.waitForFunction(() => window.location.pathname.startsWith("/subjects"), { timeout: 15000 });
  await page.waitForSelector(".sidebar", { timeout: 10000 });

  // Check profile switcher to YashAI if needed
  let profileName = await page.$eval(".profile-button__name", el => el.textContent.trim());
  console.log("Initial profile:", profileName);

  if (profileName !== "Yash") {
    console.log("Switching to Yash...");
    await page.click(".profile-button");
    await page.waitForSelector(".popover", { timeout: 5000 });
    const clicked = await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".popover .popover__item, .popover [role=menuitem], .popover button"));
      const match = items.find(el => el.textContent.includes("Yash") && !el.textContent.includes("YashAI"));
      if (match) {
        match.click();
        return true;
      }
      return false;
    });
    console.log("Clicked Yash?", clicked);
    await new Promise(r => setTimeout(r, 1500));
  }

  profileName = await page.$eval(".profile-button__name", el => el.textContent.trim());
  console.log("Active profile now:", profileName);

  // Take screenshot of subject page
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_subject_initial.png") });

  // Check 3-dots ActionMenu next to h1 in Subject page
  const subjectActionMenuBtn = await page.$(".page-heading h1 + .action-menu button, .page-heading .action-menu button");
  if (subjectActionMenuBtn) {
    console.log("Found subject ActionMenu button. Clicking it...");
    await subjectActionMenuBtn.click();
    await new Promise(r => setTimeout(r, 300));
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_subject_menu_opened.png") });

    // Measure bounding boxes
    const bounds = await page.evaluate(() => {
      const sidebar = document.querySelector(".sidebar");
      const menu = document.querySelector(".action-menu__dropdown");
      const btn = document.querySelector(".page-heading .action-menu button");
      return {
        sidebarRight: sidebar ? sidebar.getBoundingClientRect().right : null,
        menuLeft: menu ? menu.getBoundingClientRect().left : null,
        menuRight: menu ? menu.getBoundingClientRect().right : null,
        btnLeft: btn ? btn.getBoundingClientRect().left : null,
        btnRight: btn ? btn.getBoundingClientRect().right : null,
      };
    });
    console.log("Subject Menu bounds:", bounds);
    if (bounds.menuLeft !== null && bounds.sidebarRight !== null) {
      if (bounds.menuLeft < bounds.sidebarRight) {
        console.log(`❌ OVERLAP DETECTED! Menu left (${bounds.menuLeft}px) is less than sidebar right (${bounds.sidebarRight}px)! Overlap: ${bounds.sidebarRight - bounds.menuLeft}px`);
      } else {
        console.log(`✅ No overlap: Menu left (${bounds.menuLeft}px) >= sidebar right (${bounds.sidebarRight}px)`);
      }
    }
  }

  // Dismiss subject menu by clicking outside
  await page.click("body", { offset: { x: 500, y: 100 } });
  await new Promise(r => setTimeout(r, 300));

  // Create a real folder to test FolderDetailPage ActionMenu
  console.log("Creating a test folder 'Week 1 - Trees'...");
  const newFolderBtn = await page.evaluateHandle(() => {
    return Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("New folder"));
  });
  if (newFolderBtn && newFolderBtn.asElement()) {
    await newFolderBtn.asElement().click();
  }
  const testFolderName = `Week 1 - Trees - ${Date.now()}`;
  await page.waitForSelector(".dialog input.input", { timeout: 5000 });
  await page.type(".dialog input.input", testFolderName);
  await page.click(".dialog .btn--primary");
  await new Promise(r => setTimeout(r, 1000));

  // Click into the newly created folder
  console.log(`Navigating into '${testFolderName}' folder...`);
  const folderCard = await page.evaluateHandle((name) => {
    const cards = Array.from(document.querySelectorAll(".folder-card"));
    return cards.find(c => c.textContent.includes(name));
  }, testFolderName);
  if (folderCard && folderCard.asElement()) {
    await folderCard.asElement().click();
    await page.waitForFunction(() => window.location.pathname.includes("/folders/"), { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_folder_detail_page.png") });

    // Test folder ActionMenu (next to h1)
    const folderActionMenuBtn = await page.waitForSelector(".page-heading .action-menu button", { timeout: 5000 });
    if (folderActionMenuBtn) {
      console.log("Testing folder ActionMenu positioning...");
      await folderActionMenuBtn.click();
      await new Promise(r => setTimeout(r, 300));
      const folderBounds = await page.evaluate(() => {
        const sidebar = document.querySelector(".sidebar");
        const menu = document.querySelector(".action-menu__dropdown");
        const btn = document.querySelector(".page-heading .action-menu button");
        return {
          sidebarRight: sidebar ? sidebar.getBoundingClientRect().right : null,
          menuLeft: menu ? menu.getBoundingClientRect().left : null,
          menuRight: menu ? menu.getBoundingClientRect().right : null,
          btnLeft: btn ? btn.getBoundingClientRect().left : null,
        };
      });
      console.log("Folder Menu bounds:", folderBounds);
      if (folderBounds.menuLeft !== null && folderBounds.sidebarRight !== null) {
        if (folderBounds.menuLeft < folderBounds.sidebarRight) {
          throw new Error(`Folder menu overlaps sidebar! menuLeft: ${folderBounds.menuLeft}, sidebarRight: ${folderBounds.sidebarRight}`);
        } else {
          console.log(`✅ Folder menu No overlap: menuLeft (${folderBounds.menuLeft}px) >= sidebarRight (${folderBounds.sidebarRight}px)`);
        }
      }
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_folder_menu_opened.png") });
      await page.click("body", { offset: { x: 500, y: 100 } });
      await new Promise(r => setTimeout(r, 300));
    }
  }

  // Navigate back to subject Unfiled notes
  console.log("Navigating to Unfiled folder to open note...");
  await page.goto(`${APP_URL}/subjects/befb6eeb-da4e-4c23-96f4-54c96650296e/folders/__unfiled__`, { waitUntil: "networkidle2" });
  await page.waitForSelector(".note-row", { timeout: 5000 });
  await page.click(".note-row");
  await page.waitForFunction(() => window.location.pathname.includes("/notes/"), { timeout: 10000 });
  await page.waitForSelector(".source-page", { timeout: 10000 });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_note_detail_page.png") });

  // Inspect viewer controls in .source-page__header
  const controls = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll(".source-page__header button[data-tip]"));
    const sourcePage = document.querySelector(".source-page");
    return {
      sourcePageOverflow: window.getComputedStyle(sourcePage).overflow,
      buttons: btns.map((b, idx) => ({
        index: idx,
        text: b.textContent.trim(),
        ariaLabel: b.getAttribute("aria-label"),
        dataTip: b.getAttribute("data-tip"),
        disabled: b.disabled,
      }))
    };
  });
  console.log("Viewer controls found in .source-page__header:", controls);

  // Test tooltips on controls
  for (let i = 0; i < controls.buttons.length; i++) {
    const sel = `.source-page__header button[data-tip]:nth-of-type(${i + 1})`;
    const btn = await page.$(sel);
    if (btn) {
      await btn.hover();
      await new Promise(r => setTimeout(r, 200));
      const tipData = await page.evaluate((selector) => {
        const el = document.querySelector(selector);
        if (!el) return null;
        const after = window.getComputedStyle(el, "::after");
        return {
          content: after.content,
          display: after.display,
          top: after.top,
          zIndex: after.zIndex,
        };
      }, sel);
      console.log(`Control [${controls.buttons[i].dataTip}] hover tooltip:`, tipData);
      if (!tipData || tipData.content === "none" || !tipData.content) {
        throw new Error(`Tooltip missing on control: ${controls.buttons[i].dataTip}`);
      }
    }
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_note_zoom_in_hover.png") });

  // Test Note Detail page ActionMenu (top right)
  const noteActionMenuBtn = await page.$('.page-heading .action-menu button[aria-label="Note actions"]');
  if (noteActionMenuBtn) {
    console.log("Testing Note Detail page ActionMenu (top right)...");
    await noteActionMenuBtn.click();
    await new Promise(r => setTimeout(r, 300));
    const noteMenuBounds = await page.evaluate(() => {
      const menu = document.querySelector(".action-menu__dropdown");
      const btn = document.querySelector('.page-heading .action-menu button[aria-label="Note actions"]');
      return {
        windowWidth: window.innerWidth,
        menuLeft: menu ? menu.getBoundingClientRect().left : null,
        menuRight: menu ? menu.getBoundingClientRect().right : null,
        btnRight: btn ? btn.getBoundingClientRect().right : null,
      };
    });
    console.log("Note ActionMenu bounds:", noteMenuBounds);
    if (noteMenuBounds.menuRight !== null && noteMenuBounds.windowWidth !== null) {
      if (noteMenuBounds.menuRight > noteMenuBounds.windowWidth) {
        throw new Error(`Note menu overflows right: ${noteMenuBounds.menuRight} > ${noteMenuBounds.windowWidth}`);
      } else {
        console.log(`✅ Note menu contained within viewport: menuRight (${noteMenuBounds.menuRight}px) <= windowWidth (${noteMenuBounds.windowWidth}px)`);
      }
    }
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "08_note_menu_opened.png") });
    await page.click("body", { offset: { x: 500, y: 100 } });
    await new Promise(r => setTimeout(r, 300));
  }

  // --- MOBILE VIEWPORT TEST (375x667) ---
  console.log("Testing narrow mobile layout (375x667)...");
  await page.setViewport({ width: 375, height: 667 });
  await page.goto(`${APP_URL}/subjects/befb6eeb-da4e-4c23-96f4-54c96650296e`, { waitUntil: "networkidle2" });
  await new Promise(r => setTimeout(r, 1000));
  const mobileMenuBtn = await page.$(".page-heading .action-menu button");
  if (mobileMenuBtn) {
    await mobileMenuBtn.click();
    await new Promise(r => setTimeout(r, 300));
    const mobileBounds = await page.evaluate(() => {
      const menu = document.querySelector(".action-menu__dropdown");
      return {
        windowWidth: window.innerWidth,
        menuLeft: menu ? menu.getBoundingClientRect().left : null,
        menuRight: menu ? menu.getBoundingClientRect().right : null,
      };
    });
    console.log("Mobile ActionMenu bounds:", mobileBounds);
    if (mobileBounds.menuRight && mobileBounds.menuRight > mobileBounds.windowWidth + 5) {
      throw new Error(`Mobile ActionMenu overflows viewport: ${mobileBounds.menuRight} > ${mobileBounds.windowWidth}`);
    }
    console.log("✅ Mobile ActionMenu fits cleanly inside viewport!");
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "09_mobile_action_menu.png") });
  }

  await browser.close();
}

run().catch(err => {
  console.error("Test run error:", err);
  process.exit(1);
});
