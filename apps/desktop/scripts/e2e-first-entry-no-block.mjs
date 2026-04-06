import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import net from "node:net";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const cwd = resolve(process.cwd());
const repoRoot = resolve(cwd, "..", "..");
const outputDir = resolve(repoRoot, ".runtime-cache", "test_output", "desktop_trust");
mkdirSync(outputDir, { recursive: true });

const screenshotPath = resolve(outputDir, "first_entry_no_block.png");
const reportPath = resolve(outputDir, "first_entry_no_block.json");

function isPortAvailable(port) {
  return new Promise((resolveCheck) => {
    const server = net.createServer();
    server.once("error", () => resolveCheck(false));
    server.once("listening", () => {
      server.close(() => resolveCheck(true));
    });
    server.listen(port, "127.0.0.1");
  });
}

async function findAvailablePort(startPort = 4173, maxProbe = 30) {
  for (let port = startPort; port < startPort + maxProbe; port += 1) {
    if (await isPortAvailable(port)) return port;
  }
  throw new Error(`no available port found in range ${startPort}-${startPort + maxProbe - 1}`);
}

function waitForServer(baseUrl, timeoutMs = 30000) {
  const start = Date.now();
  return new Promise((resolveWait, rejectWait) => {
    const probe = async () => {
      try {
        const res = await fetch(baseUrl);
        if (res.ok) {
          resolveWait(true);
          return;
        }
      } catch {
        // retry until timeout
      }
      if (Date.now() - start > timeoutMs) {
        rejectWait(new Error(`server not ready: ${baseUrl}`));
        return;
      }
      setTimeout(probe, 500);
    };
    void probe();
  });
}

async function run() {
  const port = await findAvailablePort(4173, 30);
  const url = `http://127.0.0.1:${port}`;
  const devServer = spawn(
    "npm",
    ["run", "dev", "--", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd, stdio: "inherit" },
  );

  const report = {
    scenario: "desktop first entry should not be blocked by stale pending decision",
    started_at: new Date().toISOString(),
    base_url: url,
    server_mode: "vite-dev",
    checks: [],
    screenshot_path: screenshotPath,
    status: "failed",
    error: "",
  };

  let browser = null;
  try {
    await waitForServer(url);
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

    await page.route("**/api/command-tower/overview", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ total_sessions: 1, active_sessions: 1, failed_ratio: 0, blocked_sessions: 0 }),
      });
    });
    await page.route("**/api/pm/sessions?*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ pm_session_id: "pm-live-1", status: "running", current_step: "reviewer" }]),
      });
    });
    await page.route("**/api/command-tower/alerts", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ alerts: [] }),
      });
    });
    await page.route("**/api/pm/sessions/*/messages", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ pm_session_id: "pm-live-1", message: "TL 已拆解并派发执行。" }),
      });
    });

    await page.goto(url, { waitUntil: "networkidle" });
    await page.locator("aside .sidebar-link", { hasText: "PM 入口" }).first().click();
    await page.getByLabel("继续对话").waitFor({ state: "visible" });

    const placeholder = await page.getByLabel("继续对话").getAttribute("placeholder");
    const blockedHintVisible = await page.getByText("先完成上面的决策卡片，或继续补充你的约束...").isVisible().catch(() => false);
    const selectedDecisionVisible = await page.getByRole("button", { name: "已选择" }).isVisible().catch(() => false);

    report.checks.push({
      name: "composer placeholder should be non-blocking",
      expected: "审核后告诉 PM：接受并合并，或继续修改。",
      actual: placeholder,
      pass: placeholder === "审核后告诉 PM：接受并合并，或继续修改。",
    });
    report.checks.push({
      name: "blocking hint should not be visible",
      expected: false,
      actual: blockedHintVisible,
      pass: blockedHintVisible === false,
    });
    report.checks.push({
      name: "bootstrap decision should be preselected",
      expected: true,
      actual: selectedDecisionVisible,
      pass: selectedDecisionVisible === true,
    });

    await page.screenshot({ path: screenshotPath, fullPage: true });
    report.status = report.checks.every((c) => c.pass) ? "passed" : "failed";
    if (report.status !== "passed") {
      throw new Error("one or more checks failed");
    }
  } catch (error) {
    report.error = error instanceof Error ? error.message : String(error);
    throw error;
  } finally {
    report.finished_at = new Date().toISOString();
    writeFileSync(reportPath, JSON.stringify(report, null, 2));
    if (browser) await browser.close();
    devServer.kill("SIGTERM");
  }
}

run().catch((error) => {
  console.error("desktop e2e first-entry check failed:", error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
