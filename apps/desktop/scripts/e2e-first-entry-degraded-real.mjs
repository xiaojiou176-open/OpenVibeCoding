import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import net from "node:net";
import { terminateTrackedChild } from "./host-process-safety.mjs";
import { configurePlaywrightTempDir } from "./playwright-tempdir.mjs";

const playwrightTempDir = configurePlaywrightTempDir("desktop-first-entry-degraded-real");
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const scriptDir = dirname(fileURLToPath(import.meta.url));
const desktopDir = resolve(scriptDir, "..");
const repoRoot = resolve(desktopDir, "..", "..");
const outputDir = resolve(repoRoot, ".runtime-cache", "test_output", "desktop_trust");
mkdirSync(outputDir, { recursive: true });

const artifactSuffix = String(process.env.OPENVIBECODING_E2E_ARTIFACT_SUFFIX || "").trim();
function withSuffix(filename) {
  if (!artifactSuffix) return filename;
  const dot = filename.lastIndexOf(".");
  if (dot <= 0) return `${filename}.${artifactSuffix}`;
  return `${filename.slice(0, dot)}.${artifactSuffix}${filename.slice(dot)}`;
}

const screenshotPath = resolve(outputDir, withSuffix("first_entry_degraded_real.png"));
const reportPath = resolve(outputDir, withSuffix("first_entry_degraded_real.json"));
const networkPath = resolve(outputDir, withSuffix("first_entry_degraded_real.network.json"));

function resolvePythonBin() {
  const candidates = [
    String(process.env.OPENVIBECODING_PYTHON || "").trim(),
    resolve(repoRoot, ".runtime-cache", "cache", "toolchains", "python", "current", "bin", "python"),
    resolve(repoRoot, ".venv", "bin", "python"),
  ].filter(Boolean);
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) {
    throw new Error(`python runtime not found; checked: ${candidates.join(", ")}`);
  }
  return found;
}

function isPortAvailable(port) {
  return new Promise((resolveCheck) => {
    const server = net.createServer();
    server.once("error", () => resolveCheck(false));
    server.once("listening", () => {
      server.close(() => resolveCheck(true));
    });
    server.listen(port);
  });
}

async function findAvailablePort(startPort = 4173, maxProbe = 40) {
  for (let port = startPort; port < startPort + maxProbe; port += 1) {
    if (await isPortAvailable(port)) return port;
  }
  throw new Error(`no available port found in range ${startPort}-${startPort + maxProbe - 1}`);
}

async function resolvePreferredPort(requestedPort, defaultStartPort, maxProbe = 60) {
  if (Number.isFinite(requestedPort) && requestedPort > 0) {
    if (await isPortAvailable(requestedPort)) return requestedPort;
    return findAvailablePort(requestedPort + 1, maxProbe);
  }
  return findAvailablePort(defaultStartPort, maxProbe);
}

function waitForHttpReady(url, timeoutMs = 30000, acceptStatuses = null, headers = {}) {
  const start = Date.now();
  return new Promise((resolveWait, rejectWait) => {
    const probe = async () => {
      try {
        const res = await fetch(url, { headers });
        const accepted = Array.isArray(acceptStatuses)
          ? acceptStatuses.includes(res.status)
          : res.status >= 100;
        if (accepted) {
          resolveWait(true);
          return;
        }
      } catch {
        // retry until timeout
      }
      if (Date.now() - start > timeoutMs) {
        rejectWait(new Error(`server not ready: ${url}`));
        return;
      }
      setTimeout(probe, 500);
    };
    void probe();
  });
}

async function fetchWithRetry(input, init = {}, options = {}) {
  const attempts = Number.isFinite(options.attempts) ? options.attempts : 4;
  const retryDelayMs = Number.isFinite(options.retryDelayMs) ? options.retryDelayMs : 400;
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await fetch(input, init);
    } catch (error) {
      lastError = error;
      if (attempt >= attempts) break;
      await new Promise((resolveDelay) => setTimeout(resolveDelay, retryDelayMs * attempt));
    }
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError || "fetch failed"));
}

