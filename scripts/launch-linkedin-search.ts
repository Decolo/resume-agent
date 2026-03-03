/**
 * Launch Chrome with debug profile, navigate to LinkedIn job search URL.
 *
 * Usage:
 *   npx tsx scripts/launch-linkedin-search.ts <keywords> [location]
 *
 * Outputs JSON to stdout on success:
 *   { "port": 12345, "wsUrl": "ws://..." }
 *
 * Python CDPClient connects to the returned port/wsUrl.
 */
import { execSync, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { CdpConnection, findChrome, getFreePort, sleep, waitForDebugPort } from "./cdp.js";

const REAL_CHROME_DIR = path.join(os.homedir(), "Library", "Application Support", "Google", "Chrome");
const DEBUG_DIR = path.join(os.homedir(), ".chrome-debug-profile");

function ensureDebugProfile(): void {
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
    if (fs.existsSync(src)) fs.copyFileSync(src, dst);
  }

  const localState = path.join(REAL_CHROME_DIR, "Local State");
  if (fs.existsSync(localState)) {
    fs.copyFileSync(localState, path.join(DEBUG_DIR, "Local State"));
  }
  console.error("[launch] Synced cookies to debug profile");
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
  console.error("[launch] Chrome is running, quitting gracefully...");
  execSync(`osascript -e 'tell application "Google Chrome" to quit'`);
  const start = Date.now();
  while (Date.now() - start < 10_000) {
    if (!isChromeRunning()) break;
    await sleep(500);
  }
  if (isChromeRunning()) throw new Error("Chrome did not quit in time");
  console.error("[launch] Chrome quit, waiting for profile lock release...");
  await sleep(2000);
}

function buildSearchUrl(keywords: string, location: string): string {
  const params = new URLSearchParams({ keywords });
  if (location) params.set("location", location);
  return `https://www.linkedin.com/jobs/search/?${params.toString()}`;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.error("Usage: npx tsx scripts/launch-linkedin-search.ts <keywords> [location]");
    process.exit(1);
  }
  const keywords = args[0];
  const location = args[1] || "";
  const searchUrl = buildSearchUrl(keywords, location);

  const chromePath = findChrome();
  if (!chromePath) throw new Error("Chrome not found. Set CHROME_PATH env var.");

  if (isChromeRunning()) await quitChrome();
  ensureDebugProfile();

  const port = await getFreePort();
  console.error(`[launch] Launching Chrome on debug port ${port}`);
  console.error(`[launch] Search URL: ${searchUrl}`);

  const chrome = spawn(chromePath, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${DEBUG_DIR}`,
    "--profile-directory=Default",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
    searchUrl,
  ], { stdio: ["ignore", "ignore", "pipe"], detached: true });

  chrome.stderr?.on("data", (chunk: Buffer) => {
    const msg = chunk.toString().trim();
    if (msg) console.error(`[chrome stderr] ${msg}`);
  });
  chrome.on("error", (err) => console.error(`[chrome] spawn error: ${err.message}`));
  chrome.on("exit", (code) => { if (code) console.error(`[chrome] exited with code ${code}`); });
  chrome.unref();

  const wsUrl = await waitForDebugPort(port);
  const cdp = await CdpConnection.connect(wsUrl);

  try {
    // Find the LinkedIn tab
    const targets = await cdp.send<{
      targetInfos: Array<{ targetId: string; url: string; type: string }>;
    }>("Target.getTargets");
    const page = targets.targetInfos.find(
      (t) => t.type === "page" && t.url.includes("linkedin.com")
    );
    if (!page) throw new Error("LinkedIn tab not found");

    const { sessionId } = await cdp.send<{ sessionId: string }>(
      "Target.attachToTarget", { targetId: page.targetId, flatten: true }
    );
    await cdp.send("Page.enable", {}, { sessionId });
    await cdp.send("Runtime.enable", {}, { sessionId });

    // Wait for page to be ready (handles login redirects)
    console.error("[launch] Waiting for search page to load...");
    const maxWait = 60_000;
    const waitStart = Date.now();
    while (Date.now() - waitStart < maxWait) {
      await sleep(2000);
      try {
        const r = await cdp.send<{ result: { value: { url: string; ready: boolean } } }>(
          "Runtime.evaluate",
          { expression: `({ url: location.href, ready: document.readyState === "complete" })`, returnByValue: true },
          { sessionId },
        );
        const { url, ready } = r.result.value;
        console.error(`[launch] Current: ${url} (ready: ${ready})`);
        if (ready && (url.includes("/jobs/search") || url.includes("/jobs/collection"))) break;
      } catch {
        console.error("[launch] Page navigating...");
      }
    }
    await sleep(3000);
    console.error("[launch] Search page ready.");
  } finally {
    cdp.close();
  }

  // Output JSON to stdout for Python to parse
  console.log(JSON.stringify({ port, wsUrl }));
}

main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : err}`);
  process.exit(1);
});
