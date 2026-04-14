import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import net from "node:net";
import { terminateTrackedChild } from "./host-process-safety.mjs";
import { configurePlaywrightTempDir } from "./playwright-tempdir.mjs";

const playwrightTempDir = configurePlaywrightTempDir("desktop-first-entry-no-block-real");
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const scriptDir = dirname(fileURLToPath(import.meta.url));
const desktopDir = resolve(scriptDir, "..");
const repoRoot = resolve(desktopDir, "..", "..");
const outputDir = resolve(repoRoot, ".runtime-cache", "test_output", "desktop_trust");
mkdirSync(outputDir, { recursive: true });

const screenshotPath = resolve(outputDir, "first_entry_no_block_real.png");
const reportPath = resolve(outputDir, "first_entry_no_block_real.json");
const networkPath = resolve(outputDir, "first_entry_no_block_real.network.json");

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

async function getJson(baseUrl, path) {
  const apiToken = String(process.env.OPENVIBECODING_API_TOKEN || "openvibecoding-dev-token").trim();
  const headers = {};
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
  const res = await fetchWithRetry(`${baseUrl}${path}`, {
    method: "GET",
    headers,
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
    throw new Error(`GET ${path} failed: ${res.status} ${JSON.stringify(data)}`);
  }
  return data;
}

async function waitFor(checkFn, timeoutMs = 15000, intervalMs = 400) {
  const start = Date.now();
  let lastError = null;
  while (Date.now() - start < timeoutMs) {
    try {
      const value = await checkFn();
      if (value) return true;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, intervalMs));
  }
  if (lastError) {
    throw lastError;
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
  return locator
    .evaluate((node) => {
      if (
        node instanceof HTMLButtonElement ||
        node instanceof HTMLInputElement ||
        node instanceof HTMLTextAreaElement
      ) {
        return !node.disabled;
      }
      return !node.hasAttribute("disabled");
    })
    .catch(() => false);
}

const CRITICAL_BLOCKER_DIALOG_NAME = "CRITICAL 阻断告警";
const CRITICAL_BLOCKER_CONFIRM_LABEL = "我已确认，进入人工裁决";

function isPointerInterceptionError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return /intercepts pointer events|subtree intercepts pointer events|not receiving pointer events/i.test(message);
}

async function dismissCriticalBlockerIfPresent(page) {
  const dialog = page.getByRole("dialog", { name: CRITICAL_BLOCKER_DIALOG_NAME }).first();
  const visible = await dialog.isVisible().catch(() => false);
  if (!visible) return false;

  const confirmButton = page.getByRole("button", { name: CRITICAL_BLOCKER_CONFIRM_LABEL }).first();
  if (await confirmButton.isVisible().catch(() => false)) {
    await confirmButton.click();
  } else {
    await page.keyboard.press("Escape").catch(() => {});
  }
  const closed = await waitFor(async () => !(await dialog.isVisible().catch(() => false)), 8000, 200);
  if (!closed) {
    throw new Error("critical blocker dialog is visible but could not be dismissed");
  }
  return true;
}

async function clickWithBlockerRecovery(page, candidate) {
  await dismissCriticalBlockerIfPresent(page);
  try {
    await candidate.click();
    return;
  } catch (error) {
    if (!isPointerInterceptionError(error)) {
      throw error;
    }
  }
  const dismissed = await dismissCriticalBlockerIfPresent(page);
  if (!dismissed) {
    throw new Error("PM entry click was blocked by overlay, but no CRITICAL blocker dialog was found");
  }
  await candidate.click();
}

