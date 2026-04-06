import { spawn } from "node:child_process";
import { mkdirSync, readdirSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import net from "node:net";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const cwd = resolve(process.cwd());
const repoRoot = resolve(cwd, "..", "..");
const targetDir = resolve(repoRoot, ".runtime-cache", "test_output", "desktop_snapshots");
mkdirSync(targetDir, { recursive: true });
for (const fileName of readdirSync(targetDir)) {
  if (fileName.startsWith("desktop-layout-") && fileName.endsWith(".png")) {
    rmSync(resolve(targetDir, fileName), { force: true });
  }
}

const externalAuditUrl = process.env.DESKTOP_AUDIT_URL;
const viewports = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 }
];

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
        // keep retrying
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
    if (await isPortAvailable(port)) {
      return port;
    }
  }
  throw new Error(`no available port found in range ${startPort}-${startPort + maxProbe - 1}`);
}

async function run() {
  let preview = null;
  let url = externalAuditUrl;

  if (!url) {
    const port = await findAvailablePort(4173, 30);
    url = `http://127.0.0.1:${port}`;
    preview = spawn("npm", ["run", "preview", "--", "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
      cwd,
      stdio: "inherit"
    });
  }

  try {
    await waitForServer(url);

    const browser = await chromium.launch();
    const page = await browser.newPage();

    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(url, { waitUntil: "networkidle" });
      await page.screenshot({
        path: resolve(
          targetDir,
          `desktop-layout-${viewport.name}-${viewport.width}x${viewport.height}.png`
        ),
        fullPage: true
      });
    }

    await browser.close();
    console.log(`desktop snapshots written to: ${targetDir}`);
  } finally {
    if (preview) {
      preview.kill("SIGTERM");
    }
  }
}

run().catch((error) => {
  console.error("snapshot capture failed:", error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
