import { execSync, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { CdpConnection, findChrome, getFreePort, sleep, waitForDebugPort } from "./cdp.js";

const LINKEDIN_FEED = "https://www.linkedin.com/feed/";
const REAL_CHROME_DIR = path.join(os.homedir(), "Library", "Application Support", "Google", "Chrome");
const DEBUG_DIR = path.join(os.homedir(), ".chrome-debug-profile");

function ensureDebugProfile(): void {
  // Chrome won't share a profile dir with another instance (even via symlink).
  // So we create an independent profile and copy cookie/login files from the real one.
  const debugDefault = path.join(DEBUG_DIR, "Default");

  if (!fs.existsSync(debugDefault)) {
    fs.mkdirSync(debugDefault, { recursive: true });
  }

  const filesToCopy = [
    "Cookies", "Cookies-journal",
    "Login Data", "Login Data-journal",
    "Login Data For Account", "Login Data For Account-journal",
  ];

  const realDefault = path.join(REAL_CHROME_DIR, "Default");
  for (const name of filesToCopy) {
    const src = path.join(realDefault, name);
    const dst = path.join(debugDefault, name);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, dst);
    }
  }

  // Copy Local State (profile registry) to user-data-dir level
  const localState = path.join(REAL_CHROME_DIR, "Local State");
  if (fs.existsSync(localState)) {
    fs.copyFileSync(localState, path.join(DEBUG_DIR, "Local State"));
  }

  console.log("[linkedin] Synced cookies to debug profile");
}

function isChromeRunning(): boolean {
  try {
    execSync("pgrep -x 'Google Chrome'", { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

async function quitChrome(): Promise<void> {
  console.log("[linkedin] Chrome is running, quitting gracefully...");
  execSync(`osascript -e 'tell application "Google Chrome" to quit'`);
  const start = Date.now();
  while (Date.now() - start < 10_000) {
    if (!isChromeRunning()) break;
    await sleep(500);
  }
  if (isChromeRunning()) throw new Error("Chrome did not quit in time");
  console.log("[linkedin] Chrome quit, waiting for profile lock release...");
  await sleep(2000);
}

async function main() {
  const chromePath = findChrome();
  if (!chromePath) throw new Error("Chrome not found. Set CHROME_PATH env var.");

  if (isChromeRunning()) await quitChrome();

  ensureDebugProfile();

  const port = await getFreePort();
  console.log(`[linkedin] Launching Chrome on debug port ${port}`);

  const chrome = spawn(chromePath, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${DEBUG_DIR}`,
    "--profile-directory=Default",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
    LINKEDIN_FEED,
  ], { stdio: ["ignore", "ignore", "pipe"], detached: true });

  chrome.stderr?.on("data", (chunk: Buffer) => {
    const msg = chunk.toString().trim();
    if (msg) console.log(`[chrome stderr] ${msg}`);
  });

  chrome.on("error", (err) => console.error(`[chrome] spawn error: ${err.message}`));
  chrome.on("exit", (code) => { if (code) console.error(`[chrome] exited with code ${code}`); });
  chrome.unref();

  let cdp: CdpConnection | null = null;
  try {
    const wsUrl = await waitForDebugPort(port);
    cdp = await CdpConnection.connect(wsUrl);

    // Find LinkedIn tab
    const targets = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>("Target.getTargets");
    const page = targets.targetInfos.find((t) => t.type === "page" && t.url.includes("linkedin.com"));
    if (!page) throw new Error("LinkedIn tab not found");

    const { sessionId } = await cdp.send<{ sessionId: string }>("Target.attachToTarget", { targetId: page.targetId, flatten: true });
    await cdp.send("Page.enable", {}, { sessionId });
    await cdp.send("Runtime.enable", {}, { sessionId });

    // Wait until we're actually on the feed page (not login/redirect)
    console.log("[linkedin] Waiting for feed page...");
    const maxWait = 60_000;
    const waitStart = Date.now();
    while (Date.now() - waitStart < maxWait) {
      await sleep(2000);
      try {
        const r = await cdp.send<{ result: { value: { url: string; ready: boolean } } }>("Runtime.evaluate", {
          expression: `({ url: location.href, ready: document.readyState === "complete" })`,
          returnByValue: true,
        }, { sessionId });
        const { url, ready } = r.result.value;
        console.log(`[linkedin] Current: ${url} (ready: ${ready})`);
        if (url.includes("/feed") && ready) break;
      } catch {
        console.log("[linkedin] Page navigating...");
      }
    }
    // Let feed content render
    await sleep(3000);

    // Scroll from Node side — each scroll is a separate evaluate, resilient to context loss
    console.log("[linkedin] Scrolling feed...");
    let sameCount = 0;
    let lastHeight = 0;
    let scrolled = 0;
    const scrollStart = Date.now();

    while (Date.now() - scrollStart < 120_000) {
      try {
        const r = await cdp.send<{ result: { value: { h: number } } }>("Runtime.evaluate", {
          expression: `(() => { window.scrollBy(0, 800); return { h: document.documentElement.scrollHeight }; })()`,
          returnByValue: true,
        }, { sessionId });
        scrolled++;
        const h = r.result.value.h;
        if (h === lastHeight) sameCount++;
        else { sameCount = 0; lastHeight = h; }
        if (scrolled % 20 === 0) console.log(`[linkedin] Scrolled ${scrolled} times, height: ${h}`);
        if (scrolled >= 10 && sameCount >= 5) break;
      } catch {
        console.log("[linkedin] Context lost during scroll, retrying...");
        sameCount = 0;
        await sleep(3000);
      }
      await sleep(500);
    }

    console.log(`[linkedin] Scroll finished (scrolled ${scrolled} times)`);
  } finally {
    if (cdp) cdp.close();
  }
  console.log("[linkedin] Done. Chrome stays open.");
}

main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : err}`);
  process.exit(1);
});
