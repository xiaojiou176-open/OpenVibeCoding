import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function normalizeValue(value) {
  const normalized = String(value || "").trim();
  return normalized.length > 0 ? normalized : "";
}

function sanitizeScope(scope) {
  return String(scope || "desktop-e2e").replace(/[^a-zA-Z0-9._-]/g, "-");
}

function resolveTempRoot(scriptDir) {
  const runnerTemp = normalizeValue(process.env.RUNNER_TEMP);
  if (runnerTemp) return resolve(runnerTemp);
  return resolve(scriptDir, "..", "..", "..", ".runtime-cache", "cache", "tmp");
}

export function configurePlaywrightTempDir(scope) {
  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const tempRoot = resolveTempRoot(scriptDir);
  const runToken =
    normalizeValue(process.env.GITHUB_RUN_ID) ||
    `${Date.now()}-${process.pid}`;
  const targetDir = resolve(tempRoot, "playwright-artifacts", sanitizeScope(scope), runToken);
  mkdirSync(targetDir, { recursive: true });

  process.env.TMPDIR = targetDir;
  process.env.TMP = targetDir;
  process.env.TEMP = targetDir;

  return targetDir;
}