async function clickWhenEnabled(locator, timeoutMs = 12000, intervalMs = 200) {
  const start = Date.now();
  let lastError = null;
  while (Date.now() - start < timeoutMs) {
    try {
      if (await safeIsEnabled(locator)) {
        try {
          await locator.click({ timeout: intervalMs * 3, noWaitAfter: true });
        } catch (error) {
          lastError = error;
          await locator.click({ timeout: intervalMs * 3, force: true, noWaitAfter: true });
        }
        return true;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, intervalMs));
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
  await dismissCriticalBlockerIfPresent(page);

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
    await clickWithBlockerRecovery(page, candidate);
    const switched = await waitFor(
      async () =>
        (await composer.isVisible().catch(() => false)) ||
        (await composerFallback.isVisible().catch(() => false)),
      8000,
      300,
    );
    if (switched) return;
  }

  await dismissCriticalBlockerIfPresent(page);
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
      `composer not visible before session bootstrap; page_url=${page.url()} body_preview=${JSON.stringify(bodyPreview.slice(0, 240))}`,
    );
  }

  const sessionReady = await waitFor(async () => {
    const hasEmptyState = await emptyState.isVisible().catch(() => false);
    if (hasEmptyState) {
      const canCreate = await createSessionButton.isEnabled().catch(() => false);
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
    const canSendNow = await sendButton.isEnabled();
    await composer.fill("");
    return canSendNow;
  }, 45000, 500);

  if (!sessionReady) {
    const composer = await resolveVisibleLocator(composerCandidates);
    const placeholder = await composer.getAttribute("placeholder");
    const stateNote = (await page.locator(".composer-state-note").allTextContents()).join(" | ");
    throw new Error(
      `pm session bootstrap not ready before send: placeholder=${JSON.stringify(placeholder)} state_note=${JSON.stringify(stateNote)}`,
    );
  }
}

async function waitForDesktopShellReady(page) {
  const ready = await waitFor(async () => {
    const bodyVisible = await page.locator("body").isVisible().catch(() => false);
    if (!bodyVisible) return false;

    const sidebarVisible = await page.locator('[data-testid="app-sidebar"], aside, nav').first().isVisible().catch(() => false);
    const pmComposerVisible = await page.locator("#desktop-chat-input, section.chat-composer textarea").first().isVisible().catch(() => false);
    const autobrowserVisible = await page.getByText("AutoBrowser").first().isVisible().catch(() => false);
    return sidebarVisible || pmComposerVisible || autobrowserVisible;
  }, 45000, 300);

  if (!ready) {
    const bodyPreview = await page.locator("body").innerText().catch(() => "");
    throw new Error(
      `desktop shell not ready after navigation; page_url=${page.url()} body_preview=${JSON.stringify(bodyPreview.slice(0, 240))}`,
    );
  }
}

function extractPmSessionIdFromMessageUrl(url) {
  const marker = "/api/pm/sessions/";
  const markerIndex = url.indexOf(marker);
  if (markerIndex < 0) return "";
  const tail = url.slice(markerIndex + marker.length);
  const messagesIndex = tail.indexOf("/messages");
  if (messagesIndex <= 0) return "";
  return tail.slice(0, messagesIndex).trim();
}

