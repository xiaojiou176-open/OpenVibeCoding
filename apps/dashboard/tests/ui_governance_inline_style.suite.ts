import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

function collectTsxFiles(dir: string): string[] {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectTsxFiles(fullPath));
      continue;
    }
    if (entry.isFile() && fullPath.endsWith(".tsx")) {
      files.push(fullPath);
    }
  }
  return files;
}

function relative(filePath: string): string {
  return path.relative(projectRoot, filePath).replaceAll(path.sep, "/");
}

describe("ui governance: inline style guard", () => {
  it("forbids style prop object literal in app/components tsx", () => {
    const roots = [path.join(projectRoot, "app"), path.join(projectRoot, "components")];
    const violations: string[] = [];
    for (const root of roots) {
      for (const filePath of collectTsxFiles(root)) {
        const source = fs.readFileSync(filePath, "utf-8");
        if (source.includes("style={{")) {
          violations.push(relative(filePath));
        }
      }
    }
    expect(violations).toEqual([]);
  });

  it("forbids embedded <style> blocks in app/components tsx", () => {
    const roots = [path.join(projectRoot, "app"), path.join(projectRoot, "components")];
    const violations: string[] = [];
    for (const root of roots) {
      for (const filePath of collectTsxFiles(root)) {
        const source = fs.readFileSync(filePath, "utf-8");
        if (source.includes("<style>") || source.includes("<style>{")) {
          violations.push(relative(filePath));
        }
      }
    }
    expect(violations).toEqual([]);
  });
});
