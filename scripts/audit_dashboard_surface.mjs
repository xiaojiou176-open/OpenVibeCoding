#!/usr/bin/env node
import {createRequire} from "node:module";
import {mkdirSync, rmSync, writeFileSync} from "node:fs";
import {resolve, dirname} from "node:path";
import {fileURLToPath} from "node:url";
import {spawn} from "node:child_process";
import net from "node:net";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const OUT_DIR = resolve(ROOT, ".runtime-cache/test_output/dashboard_surface");
const SUMMARY_JSON = resolve(OUT_DIR, "summary.json");
const SUMMARY_MD = resolve(OUT_DIR, "summary.md");
const DESKTOP_DIR = resolve(OUT_DIR, "screenshots/desktop");
const MOBILE_DIR = resolve(OUT_DIR, "screenshots/mobile");

const require = createRequire(import.meta.url);
const {chromium} = require(resolve(ROOT, "apps/dashboard/node_modules/playwright"));

const ROUTES = [
  {
    path: "/",
    label: "home",
    checks: async (page) => {
      const hero = await page.locator("h1").first().textContent();
      const primaryButtons =
        (await page.getByRole("link", {name: /Open command tower|See first proven workflow|Choose the right adoption path/i}).count()) +
        (await page.getByRole("button", {name: /Open command tower|See first proven workflow|Choose the right adoption path/i}).count());
      return {
        hero: hero?.trim() || "",
        primary_actions: primaryButtons,
        issue:
          primaryButtons < 1
            ? "homepage missing primary navigation CTA"
            : "",
      };
    },
  },
  {
    path: "/pm",
    label: "pm",
    checks: async (page) => {
      const startRequest = await page.locator("text=/Start first request|启动首个任务|Start the first request/i").count();
      const textboxes = await page.locator("textarea, input").count();
      return {
        start_request_cta: startRequest,
        input_count: textboxes,
        issue: startRequest < 1 ? "pm route missing first-request CTA" : textboxes < 1 ? "pm route missing composer inputs" : "",
      };
    },
  },
  {
    path: "/command-tower",
    label: "command-tower",
    checks: async (page) => {
      const focusButton = page.getByRole("button", {name: /Focus high-risk sessions/i});
      let exists = 0;
      let clicked = false;
      try {
        exists = await focusButton.count();
        if (exists > 0) {
          await focusButton.first().click();
          clicked = true;
        }
      } catch {
        clicked = false;
      }
      return {
        focus_toggle_present: exists,
        focus_toggle_clicked: clicked,
        issue: exists < 1 ? "command-tower missing focus toggle" : clicked ? "" : "command-tower focus toggle could not be clicked",
      };
    },
  },
  {
    path: "/agents",
    label: "agents",
    checks: async (page) => {
      const details = await page.locator("details").count();
      const roleDesk = await page.locator("text=/Role desk|角色桌/i").count();
      return {
        details_count: details,
        role_desk_mentions: roleDesk,
        issue: roleDesk < 1 ? "agents route missing role-desk framing" : "",
      };
    },
  },
  {
    path: "/search",
    label: "search",
    checks: async (page) => {
      const runInput = await page.locator("input[placeholder='Run ID'], input[aria-label='Run ID']").count();
      const loadButton = await page.getByRole("button", {name: /Load/i}).count();
      return {
        run_input_present: runInput,
        load_button_present: loadButton,
        issue: runInput < 1 || loadButton < 1 ? "search route missing run-id load controls" : "",
      };
    },
  },
  {
    path: "/workflows",
    label: "workflows",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "workflows route missing h1"};
    },
  },
  {
    path: "/runs",
    label: "runs",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "runs route missing h1"};
    },
  },
  {
    path: "/contracts",
    label: "contracts",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "contracts route missing h1"};
    },
  },
  {
    path: "/events",
    label: "events",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "events route missing h1"};
    },
  },
  {
    path: "/reviews",
    label: "reviews",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "reviews route missing h1"};
    },
  },
  {
    path: "/tests",
    label: "tests",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "tests route missing h1"};
    },
  },
  {
    path: "/policies",
    label: "policies",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "policies route missing h1"};
    },
  },
  {
    path: "/locks",
    label: "locks",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "locks route missing h1"};
    },
  },
  {
    path: "/worktrees",
    label: "worktrees",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "worktrees route missing h1"};
    },
  },
  {
    path: "/god-mode",
    label: "god-mode",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "god-mode route missing h1"};
    },
  },
  {
    path: "/diff-gate",
    label: "diff-gate",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "diff-gate route missing h1"};
    },
  },
  {
    path: "/planner",
    label: "planner",
    checks: async (page) => {
      const h1 = (await page.locator("h1").first().textContent())?.trim() || "";
      return {issue: h1 ? "" : "planner route missing h1"};
    },
  },
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

