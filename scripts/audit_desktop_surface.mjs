#!/usr/bin/env node
import {createRequire} from "node:module";
import {mkdirSync, rmSync, writeFileSync} from "node:fs";
import {resolve, dirname} from "node:path";
import {fileURLToPath} from "node:url";
import {spawn} from "node:child_process";
import net from "node:net";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const OUT_DIR = resolve(ROOT, ".runtime-cache/test_output/desktop_surface");
const SUMMARY_JSON = resolve(OUT_DIR, "summary.json");
const SUMMARY_MD = resolve(OUT_DIR, "summary.md");
const DESKTOP_DIR = resolve(OUT_DIR, "screenshots/desktop");
const COMPACT_DIR = resolve(OUT_DIR, "screenshots/compact");

function loadPlaywright() {
  const candidates = [
    resolve(ROOT, "apps/desktop/package.json"),
    resolve(ROOT, "apps/dashboard/package.json"),
  ];
  for (const candidate of candidates) {
    try {
      const scopedRequire = createRequire(candidate);
      return scopedRequire("playwright");
    } catch {
      // Try next
    }
  }
  throw new Error("playwright dependency unavailable in desktop or dashboard package roots");
}

const {chromium} = loadPlaywright();

const NAV_ITEMS = [
  {page: "pm", label: "PM intake", anchor: async (page) => (await page.locator("text=/Start first request|Create the first session/i").count()) > 0},
  {page: "command-tower", label: "Command Tower", anchor: async (page) => (await page.locator("text=/Refresh progress|Retry refresh|All\\s+0|High risk\\s+0/i").count()) > 0},
  {page: "search", label: "Search", anchor: async (page) => (await page.locator("text=/Run ID/i").count()) > 0 && (await page.getByRole("button", {name: /Load/i}).count()) > 0},
  {page: "overview", label: "Overview", anchor: async (page) => (await page.locator("text=/Command deck overview|One operator loop/i").count()) > 0},
  {page: "runs", label: "Proof & Replay", anchor: async (page) => (await page.locator("text=/Proof & Replay|证明与回放/i").count()) > 0},
  {page: "workflows", label: "Workflow Cases", anchor: async (page) => (await page.locator("text=/Workflow Cases|工作流案例/i").count()) > 0},
  {page: "god-mode", label: "Quick approval", anchor: async (page) => (await page.locator("text=/Quick approval|快速审批/i").count()) > 0},
  {page: "events", label: "Events", anchor: async (page) => (await page.locator("text=/Events|Event stream|事件流/i").count()) > 0 && (await page.getByRole("button", {name: /Refresh|刷新/i}).count()) > 0},
  {page: "agents", label: "Role desk", anchor: async (page) => (await page.locator("text=/Role desk|角色桌/i").count()) > 0},
  {page: "reviews", label: "Reviews", anchor: async (page) => (await page.locator("text=/Reviews|Review queue|审查/i").count()) > 0 && (await page.getByRole("button", {name: /Refresh|刷新/i}).count()) > 0},
  {page: "change-gates", label: "Diff gate", anchor: async (page) => (await page.locator("text=/Diff gate|Diff Gate/i").count()) > 0},
  {page: "tests", label: "Tests", anchor: async (page) => (await page.locator("text=/Tests|测试/i").count()) > 0},
  {page: "contracts", label: "Contract desk", anchor: async (page) => (await page.locator("text=/Contract desk|合约桌/i").count()) > 0},
  {page: "policies", label: "Policies", anchor: async (page) => (await page.locator("text=/Policies|策略/i").count()) > 0},
  {page: "locks", label: "Locks", anchor: async (page) => (await page.locator("text=/Locks|Lock Management|锁/i").count()) > 0 && (await page.getByRole("button", {name: /Refresh|刷新/i}).count()) > 0},
  {page: "worktrees", label: "Worktrees", anchor: async (page) => (await page.locator("text=/Worktrees|工作树/i").count()) > 0},
];

function startServer(command, args, env = {}) {
  return spawn(command, args, {
    cwd: ROOT,
    env: {
      ...process.env,
      ...env,
    },
    stdio: "ignore",
  });
}

