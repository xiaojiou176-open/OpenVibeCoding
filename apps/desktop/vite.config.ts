import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Recommended overrides: local -> VITEST_MAX_WORKERS=50% / VITEST_POOL=forks; use threads only for explicit diagnostics.
const maxWorkers = process.env.DESKTOP_VITEST_MAX_WORKERS ?? process.env.VITEST_MAX_WORKERS ?? "50%";
const pool = process.env.DESKTOP_VITEST_POOL ?? process.env.VITEST_POOL ?? "forks";
const coverageRunId = process.env.CORTEXPILOT_DESKTOP_COVERAGE_RUN_ID ?? `${process.pid}`;
const coverageReportsDirectory = process.env.CORTEXPILOT_DESKTOP_COVERAGE_DIR ?? path.join("coverage", `run-${coverageRunId}`);
const shouldEmitHtmlCoverage = !process.env.CI || process.env.CORTEXPILOT_COVERAGE_HTML === "1";
const coverageReporter = shouldEmitHtmlCoverage ? ["text", "html", "json-summary"] : ["text", "json-summary"];

function chunkDesktopVendors(id: string): string | undefined {
  if (!id.includes("node_modules/")) {
    return undefined;
  }
  if (id.includes("/react/") || id.includes("/react-dom/")) {
    return "react";
  }
  if (id.includes("/@xyflow/react/")) {
    return "flow";
  }
  if (id.includes("/react-markdown/") || id.includes("/remark-gfm/")) {
    return "markdown";
  }
  if (id.includes("/lucide-react/")) {
    return "icons";
  }
  if (id.includes("/sonner/")) {
    return "sonner";
  }
  return undefined;
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@cortexpilot/frontend-shared/uiCopy": path.resolve(process.cwd(), "../../packages/frontend-shared/uiCopy.ts"),
      "@cortexpilot/frontend-shared/uiLocale": path.resolve(process.cwd(), "../../packages/frontend-shared/uiLocale.ts"),
    },
  },
  build: {
    // Keep debuggability without exposing full source maps by default.
    sourcemap: process.env.CORTEXPILOT_DESKTOP_SOURCEMAP === "full" ? true : "hidden",
    rollupOptions: {
      output: {
        manualChunks: chunkDesktopVendors
      }
    }
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    pool,
    maxWorkers,
    // Keep file-level parallelism deterministic for coverage tmp artifacts.
    fileParallelism: false,
    coverage: {
      // Keep desktop:test focused on unit-tested app surfaces; real-backend E2E scripts are gated separately.
      exclude: ["**/scripts/**", "**/src/test/**", "**/src/styles.non-pm.css"],
      // Isolate coverage temp artifacts per process to avoid ENOENT races when desktop tests run concurrently.
      reportsDirectory: coverageReportsDirectory,
      reporter: coverageReporter,
      thresholds: {
        statements: 80,
        functions: 80,
        lines: 80,
        branches: 80,
      },
    },
  }
});