function startManagedApiServer(apiPort, apiToken) {
  const command = [
    "source scripts/lib/toolchain_env.sh",
    `PYTHON_BIN="$(openvibecoding_python_bin "${ROOT}")"`,
    'if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then echo "missing managed python" >&2; exit 1; fi',
    `export PYTHONPATH="${resolve(ROOT, "apps/orchestrator/src")}"`,
    'export PYTHONDONTWRITEBYTECODE=1',
    'export OPENVIBECODING_API_AUTH_REQUIRED=true',
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

async function findOpenPort(start = 19400, end = 19450) {
  for (let port = start; port <= end; port += 1) {
    const available = await new Promise((resolveCheck) => {
      const server = net.createServer();
      server.once("error", () => resolveCheck(false));
      server.once("listening", () => server.close(() => resolveCheck(true)));
      server.listen(port, "127.0.0.1");
    });
    if (available) {
      return port;
    }
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
      // Retry
    }
    await new Promise((resolveSleep) => setTimeout(resolveSleep, 800));
  }
  throw new Error(`timed out waiting for ${url}`);
}

function buildMarkdown(summary) {
  const lines = [
    "# Dashboard Surface Audit",
    "",
    `- generated_at: ${summary.generated_at}`,
    `- base_url: ${summary.base_url}`,
    `- audited_routes: ${summary.routes.length}`,
    "",
    "| Route | H1 | Desktop | Mobile | Notes |",
    "| --- | --- | --- | --- | --- |",
  ];
  for (const route of summary.routes) {
    lines.push(
      `| \`${route.path}\` | ${route.h1 || "-"} | \`${route.desktop_screenshot}\` | \`${route.mobile_screenshot}\` | ${route.issue || "ok"} |`
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
  mkdirSync(MOBILE_DIR, {recursive: true});

  const apiPort = await findOpenPort(19400, 19420);
  const dashboardPort = await findOpenPort(19421, 19450);
  const apiToken = "openvibecoding-dashboard-audit-token";
  const apiBase = `http://127.0.0.1:${apiPort}`;
  const dashboardBase = `http://127.0.0.1:${dashboardPort}`;

  const api = startManagedApiServer(apiPort, apiToken);

  const dashboard = startServer("pnpm", ["--dir", "apps/dashboard", "dev", "--hostname", "127.0.0.1", "--port", String(dashboardPort)], {
    NEXT_PUBLIC_OPENVIBECODING_API_BASE: apiBase,
    NEXT_PUBLIC_OPENVIBECODING_API_TOKEN: apiToken,
    OPENVIBECODING_API_TOKEN: apiToken,
  });

  const browser = await chromium.launch();
  const desktop = await browser.newPage({viewport: {width: 1440, height: 1024}});
  const mobile = await browser.newPage({
    viewport: {width: 390, height: 844},
    isMobile: true,
    hasTouch: true,
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  });

  try {
    await waitForUrl(`${apiBase}/health`, 30000);
    await waitForUrl(`${dashboardBase}/`, 120000);

    const routes = [];
    const issues = [];
    for (const route of ROUTES) {
      const url = `${dashboardBase}${route.path}`;
      await desktop.goto(url, {waitUntil: "networkidle"});
      await mobile.goto(url, {waitUntil: "networkidle"});
      const h1 = (await desktop.locator("h1").first().textContent())?.trim() || "";
      const desktopShot = resolve(DESKTOP_DIR, `${route.label}.png`);
      const mobileShot = resolve(MOBILE_DIR, `${route.label}.png`);
      await desktop.screenshot({path: desktopShot, fullPage: true});
      await mobile.screenshot({path: mobileShot, fullPage: true});
      const result = await route.checks(desktop);
      const record = {
        path: route.path,
        h1,
        desktop_screenshot: desktopShot.replace(`${ROOT}/`, ""),
        mobile_screenshot: mobileShot.replace(`${ROOT}/`, ""),
        ...result,
      };
      routes.push(record);
      if (!h1) issues.push(`${route.path} missing h1`);
      if (record.issue) issues.push(`${route.path}: ${record.issue}`);
    }

    const summary = {
      generated_at: new Date().toISOString(),
      base_url: dashboardBase,
      routes,
      issues,
    };
    writeFileSync(SUMMARY_JSON, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    writeFileSync(SUMMARY_MD, buildMarkdown(summary), "utf8");
    console.log(`✅ [dashboard-surface-audit] wrote ${SUMMARY_JSON.replace(`${ROOT}/`, "")}`);
    console.log(`✅ [dashboard-surface-audit] wrote ${SUMMARY_MD.replace(`${ROOT}/`, "")}`);
    if (issues.length > 0) {
      console.log(`⚠️ [dashboard-surface-audit] issues=${issues.length}`);
    } else {
      console.log("✅ [dashboard-surface-audit] all audited routes passed route-level display and interaction contracts");
    }
  } finally {
    await desktop.close();
    await mobile.close();
    await browser.close();
    dashboard.kill("SIGTERM");
    api.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(`❌ [dashboard-surface-audit] ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