function runSync(command, args, env = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, args, {
      cwd: ROOT,
      env: {
        ...process.env,
        ...env,
      },
      stdio: "inherit",
    });
    child.on("exit", (code) => {
      if (code === 0) {
        resolveRun(true);
        return;
      }
      rejectRun(new Error(`${command} ${args.join(" ")} exited with code ${code}`));
    });
    child.on("error", rejectRun);
  });
}

function startManagedApiServer(apiPort, apiToken) {
  const command = [
    "source scripts/lib/toolchain_env.sh",
    `PYTHON_BIN="$(openvibecoding_python_bin "${ROOT}")"`,
    'if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then echo "missing managed python" >&2; exit 1; fi',
    `export PYTHONPATH="${resolve(ROOT, "apps/orchestrator/src")}"`,
    "export PYTHONDONTWRITEBYTECODE=1",
    "export OPENVIBECODING_API_AUTH_REQUIRED=true",
    `export OPENVIBECODING_API_TOKEN="${apiToken}"`,
    `exec "$PYTHON_BIN" -B -m openvibecoding_orch.cli serve --host 127.0.0.1 --port ${apiPort}`,
  ].join(" && ");
  return spawn("bash", ["-lc", command], {
    cwd: ROOT,
    env: {
      ...process.env,
    },
    stdio: "ignore",
  });
}

async function findOpenPort(start = 19500, end = 19580) {
  for (let port = start; port <= end; port += 1) {
    const available = await new Promise((resolveCheck) => {
      const server = net.createServer();
      server.once("error", () => resolveCheck(false));
      server.once("listening", () => server.close(() => resolveCheck(true)));
      server.listen(port, "127.0.0.1");
    });
    if (available) return port;
  }
  throw new Error(`no free port in range ${start}-${end}`);
}

async function waitForUrl(url, timeoutMs = 120000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // retry
    }
    await new Promise((resolveSleep) => setTimeout(resolveSleep, 800));
  }
  throw new Error(`timed out waiting for ${url}`);
}

async function waitForCondition(checkFn, timeoutMs = 20000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await checkFn()) return true;
    await new Promise((resolveSleep) => setTimeout(resolveSleep, 300));
  }
  return false;
}

function buildMarkdown(summary) {
  const lines = [
    "# Desktop Surface Audit",
    "",
    `- generated_at: ${summary.generated_at}`,
    `- base_url: ${summary.base_url}`,
    `- audited_pages: ${summary.routes.length}`,
    "",
    "| Page | Topbar | Desktop | Compact | Notes |",
    "| --- | --- | --- | --- | --- |",
  ];
  for (const route of summary.routes) {
    lines.push(
      `| \`${route.page}\` | ${route.topbar || "-"} | \`${route.desktop_screenshot}\` | \`${route.compact_screenshot}\` | ${route.issue || "ok"} |`
    );
  }
  if (summary.locale_checks) {
    lines.push(
      "",
      "## Locale",
      "",
      `- initial_toggle_label: ${summary.locale_checks.initial_label}`,
      `- zh_toggle_label: ${summary.locale_checks.zh_label}`,
      `- restored_toggle_label: ${summary.locale_checks.restored_label}`,
      `- issue: ${summary.locale_checks.issue || "ok"}`,
    );
  }
  if (summary.issues.length > 0) {
    lines.push("", "## Issues", "");
    for (const issue of summary.issues) lines.push(`- ${issue}`);
  }
  return `${lines.join("\n")}\n`;
}