async function run() {
  const apiPort = await findAvailablePort(18500, 200);
  const webPort = await findAvailablePort(19173, 200);
  const apiBase = `http://127.0.0.1:${apiPort}`;
  const webBase = `http://127.0.0.1:${webPort}`;
  const apiToken = String(process.env.OPENVIBECODING_API_TOKEN || "openvibecoding-dev-token").trim();
  const forceCriticalBlocker = String(process.env.OPENVIBECODING_DESKTOP_E2E_FORCE_CRITICAL_BLOCKER || "").trim() === "1";

  const report = {
    scenario: "desktop first entry should not be blocked by stale pending decision (real backend)",
    started_at: new Date().toISOString(),
    mode: "real-backend",
    playwright_tmpdir: playwrightTempDir,
    api_base_url: apiBase,
    web_base_url: webBase,
    force_critical_blocker: forceCriticalBlocker,
    checks: [],
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
  let page = null;
  try {
    await waitForHttpReady(
      `${apiBase}/api/intakes`,
      90000,
      [200],
      apiToken ? { Authorization: `Bearer ${apiToken}` } : {},
    );
    await waitForHttpReady(webBase, 90000, [200]);

    const intakePayload = {
      objective: "E2E verify desktop first entry no blocking",
      allowed_paths: ["apps/desktop"],
      constraints: ["test-only"],
      requester_role: "PM",
      browser_policy_preset: "safe",
      acceptance_tests: [
        {
          name: "desktop-first-entry-real-e2e",
          cmd: "npm --prefix apps/desktop run e2e:first-entry:real",
          must_pass: true,
        },
      ],
    };

    const intakeResponse = await postJson(apiBase, "/api/pm/intake", intakePayload);
    const intakeId = String(intakeResponse?.intake_id || "").trim();
    if (!intakeId) {
      throw new Error("intake create succeeded but intake_id is empty");
    }
    report.intake_id = intakeId;

    browser = await chromium.launch({ args: ["--no-proxy-server"] });
    context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    page = await context.newPage();
    const networkEvidence = [];
    page.on("response", async (res) => {
      const url = res.url();
      if (!url.startsWith(`${apiBase}/api/`)) return;
      const method = res.request().method();
      networkEvidence.push({
        ts: new Date().toISOString(),
        method,
        url,
        status: res.status(),
      });
    });
    if (forceCriticalBlocker) {
      await page.route("**/api/command-tower/alerts*", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "critical",
            alerts: [{ code: "CRITICAL_GATE", severity: "critical", message: "forced critical blocker for e2e recovery path" }],
          }),
        });
      });
    }
    await page.goto(webBase, { waitUntil: "domcontentloaded" });
    await waitForDesktopShellReady(page);
    if (forceCriticalBlocker) {
      const forcedBlockerVisible = await waitFor(
        async () => await page.getByRole("dialog", { name: CRITICAL_BLOCKER_DIALOG_NAME }).first().isVisible().catch(() => false),
        10000,
        250,
      );
      report.checks.push({
        name: "forced critical blocker dialog should appear for recovery verification",
        expected: true,
        actual: forcedBlockerVisible,
        pass: forcedBlockerVisible === true,
      });
      if (!forcedBlockerVisible) {
        throw new Error("force-critical-blocker mode enabled but blocker dialog did not appear");
      }
    }
    const blockerDismissedAtEntry = await dismissCriticalBlockerIfPresent(page);
    if (blockerDismissedAtEntry || forceCriticalBlocker) {
      report.checks.push({
        name: "critical blocker dialog should be auto-dismissed before PM navigation",
        expected: forceCriticalBlocker ? true : false,
        actual: blockerDismissedAtEntry,
        pass: forceCriticalBlocker ? blockerDismissedAtEntry === true : true,
      });
      if (forceCriticalBlocker && !blockerDismissedAtEntry) {
        throw new Error("critical blocker dialog appeared but was not dismissed before PM navigation");
      }
    }

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
    const blockedHintVisible = await page
      .getByText("先完成上面的决策卡片，或继续补充你的约束...")
      .isVisible()
      .catch(() => false);
    const selectedDecisionVisible = await page
      .getByRole("button", { name: "已选择" })
      .isVisible()
      .catch(() => false);

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

    const userMessage = "E2E real message: please decompose and execute.";
    const firstComposer = await resolveComposer(page);
    const firstSendButton = await resolveSendButton(page);
    await dismissCriticalBlockerIfPresent(page);
    await firstComposer.fill(userMessage);
    await firstSendButton.click({ noWaitAfter: true });

    const pmAckVisible = await waitFor(async () => {
      const text = await page.locator("[data-message-id]").allTextContents();
      return text.some((line) => line.includes("我已接收需求，正在委派给 TL 进行拆解与执行。"));
    }, 20000);
    report.checks.push({
      name: "UI should render PM delegation ack after send",
      expected: true,
      actual: pmAckVisible,
      pass: pmAckVisible === true,
    });

    const messagePost200Observed = await waitFor(async () => {
      return networkEvidence.some(
        (item) =>
          item.method === "POST" &&
          item.url.includes("/api/pm/sessions/") &&
          item.url.includes("/messages") &&
          item.status === 200,
      );
    }, 20000);

    const resolvedSessionIdFromNetwork = (() => {
      for (let i = networkEvidence.length - 1; i >= 0; i -= 1) {
        const item = networkEvidence[i];
        if (item.method !== "POST" || item.status !== 200) continue;
        if (!item.url.includes("/api/pm/sessions/") || !item.url.includes("/messages")) continue;
        const sessionId = extractPmSessionIdFromMessageUrl(item.url);
        if (sessionId) return sessionId;
      }
      return "";
    })();
    const resolvedSessionId =
      resolvedSessionIdFromNetwork ||
      String(report.pm_session_id || "").trim() ||
      String(report.intake_id || "").trim();
    if (!resolvedSessionId) {
      throw new Error("unable to resolve real pm_session_id from message POST network evidence");
    }
    report.pm_session_id = resolvedSessionId;

    report.checks.push({
      name: "network should observe 200 for PM session message POST",
      expected: true,
      actual: messagePost200Observed,
      pass: messagePost200Observed === true,
    });

    const backendEventPersisted = await waitFor(async () => {
      const events = await getJson(apiBase, `/api/pm/sessions/${encodeURIComponent(resolvedSessionId)}/events?limit=120&tail=1`);
      if (!Array.isArray(events)) return false;
      return events.some((event) => {
        const context = event && typeof event === "object" ? event.context : null;
        const message = context && typeof context === "object" ? String(context.message || "") : "";
        return message === userMessage;
      });
    }, 20000);
    report.checks.push({
      name: "backend session events should persist the sent message",
      expected: true,
      actual: backendEventPersisted,
      pass: backendEventPersisted === true,
    });

    // Exercise stop-generation path with real UI interaction:
    // delay second POST to keep generation active long enough for manual stop click.
    const slowMessagePattern = new RegExp(`/api/pm/sessions/${resolvedSessionId}/messages$`);
    const delayedRouteHandler = async (route) => {
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 5000));
      try {
        await route.continue();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (!message.includes("Route is already handled")) {
          throw error;
        }
      }
    };
    await page.route(slowMessagePattern, delayedRouteHandler);

    const secondMessage = "E2E stop-generation probe message.";
    const secondComposer = await resolveComposer(page);
    const secondSendButton = await resolveSendButton(page);
    await dismissCriticalBlockerIfPresent(page);
    await secondComposer.fill(secondMessage);
    await secondSendButton.click({ noWaitAfter: true });

    const stopButton = page.getByRole("button", { name: "停止生成" });
    const stopClicked = await clickWhenEnabled(stopButton, 12000, 200);
    await page.unroute(slowMessagePattern, delayedRouteHandler);

    const stopAckVisible = await waitFor(async () => {
      const text = await page.locator("[data-message-id]").allTextContents();
      return text.some((line) => line.includes("已停止当前生成"));
    }, 10000);
    const stopDisabledAfterClick = !(await stopButton.isEnabled().catch(() => false));
    report.checks.push({
      name: "stop generation should be clickable while generation is active",
      expected: true,
      actual: stopClicked,
      pass: stopClicked === true,
    });
    report.checks.push({
      name: "stop generation should append stop acknowledgment message",
      expected: true,
      actual: stopAckVisible,
      pass: stopAckVisible === true,
    });
    report.checks.push({
      name: "stop generation should return button to disabled state",
      expected: true,
      actual: stopDisabledAfterClick,
      pass: stopDisabledAfterClick === true,
    });

    const requiredApiPrefixes = [`${apiBase}/api/pm/sessions`];
    for (const prefix of requiredApiPrefixes) {
      const ok = networkEvidence.some((item) => item.url.startsWith(prefix) && item.status === 200);
      report.checks.push({
        name: `network should observe 200 from ${prefix.replace(apiBase, "")}`,
        expected: true,
        actual: ok,
        pass: ok,
      });
    }
    writeFileSync(networkPath, JSON.stringify({ api_base_url: apiBase, records: networkEvidence }, null, 2));

    await page.screenshot({ path: screenshotPath, fullPage: true });

    report.status = report.checks.every((c) => c.pass) ? "passed" : "failed";
    if (report.status !== "passed") {
      throw new Error("one or more checks failed");
    }
  } catch (error) {
    report.error = error instanceof Error ? error.message : String(error);
    if (page) {
      try {
        await page.screenshot({ path: screenshotPath, fullPage: true });
      } catch {
        // best effort diagnostics
      }
    }
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
    "desktop e2e first-entry real-backend check failed:",
    error instanceof Error ? error.message : String(error),
  );
  process.exitCode = 1;
});
