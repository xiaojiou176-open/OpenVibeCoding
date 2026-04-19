#!/usr/bin/env node
import {createRequire} from "node:module";
import {mkdirSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import {resolve, dirname} from "node:path";
import {fileURLToPath} from "node:url";
import {spawn} from "node:child_process";
import net from "node:net";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const REGISTRY_PATH = resolve(ROOT, "configs/docs_nav_registry.json");
const OUT_DIR = resolve(ROOT, ".runtime-cache/test_output/public_docs_surface");
const SUMMARY_JSON = resolve(OUT_DIR, "summary.json");
const SUMMARY_MD = resolve(OUT_DIR, "summary.md");
const SCREENSHOT_DIR = resolve(OUT_DIR, "screenshots");
const DESKTOP_SCREENSHOT_DIR = resolve(SCREENSHOT_DIR, "desktop");
const MOBILE_SCREENSHOT_DIR = resolve(SCREENSHOT_DIR, "mobile");

const require = createRequire(import.meta.url);
const {chromium} = require(resolve(ROOT, "apps/dashboard/node_modules/playwright"));

function loadRegistry() {
  const payload = JSON.parse(readFileSync(REGISTRY_PATH, "utf8"));
  const entries = Array.isArray(payload.entries) ? payload.entries : [];
  return entries.filter((entry) =>
    entry &&
    entry.kind === "entrypoint" &&
    entry.status === "active" &&
    entry.canonical === true &&
    typeof entry.path === "string" &&
    entry.path.startsWith("docs/")
  );
}

function routeSlugFromPath(path) {
  const token = path.replace(/^docs\//, "").replace(/\/index\.html$/, "").replace(/\.html$/, "").replace(/\//g, "-");
  return token || "home";
}

function docsUrlFromPath(baseUrl, docsPath) {
  const normalized = docsPath.replace(/^docs/, "").replace(/index\.html$/, "");
  if (!normalized || normalized === "/") {
    return `${baseUrl}/docs/`;
  }
  return `${baseUrl}/docs${normalized}`;
}

async function findOpenPort(start = 4188, end = 4210) {
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

async function waitForUrl(url, timeoutMs = 30000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // Retry
    }
    await new Promise((resolveSleep) => setTimeout(resolveSleep, 500));
  }
  throw new Error(`timed out waiting for ${url}`);
}

function startLocalServer(port) {
  const server = spawn("python3", ["-B", "-m", "http.server", String(port), "-d", ROOT], {
    cwd: ROOT,
    stdio: "ignore",
  });
  return server;
}

function buildMarkdown(summary) {
  const lines = [
    "# Public Docs Surface Audit",
    "",
    `- generated_at: ${summary.generated_at}`,
    `- base_url: ${summary.base_url}`,
    `- audited_routes: ${summary.routes.length}`,
    `- desktop_screenshots: ${summary.desktop_screenshot_dir}`,
    `- mobile_screenshots: ${summary.mobile_screenshot_dir}`,
    "",
    "| Route | Title | H1 | Description | OG image | Internal links | Buttons / Details / Video | Screenshots |",
    "| --- | --- | --- | --- | --- | --- | --- | --- |",
  ];
  for (const route of summary.routes) {
    lines.push(
      `| \`${route.route}\` | ${route.title || "-"} | ${route.h1 || "-"} | ${route.description || "-"} | ${route.og_image || "-"} | ${route.internal_link_count} ok / ${route.broken_internal_links.length} broken | ${route.button_count} / ${route.details_count} / ${route.video_count} | \`${route.desktop_screenshot_path}\`<br/>\`${route.mobile_screenshot_path}\` |`
    );
  }
  if (summary.issues.length > 0) {
    lines.push("", "## Issues", "");
    for (const issue of summary.issues) {
      lines.push(`- ${issue}`);
    }
  }
  return `${lines.join("\n")}\n`;
}

async function auditInternalLinks(urls) {
  const broken = [];
  for (const url of urls) {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        broken.push(`${url} -> ${response.status}`);
      }
    } catch (error) {
      broken.push(`${url} -> ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return broken;
}

async function main() {
  rmSync(OUT_DIR, {recursive: true, force: true});
  mkdirSync(DESKTOP_SCREENSHOT_DIR, {recursive: true});
  mkdirSync(MOBILE_SCREENSHOT_DIR, {recursive: true});
  const port = await findOpenPort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const server = startLocalServer(port);
  const browser = await chromium.launch();
  const desktopPage = await browser.newPage({viewport: {width: 1440, height: 1024}});
  const mobilePage = await browser.newPage({
    viewport: {width: 390, height: 844},
    isMobile: true,
    hasTouch: true,
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  });

  try {
    await waitForUrl(`${baseUrl}/docs/`);
    const routes = [];
    const issues = [];
    for (const entry of loadRegistry()) {
      const route = entry.path.replace(/^docs/, "");
      const url = docsUrlFromPath(baseUrl, entry.path);
      await desktopPage.goto(url, {waitUntil: "networkidle"});
      await mobilePage.goto(url, {waitUntil: "networkidle"});
      const routeSummary = await desktopPage.evaluate((origin) => {
        const title = document.title || "";
        const h1 = document.querySelector("h1")?.textContent?.trim() || "";
        const description = document.querySelector('meta[name="description"]')?.getAttribute("content") || "";
        const ogTitle = document.querySelector('meta[property="og:title"]')?.getAttribute("content") || "";
        const ogDescription = document.querySelector('meta[property="og:description"]')?.getAttribute("content") || "";
        const ogImage = document.querySelector('meta[property="og:image"]')?.getAttribute("content") || "";
        const links = Array.from(document.querySelectorAll("a[href]"))
          .map((anchor) => anchor.href)
          .filter((href) => href.startsWith(origin) && !href.includes("#"));
        const internalLinks = Array.from(new Set(links));
        const buttonCount = document.querySelectorAll("button").length;
        const detailsCount = document.querySelectorAll("details").length;
        const videoCount = document.querySelectorAll("video").length;
        const trackCount = document.querySelectorAll("track[kind='captions']").length;
        const primaryActionCount = document.querySelectorAll(".actions a").length;
        return {
          title,
          h1,
          description,
          og_title: ogTitle,
          og_description: ogDescription,
          og_image: ogImage,
          internal_links: internalLinks,
          button_count: buttonCount,
          details_count: detailsCount,
          video_count: videoCount,
          caption_track_count: trackCount,
          primary_action_count: primaryActionCount,
        };
      }, baseUrl);
      const slug = routeSlugFromPath(entry.path);
      const desktopScreenshotPath = resolve(DESKTOP_SCREENSHOT_DIR, `${slug}.png`);
      const mobileScreenshotPath = resolve(MOBILE_SCREENSHOT_DIR, `${slug}.png`);
      await desktopPage.screenshot({path: desktopScreenshotPath, fullPage: true});
      await mobilePage.screenshot({path: mobileScreenshotPath, fullPage: true});
      const brokenInternalLinks = await auditInternalLinks(routeSummary.internal_links);
      const record = {
        route,
        url,
        desktop_screenshot_path: desktopScreenshotPath.replace(`${ROOT}/`, ""),
        mobile_screenshot_path: mobileScreenshotPath.replace(`${ROOT}/`, ""),
        internal_link_count: routeSummary.internal_links.length - brokenInternalLinks.length,
        broken_internal_links: brokenInternalLinks,
        ...routeSummary,
      };
      routes.push(record);
      if (!record.title) issues.push(`${route} missing <title>`);
      if (!record.h1) issues.push(`${route} missing <h1>`);
      if (!record.description) issues.push(`${route} missing meta description`);
      if (!record.og_image) issues.push(`${route} missing og:image`);
      if (record.broken_internal_links.length > 0) {
        issues.push(`${route} has broken internal links: ${record.broken_internal_links.join(", ")}`);
      }
      if (route === "/index.html") {
        if (record.video_count === 0) issues.push(`${route} missing hero video element`);
        if (record.caption_track_count === 0) issues.push(`${route} missing captions track for teaser video`);
        if (record.primary_action_count < 3) issues.push(`${route} hero primary actions dropped below 3`);
      }
    }

    const summary = {
      generated_at: new Date().toISOString(),
      base_url: baseUrl,
      desktop_screenshot_dir: DESKTOP_SCREENSHOT_DIR.replace(`${ROOT}/`, ""),
      mobile_screenshot_dir: MOBILE_SCREENSHOT_DIR.replace(`${ROOT}/`, ""),
      routes,
      issues,
    };
    writeFileSync(SUMMARY_JSON, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    writeFileSync(SUMMARY_MD, buildMarkdown(summary), "utf8");
    console.log(`✅ [public-docs-audit] wrote ${SUMMARY_JSON.replace(`${ROOT}/`, "")}`);
    console.log(`✅ [public-docs-audit] wrote ${SUMMARY_MD.replace(`${ROOT}/`, "")}`);
    console.log(`✅ [public-docs-audit] screenshots: ${SCREENSHOT_DIR.replace(`${ROOT}/`, "")}`);
    if (issues.length > 0) {
      console.log(`⚠️ [public-docs-audit] issues=${issues.length}`);
    } else {
      console.log("✅ [public-docs-audit] all audited routes expose title, h1, description, og:image, and valid internal-link/media contracts");
    }
  } finally {
    await desktopPage.close();
    await mobilePage.close();
    await browser.close();
    server.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(`❌ [public-docs-audit] ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
