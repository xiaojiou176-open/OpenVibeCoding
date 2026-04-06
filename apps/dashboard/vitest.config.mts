import fs from "node:fs";
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Recommended overrides: local -> VITEST_MAX_WORKERS=50% / VITEST_POOL=forks; CI heavy load -> 25%-50%.
const maxWorkers = process.env.DASHBOARD_VITEST_MAX_WORKERS ?? process.env.VITEST_MAX_WORKERS ?? "50%";
const defaultPool = "forks";
const requestedPool = process.env.DASHBOARD_VITEST_POOL ?? process.env.VITEST_POOL ?? defaultPool;
const unstablePools = new Set(["vmThreads"]);
const pool = unstablePools.has(requestedPool) ? "forks" : requestedPool;
const coverageEnabled = process.argv.includes("--coverage");
// v8 coverage writes per-worker temp files under coverage/.tmp; on busy GitHub-hosted CI runners
// the full dashboard suite can race that temp directory when many workers flush at once.
const serialCoverageMode = Boolean(
  coverageEnabled &&
    (
      process.env.CI ||
      process.env.CORTEXPILOT_DASHBOARD_SERIAL_COVERAGE === "1" ||
      process.env.CORTEXPILOT_CI_SERIAL_COVERAGE === "1"
    ),
);
if (pool !== requestedPool) {
  console.warn(
    `[vitest] pool '${requestedPool}' is downgraded to 'forks' to avoid ESM worker bootstrap conflicts in jsdom coverage mode`,
  );
}
const shouldEmitHtmlCoverage = !process.env.CI || process.env.CORTEXPILOT_COVERAGE_HTML === "1";
const coverageReporter = shouldEmitHtmlCoverage ? ["text", "html", "json-summary"] : ["text", "json-summary"];
const coverageReportsDirectory = path.resolve(process.cwd(), "coverage");
const coverageClean = !serialCoverageMode;
const coverageProcessingConcurrency = serialCoverageMode ? 1 : undefined;
const testTimeout = process.env.CI ? 45000 : 15000;
if (coverageEnabled) {
  fs.mkdirSync(path.join(coverageReportsDirectory, ".tmp"), { recursive: true });
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@cortexpilot/frontend-shared/uiCopy": path.resolve(process.cwd(), "../../packages/frontend-shared/uiCopy.ts"),
      "@cortexpilot/frontend-shared/uiLocale": path.resolve(process.cwd(), "../../packages/frontend-shared/uiLocale.ts"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx", "tests/**/*.suite.ts", "tests/**/*.suite.tsx"],
    globals: true,
    pool,
    singleFork: serialCoverageMode,
    maxWorkers: serialCoverageMode ? 1 : maxWorkers,
    fileParallelism: !serialCoverageMode,
    testTimeout,
    coverage: {
      provider: "v8",
      reporter: coverageReporter,
      reportsDirectory: coverageReportsDirectory,
      clean: coverageClean,
      processingConcurrency: coverageProcessingConcurrency,
      thresholds: {
        statements: 85,
        functions: 85,
        lines: 85,
        branches: 80,
      },
      exclude: ["**/tests/**", "**/node_modules/**"],
    },
  },
});
