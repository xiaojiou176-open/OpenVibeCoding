"use client";

import * as Diff2Html from "diff2html";
import DOMPurify from "dompurify";
import { useMemo } from "react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";

type Props = {
  diff: string;
  allowedPaths?: string[];
  onRetry?: () => void;
};

function normalizePath(path: string) {
  return path.replace(/^([ab]|i|w|c|o)\//, "").replace(/^\.?\//, "").trim();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isAllowed(path: string, allowedPaths: string[]) {
  if (!allowedPaths || allowedPaths.length === 0) return true;
  const normalized = normalizePath(path);
  return allowedPaths.some((item) => {
    const rule = normalizePath(item);
    return normalized === rule || normalized.startsWith(`${rule}/`);
  });
}

const DANGEROUS_PROTOCOL = /^\s*javascript:/i;
const FORBID_TAGS = [
  "script",
  "iframe",
  "object",
  "embed",
  "link",
  "meta",
  "base",
  "form",
  "input",
  "button",
  "textarea",
  "select",
  "option",
];
const FORBID_ATTR = ["srcdoc"];
let domPurifyHardened = false;
let domPurifyInstance: typeof DOMPurify | null = null;

function getDomPurifyInstance() {
  if (domPurifyInstance) {
    return domPurifyInstance;
  }
  const candidate = DOMPurify as typeof DOMPurify & {
    default?: typeof DOMPurify;
  };
  if (typeof candidate?.addHook === "function" && typeof candidate?.sanitize === "function") {
    domPurifyInstance = candidate;
    return domPurifyInstance;
  }
  if (
    typeof window !== "undefined" &&
    typeof candidate === "function"
  ) {
    const created = candidate(window);
    domPurifyInstance = created;
    return domPurifyInstance;
  }
  if (
    typeof window !== "undefined" &&
    candidate?.default &&
    typeof candidate.default === "function"
  ) {
    const created = candidate.default(window);
    domPurifyInstance = created;
    return domPurifyInstance;
  }
  throw new Error("DOMPurify instance is unavailable");
}

function ensureDomPurifyHardened() {
  if (domPurifyHardened) {
    return;
  }
  const purify = getDomPurifyInstance();
  purify.addHook("uponSanitizeAttribute", (_node, data) => {
    const attrName = String(data.attrName || "").toLowerCase();
    if (attrName.startsWith("on") || attrName === "srcdoc") {
      data.keepAttr = false;
      return;
    }
    if (
      (attrName === "href" || attrName === "src" || attrName === "xlink:href") &&
      DANGEROUS_PROTOCOL.test(String(data.attrValue || ""))
    ) {
      data.keepAttr = false;
    }
  });
  domPurifyHardened = true;
}

export function sanitizeHtml(raw: string): string {
  const purify = getDomPurifyInstance();
  ensureDomPurifyHardened();
  return purify.sanitize(raw, {
    USE_PROFILES: { html: true },
    ALLOW_DATA_ATTR: false,
    ALLOW_UNKNOWN_PROTOCOLS: false,
    FORBID_TAGS,
    FORBID_ATTR,
  });
}

export default function DiffViewer({ diff, allowedPaths = [], onRetry }: Props) {
  const handleRetry = () => {
    if (onRetry) {
      onRetry();
      return;
    }
    window.location.reload();
  };

  /* All hooks are called unconditionally before any early return */
  const parseResult = useMemo(() => {
    if (!diff) return { files: [], parseError: "" };
    try {
      return { files: Diff2Html.parse(diff), parseError: "" };
    } catch (error) {
      return {
        files: [],
        parseError: error instanceof Error ? error.message : "Diff parse failed",
      };
    }
  }, [diff]);
  const files = parseResult.files;

  const outOfBounds = useMemo(() => {
    const paths: string[] = [];
    for (const file of files) {
      const f = file as { newName?: string; oldName?: string };
      const raw = f.newName && f.newName !== "/dev/null" ? f.newName : f.oldName;
      if (!raw) continue;
      const normalized = normalizePath(String(raw));
      if (!isAllowed(normalized, allowedPaths)) paths.push(normalized);
    }
    return Array.from(new Set(paths));
  }, [files, allowedPaths]);

  const renderResult = useMemo(() => {
    if (!diff) return { html: "", parseError: parseResult.parseError };
    try {
      let output = Diff2Html.html(diff, {
        drawFileList: false,
        matching: "lines",
        outputFormat: "line-by-line",
      });
      if (outOfBounds.length > 0) {
        for (const file of outOfBounds) {
          const safe = escapeRegExp(file);
          const pattern = new RegExp(`(<span class=\\"d2h-file-name\\">[^<]*?)(${safe})([^<]*?<\\/span>)`, "g");
          output = output.replace(pattern, `$1<span class=\\"d2h-oob-file\\">$2</span>$3`);
        }
      }
      return { html: sanitizeHtml(output), parseError: parseResult.parseError };
    } catch (error) {
      const renderError = error instanceof Error ? error.message : "Diff render failed";
      return {
        html: `<pre>${escapeHtml(diff)}</pre>`,
        parseError: parseResult.parseError || renderError,
      };
    }
  }, [diff, outOfBounds, parseResult.parseError]);

  /* Early returns AFTER all hooks */
  if (!diff) {
    return (
      <Card>
        <div className="empty-state-stack">
          <span className="muted">No code changes are available yet.</span>
          <span className="muted">Next: refresh to request the latest result again.</span>
          <Button type="button" variant="secondary" onClick={handleRetry}>
            Refresh this page
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <div className="diff-viewer-wrapper">
      {renderResult.parseError && (
        <Card variant="unstyled" className="alert alert-danger" role="alert">
          <div className="diff-oob-stack">
            <strong className="diff-oob-title">The diff cannot be shown right now.</strong>
            <span className="muted">Next: refresh first. If it still fails, reload run detail once.</span>
            <span className="mono text-xs">{renderResult.parseError}</span>
            <Button type="button" variant="secondary" onClick={handleRetry}>
              Retry refresh
            </Button>
          </div>
        </Card>
      )}
      {outOfBounds.length > 0 && (
        <Card variant="unstyled" className="alert alert-danger" role="alert">
          <div className="diff-oob-stack">
            <strong className="diff-oob-title">
              Files outside the assigned scope were detected.
            </strong>
            <span className="muted">Next: confirm whether these files should be touched before continuing.</span>
            <div className="diff-oob-list">
              {outOfBounds.map((file) => (
                <Badge key={file} variant="failed">{file}</Badge>
              ))}
            </div>
          </div>
        </Card>
      )}
      <div
        className="diff-viewer"
        dangerouslySetInnerHTML={{ __html: renderResult.html }}
      />
    </div>
  );
}