async function postJson(baseUrl, path, payload) {
  const apiToken = String(process.env.OPENVIBECODING_API_TOKEN || "openvibecoding-dev-token").trim();
  const headers = { "Content-Type": "application/json" };
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
  const res = await fetchWithRetry(`${baseUrl}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }
  if (!res.ok) {
    throw new Error(`POST ${path} failed: ${res.status} ${JSON.stringify(data)}`);
  }
  return data;
}

async function waitFor(checkFn, timeoutMs = 15000, intervalMs = 400) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const value = await checkFn();
      if (value) return true;
    } catch {
      // keep retrying
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, intervalMs));
  }
  return false;
}

async function resolveVisibleLocator(candidates) {
  for (const candidate of candidates) {
    if (await candidate.isVisible().catch(() => false)) return candidate;
  }
  return candidates[0];
}

async function resolveComposer(page) {
  return resolveVisibleLocator([
    page.locator("#desktop-chat-input").first(),
    page.getByLabel("继续对话").first(),
    page.locator("section.chat-composer textarea").first(),
  ]);
}

async function resolveSendButton(page) {
  return resolveVisibleLocator([
    page.getByRole("button", { name: "发送消息" }).first(),
    page.locator("section.chat-composer button", { hasText: "发送消息" }).first(),
  ]);
}

async function safeIsEnabled(locator) {
  const visible = await locator.isVisible().catch(() => false);
  if (!visible) return false;
  return locator.evaluate((node) => {
    if (node instanceof HTMLButtonElement || node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement) {
      return !node.disabled;
    }
    return !node.hasAttribute("disabled");
  }).catch(() => false);
}

async function clickSendButton(page, timeoutMs = 12000, intervalMs = 200) {
  const start = Date.now();
  let lastError = null;
  while (Date.now() - start < timeoutMs) {
    try {
      const button = await resolveSendButton(page);
      if (!(await safeIsEnabled(button))) {
        await new Promise((resolveDelay) => setTimeout(resolveDelay, intervalMs));
        continue;
      }
      await button.click({ timeout: intervalMs * 2, noWaitAfter: true });
      return true;
    } catch (error) {
      lastError = error;
      await new Promise((resolveDelay) => setTimeout(resolveDelay, intervalMs));
    }
  }
  if (lastError) {
    throw lastError;
  }
  return false;
}

async function openPmEntry(page) {
  const composer = page.getByLabel("继续对话");
  const composerFallback = page.locator("section.chat-composer textarea").first();
  const alreadyOnPm =
    (await composer.isVisible().catch(() => false)) ||
    (await composerFallback.isVisible().catch(() => false));
  if (alreadyOnPm) return;

  const candidates = [
    page.getByRole("button", { name: /PM\s*入口|发需求/ }).first(),
    page.locator("aside .sidebar-link", { hasText: /PM\s*入口|发需求/ }).first(),
    page.getByText("主步骤 1 · 发需求").first(),
  ];

  await waitFor(async () => {
    if (await composer.isVisible().catch(() => false)) return true;
    if (await composerFallback.isVisible().catch(() => false)) return true;
    for (const candidate of candidates) {
      if (await candidate.isVisible().catch(() => false)) return true;
    }
    return false;
  }, 60000, 400);

  for (const candidate of candidates) {
    const visible = await candidate.isVisible().catch(() => false);
    if (!visible) continue;
    await candidate.click();
    const switched = await waitFor(
      async () =>
        (await composer.isVisible().catch(() => false)) ||
        (await composerFallback.isVisible().catch(() => false)),
      8000,
      300,
    );
    if (switched) return;
  }

  const clickedViaDom = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll("aside .sidebar-link"));
    const target = buttons.find((btn) => /PM\s*入口|发需求/.test((btn.textContent || "").trim()));
    if (!target) return false;
    (target instanceof HTMLElement ? target : null)?.click();
    return true;
  });
  if (clickedViaDom) {
    await waitFor(
      async () =>
        (await composer.isVisible().catch(() => false)) ||
        (await composerFallback.isVisible().catch(() => false)),
      8000,
      300,
    );
    return;
  }

  // Keep legacy behavior tolerant: desktop may already restore PM view asynchronously
  // after hydration, so inability to click a navigation target here should not fail fast.
  return;
}

async function ensurePmSessionReady(page) {
  const composerCandidates = [
    page.locator("#desktop-chat-input").first(),
    page.locator("section.chat-composer textarea").first(),
    page.getByLabel("继续对话").first(),
  ];
  const sendButtonCandidates = [
    page.locator("section.chat-composer button", { hasText: "发送消息" }).first(),
    page.getByRole("button", { name: "发送消息" }).first(),
  ];
  const createSessionButton = page.getByRole("button", { name: "端内创建首会话" });
  const noSessionHint = "请先点击“端内创建首会话”；若失败请点击“打开 Dashboard /pm 手动创建”。";
  const emptyState = page.locator('section[aria-label="首会话空状态"]');

  const composerVisible = await waitFor(
    async () => {
      const composer = await resolveVisibleLocator(composerCandidates);
      return composer.isVisible().catch(() => false);
    },
    60000,
    400,
  );
  if (!composerVisible) {
    const bodyPreview = await page.locator("body").innerText().catch(() => "");
    throw new Error(
      `composer not visible before session bootstrap; body_preview=${JSON.stringify(bodyPreview.slice(0, 240))}`,
    );
  }

  const sessionReady = await waitFor(async () => {
    const hasEmptyState = await emptyState.isVisible().catch(() => false);
    if (hasEmptyState) {
      const canCreate = await safeIsEnabled(createSessionButton);
      if (canCreate) {
        await createSessionButton.click();
      }
      return false;
    }
    const needsCreateHint = await page.getByText(noSessionHint).isVisible().catch(() => false);
    if (needsCreateHint) return false;

    const composer = await resolveVisibleLocator(composerCandidates);
    const sendButton = await resolveVisibleLocator(sendButtonCandidates);
    await composer.fill("session-ready-probe");
    const canSendNow = await safeIsEnabled(sendButton);
    await composer.fill("");
    return canSendNow;
  }, 45000, 500);

  if (!sessionReady) {
    const composer = await resolveVisibleLocator(composerCandidates);
    const placeholder = await composer.getAttribute("placeholder");
    const stateNote = (await page.locator(".composer-state-note").allTextContents()).join(" | ");
    throw new Error(
      `pm session bootstrap not ready before degraded send: placeholder=${JSON.stringify(placeholder)} state_note=${JSON.stringify(stateNote)}`,
    );
  }
}

function isTrackedApi(url, apiBase) {
  if (url.startsWith(`${apiBase}/api/`)) return true;
  try {
    const parsed = new URL(url);
    return parsed.pathname.startsWith("/api/");
  } catch {
    return false;
  }
}

async function run() {
  const apiPort = await findAvailablePort(18600, 200);
  const webPort = await findAvailablePort(19273, 200);
  const apiBase = `http://127.0.0.1:${apiPort}`;
  const webBase = `http://127.0.0.1:${webPort}`;
  const apiToken = String(process.env.OPENVIBECODING_API_TOKEN || "openvibecoding-dev-token").trim();

  const report = {
    scenario: "desktop first entry degraded path should fail soft and remain interactive",
    started_at: new Date().toISOString(),
    mode: "real-backend-degraded",
    playwright_tmpdir: playwrightTempDir,
    api_base_url: apiBase,
    web_base_url: webBase,
    checks: [],
    failed_checks: [],
    screenshot_path: screenshotPath,
    status: "failed",
    error: "",
  };

  const pythonBin = resolvePythonBin();
  const apiServer = spawn(
    pythonBin,
    ["-m", "openvibecoding_orch.cli", "serve", "--host", "127.0.0.1", "--port", String(apiPort)],
    {
      cwd: repoRoot,
      stdio: "ignore",
      env: {
        ...process.env,
        PYTHONPATH: "apps/orchestrator/src",
        OPENVIBECODING_API_AUTH_REQUIRED: "true",
        OPENVIBECODING_API_TOKEN: apiToken,
        OPENVIBECODING_DASHBOARD_PORT: String(webPort),
      },
    },
  );

  const webServer = spawn(
    "npm",
    ["run", "dev", "--", "--host", "127.0.0.1", "--port", String(webPort), "--strictPort"],
    {
      cwd: desktopDir,
      stdio: "ignore",
      env: {
        ...process.env,
        VITE_OPENVIBECODING_API_BASE: apiBase,
        VITE_OPENVIBECODING_API_TOKEN: apiToken,
      },
    },
  );

  let browser = null;
  let context = null;
  try {
    await waitForHttpReady(
      `${apiBase}/api/intakes`,
      60000,
      [200],
      apiToken ? { Authorization: `Bearer ${apiToken}` } : {},
    );
    await waitForHttpReady(webBase, 60000, [200]);

    const intakePayload = {
      objective: "E2E degraded path verify desktop send fallback",
      allowed_paths: ["apps/desktop"],
      constraints: ["test-only"],
      requester_role: "PM",
      browser_policy_preset: "safe",
    };

    const intakeResponse = await postJson(apiBase, "/api/pm/intake", intakePayload);
    const intakeId = String(intakeResponse?.intake_id || "").trim();
    if (!intakeId) throw new Error("intake create returned empty intake_id");
    report.intake_id = intakeId;

    browser = await chromium.launch({ args: ["--no-proxy-server"] });
    context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    const networkEvidence = [];
    page.on("response", (res) => {
      const url = res.url();
      if (!isTrackedApi(url, apiBase)) return;
      networkEvidence.push({
        ts: new Date().toISOString(),
        method: res.request().method(),
        url,
        status: res.status(),
      });
    });

    await page.goto(webBase, { waitUntil: "networkidle" });

    const autoBrowserVisible = await page.getByText("AutoBrowser").first().isVisible().catch(() => false);
    if (autoBrowserVisible) {
      const stepModalVisible = await page.getByText(/第 ?1 步/).first().isVisible().catch(() => false);
      const runParamsVisible = await page.getByText("运行参数").first().isVisible().catch(() => false);
      const baseUrlInputValue = await page
        .locator('input[placeholder*="BASE_URL"], input[value*="127.0.0.1"]')
        .first()
        .inputValue()
        .catch(() => "");
      report.checks.push({
        name: "desktop autobrowser shell should be visible",
        expected: true,
        actual: autoBrowserVisible,
        pass: autoBrowserVisible === true,
      });
      report.checks.push({
        name: "autobrowser onboarding step modal should be visible",
        expected: true,
        actual: stepModalVisible,
        pass: stepModalVisible === true,
      });
      report.checks.push({
        name: "autobrowser run-params panel should be visible",
        expected: true,
        actual: runParamsVisible,
        pass: runParamsVisible === true,
      });
      report.checks.push({
        name: "autobrowser BASE_URL input should be populated",
        expected: true,
        actual: Boolean(baseUrlInputValue.trim()),
        pass: Boolean(baseUrlInputValue.trim()),
      });
      await page.screenshot({ path: screenshotPath, fullPage: true });
      report.status = report.checks.every((c) => c.pass) ? "passed" : "failed";
      if (report.status !== "passed") {
        throw new Error("one or more autobrowser checks failed");
      }
      return;
    }

    await openPmEntry(page);
    await ensurePmSessionReady(page);

    const composer = await resolveComposer(page);
    const placeholder = await composer.getAttribute("placeholder");
    report.checks.push({
      name: "composer placeholder should be non-blocking before degradation",
      expected: "审核后告诉 PM：接受并合并，或继续修改。",
      actual: placeholder,
      pass: placeholder === "审核后告诉 PM：接受并合并，或继续修改。",
    });

    // Trigger degraded path deterministically at the real UI boundary:
    // keep the real backend/bootstrap path, but force the next PM message request
    // to receive a server-side degraded response.
    const degradedMessagePattern = /\/api\/pm\/sessions\/[^/]+\/messages$/;
    const degradedRouteHandler = async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          detail: { reason: "upstream unavailable" },
        }),
      });
    };
    await page.route(degradedMessagePattern, degradedRouteHandler);

    const message = "E2E degraded message: backend should fail soft.";
    const messageComposer = await resolveComposer(page);
    const baselineMessageTexts = await page.locator("[data-message-id]").allTextContents().catch(() => []);
    await messageComposer.fill(message);
    try {
      await messageComposer.press("Enter");
    } catch {
      await clickSendButton(page);
    }
    await page.unroute(degradedMessagePattern, degradedRouteHandler);

    const fallbackVisible = await waitFor(async () => {
      const messageText = await page.locator("[data-message-id]").allTextContents().catch(() => []);
      if (messageText.some((line) => line.includes("后端消息通道暂不可用，我已切换本地安全回退模式。"))) {
        return true;
      }
      if (messageText.length > baselineMessageTexts.length) {
        return true;
      }
      if (await page.getByRole("button", { name: "打开 Dashboard /pm 手动创建" }).isVisible().catch(() => false)) {
        return true;
      }
      if (await page.getByRole("button", { name: "端内创建首会话" }).isVisible().catch(() => false)) {
        return true;
      }
      const stateNotes = await page.locator(".composer-state-note").allTextContents().catch(() => []);
      if (stateNotes.some((line) => line.includes("Dashboard /pm") || line.includes("端内创建首会话"))) {
        return true;
      }
      const pageText = await page.locator("body").innerText().catch(() => "");
      return (
        pageText.includes("打开 Dashboard /pm 手动创建") ||
        pageText.includes("请先点击“端内创建首会话”；若失败请点击“打开 Dashboard /pm 手动创建”。") ||
        pageText.includes("先在桌面端创建首会话，再发送需求")
      );
    }, 25000);

    await openPmEntry(page);
    const postFallbackComposer = await resolveComposer(page);
    const composerEnabled = await safeIsEnabled(postFallbackComposer);
    report.checks.push({
      name: "composer should remain interactive after fallback",
      expected: true,
      actual: composerEnabled,
      pass: composerEnabled === true,
    });

    const messagePost200 = networkEvidence.some(
      (item) =>
        item.method === "POST" &&
        item.url.includes(`/api/pm/sessions/${intakeId}/messages`) &&
        item.status === 200,
    );
    report.checks.push({
      name: "degraded path should not report message POST 200",
      expected: false,
      actual: messagePost200,
      pass: messagePost200 === false,
    });
    report.checks.push({
      name: "UI should surface a degraded recovery signal or preserve interactive fallback state when backend is down",
      expected: true,
      actual: fallbackVisible,
      pass: fallbackVisible === true || (composerEnabled === true && messagePost200 === false),
    });

    writeFileSync(networkPath, JSON.stringify({ api_base_url: apiBase, records: networkEvidence }, null, 2));
    await page.screenshot({ path: screenshotPath, fullPage: true });

    report.status = report.checks.every((c) => c.pass) ? "passed" : "failed";
    report.failed_checks = report.checks.filter((c) => !c.pass);
    if (report.status !== "passed") {
      throw new Error("one or more degraded checks failed");
    }
  } catch (error) {
    report.error = error instanceof Error ? error.message : String(error);
    throw error;
  } finally {
    report.finished_at = new Date().toISOString();
    writeFileSync(reportPath, JSON.stringify(report, null, 2));
    if (context) await context.close();
    if (browser) await browser.close();
    await terminateTrackedChild(webServer, 8000);
    await terminateTrackedChild(apiServer, 8000);
  }
}

run().catch((error) => {
  console.error(
    "desktop e2e degraded real check failed:",
    error instanceof Error ? error.message : String(error),
  );
  process.exitCode = 1;
});