async function main() {
  rmSync(OUT_DIR, {recursive: true, force: true});
  mkdirSync(DESKTOP_DIR, {recursive: true});
  mkdirSync(COMPACT_DIR, {recursive: true});

  const apiPort = await findOpenPort(19500, 19520);
  const desktopPort = await findOpenPort(19521, 19560);
  const apiToken = "openvibecoding-desktop-audit-token";
  const apiBase = `http://127.0.0.1:${apiPort}`;
  const desktopBase = `http://127.0.0.1:${desktopPort}`;

  await runSync("bash", ["scripts/install_desktop_deps.sh"]);

  const api = startManagedApiServer(apiPort, apiToken);
  const desktopServer = startServer("pnpm", ["--dir", "apps/desktop", "dev", "--host", "127.0.0.1", "--port", String(desktopPort)], {
    VITE_OPENVIBECODING_API_BASE: apiBase,
    VITE_OPENVIBECODING_API_TOKEN: apiToken,
    OPENVIBECODING_API_TOKEN: apiToken,
  });

  const browser = await chromium.launch();
  const page = await browser.newPage({viewport: {width: 1440, height: 1024}});

  try {
    await waitForUrl(`${apiBase}/health`, 30000);
    await waitForUrl(`${desktopBase}/`, 120000);
    await page.goto(`${desktopBase}/`, {waitUntil: "networkidle"});

    const localeToggle = page.locator(".topbar .workspace-picker .workspace-trigger").nth(2);
    const initialLabel = ((await localeToggle.textContent()) || "").trim();
    await localeToggle.click();
    await waitForCondition(async () => {
      const label = ((await localeToggle.textContent()) || "").trim();
      return label === "EN";
    }, 10000);
    const zhLabel = ((await localeToggle.textContent()) || "").trim();
    await localeToggle.click();
    await waitForCondition(async () => {
      const label = ((await localeToggle.textContent()) || "").trim();
      return label === "中文";
    }, 10000);
    const restoredLabel = ((await localeToggle.textContent()) || "").trim();

    const routes = [];
    const issues = [];
    for (const item of NAV_ITEMS) {
      await page.getByRole("button", {name: item.label}).first().click();
      await waitForCondition(item.anchor.bind(null, page), 15000);
      const topbar = ((await page.locator(".topbar-title").first().textContent()) || "").trim();
      const desktopShot = resolve(DESKTOP_DIR, `${item.page}.png`);
      const compactShot = resolve(COMPACT_DIR, `${item.page}.png`);
      await page.setViewportSize({width: 1440, height: 1024});
      await page.screenshot({path: desktopShot, fullPage: true});
      await page.setViewportSize({width: 768, height: 1024});
      await page.screenshot({path: compactShot, fullPage: true});
      await page.setViewportSize({width: 1440, height: 1024});

      const ok = await item.anchor(page);
      const record = {
        page: item.page,
        topbar,
        desktop_screenshot: desktopShot.replace(`${ROOT}/`, ""),
        compact_screenshot: compactShot.replace(`${ROOT}/`, ""),
        issue: ok ? "" : `${item.page} anchor contract failed`,
      };
      routes.push(record);
      if (!topbar) issues.push(`${item.page} missing topbar title`);
      if (record.issue) issues.push(record.issue);
    }

    const localeIssue =
      initialLabel !== "中文" || zhLabel !== "EN" || restoredLabel !== "中文"
        ? `locale toggle drifted: initial=${initialLabel}, zh=${zhLabel}, restored=${restoredLabel}`
        : "";
    if (localeIssue) issues.push(localeIssue);

    const summary = {
      generated_at: new Date().toISOString(),
      base_url: desktopBase,
      routes,
      locale_checks: {
        initial_label: initialLabel,
        zh_label: zhLabel,
        restored_label: restoredLabel,
        issue: localeIssue,
      },
      issues,
    };
    writeFileSync(SUMMARY_JSON, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    writeFileSync(SUMMARY_MD, buildMarkdown(summary), "utf8");
    console.log(`✅ [desktop-surface-audit] wrote ${SUMMARY_JSON.replace(`${ROOT}/`, "")}`);
    console.log(`✅ [desktop-surface-audit] wrote ${SUMMARY_MD.replace(`${ROOT}/`, "")}`);
    if (issues.length > 0) {
      console.log(`⚠️ [desktop-surface-audit] issues=${issues.length}`);
    } else {
      console.log("✅ [desktop-surface-audit] all audited desktop pages passed route-level display and interaction contracts");
    }
  } finally {
    await page.close();
    await browser.close();
    desktopServer.kill("SIGTERM");
    api.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(`❌ [desktop-surface-audit] ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
