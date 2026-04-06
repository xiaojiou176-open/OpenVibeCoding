"use client";

import { useState } from "react";

import { Button } from "../ui/button";

type Props = {
  sharePath: string;
  fileName: string;
  payload: Record<string, unknown>;
};

export default function WorkflowCaseShareActions({ sharePath, fileName, payload }: Props) {
  const [feedback, setFeedback] = useState("");

  async function copyShareLink() {
    const shareUrl =
      typeof window !== "undefined" ? new URL(sharePath, window.location.origin).toString() : "";
    if (!shareUrl) {
      setFeedback("This environment cannot copy the share link automatically.");
      return;
    }
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
      } else if (typeof document !== "undefined") {
        const textarea = document.createElement("textarea");
        textarea.value = shareUrl;
        textarea.setAttribute("readonly", "");
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setFeedback("Copied the share-ready case link.");
    } catch {
      setFeedback("Copy failed. Use the address bar URL instead.");
    }
  }

  function downloadAsset() {
    if (typeof window === "undefined" || typeof document === "undefined") {
      setFeedback("This environment cannot export the case asset automatically.");
      return;
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    URL.revokeObjectURL(url);
    setFeedback("Downloaded the case asset JSON.");
  }

  return (
    <div className="stack-gap-2">
      <div className="toolbar">
        <Button variant="secondary" onClick={() => void copyShareLink()}>
          Copy share link
        </Button>
        <Button variant="secondary" onClick={downloadAsset}>
          Download case asset JSON
        </Button>
      </div>
      {feedback ? <p className="mono muted">{feedback}</p> : null}
    </div>
  );
}
