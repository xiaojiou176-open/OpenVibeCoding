import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

function readCssBundle(entryPath: string, visited: Set<string> = new Set()): string {
  if (!existsSync(entryPath) || visited.has(entryPath)) {
    return "";
  }
  visited.add(entryPath);
  const css = readFileSync(entryPath, "utf8");
  const imports = [...css.matchAll(/@import\s+["'](.+?)["'];/g)];
  let bundledCss = css;
  for (const match of imports) {
    const importTarget = match[1];
    if (!importTarget.endsWith(".css")) {
      continue;
    }
    bundledCss += `\n${readCssBundle(resolve(dirname(entryPath), importTarget), visited)}`;
  }
  return bundledCss;
}

function loadDashboardCss(): string {
  const cssPath = (() => {
    try {
      return fileURLToPath(new URL("../app/globals.css", import.meta.url));
    } catch {
      return resolve(process.cwd(), "app/globals.css");
    }
  })();
  return readCssBundle(cssPath);
}

describe("dashboard landing home layout contract", () => {
  it("keeps the landing briefing shell aligned with the single-column hero structure", () => {
    const css = loadDashboardCss();

    expect(css).toMatch(
      /\.app-shell--landing\s+\.home-briefing-shell\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\);/m
    );
    expect(css).not.toMatch(
      /\.app-shell--landing\s+\.home-briefing-shell\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1\.18fr\)\s*420px;/m
    );
  });

  it("keeps the landing hero title on a mobile-specific scale instead of inheriting the oversized desktop clamp", () => {
    const css = loadDashboardCss();

    expect(css).toMatch(
      /@media\s*\(max-width:\s*640px\)\s*\{[\s\S]*?\.app-shell--landing\s+\.home-briefing-copy\s+\.page-title\s*\{\s*font-size:\s*clamp\(2\.25rem,\s*12vw,\s*3\.25rem\);/m
    );
    expect(css).toMatch(
      /@media\s*\(max-width:\s*640px\)\s*\{[\s\S]*?\.app-shell--landing\s+\.home-briefing-copy\s+\.page-subtitle\s*\{\s*max-width:\s*30ch;\s*font-size:\s*16px;/m
    );
  });

  it("keeps the dashboard shell product-first on mobile by placing the app main content before the sidebar chrome", () => {
    const css = loadDashboardCss();

    expect(css).toMatch(
      /@media\s*\(max-width:\s*920px\)\s*\{[\s\S]*?\.app-main\s*\{\s*order:\s*1;\s*\}/m
    );
    expect(css).toMatch(
      /@media\s*\(max-width:\s*920px\)\s*\{[\s\S]*?\.sidebar\s*\{[\s\S]*?order:\s*2;[\s\S]*?border-top:\s*1px solid var\(--color-border\);[\s\S]*?border-bottom:\s*0;/m
    );
  });
});
