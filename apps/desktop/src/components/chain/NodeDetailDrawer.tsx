import { Button } from "../ui/Button";
import type { ChainNodeData } from "../../lib/desktopUi";
import type { Node } from "@xyflow/react";

type NodeDetailDrawerProps = {
  open: boolean;
  selectedNodeId: string;
  selectedNode?: Node<ChainNodeData>;
  reviewDecision: "pending" | "accepted" | "rework";
  showRawNodeOutput: boolean;
  nodeRawOutput: string;
  onClose: () => void;
  onToggleRaw: () => void;
  onOpenDiff: () => void;
};

export function NodeDetailDrawer({
  open,
  selectedNodeId,
  selectedNode,
  reviewDecision,
  showRawNodeOutput,
  nodeRawOutput,
  onClose,
  onToggleRaw,
  onOpenDiff
}: NodeDetailDrawerProps) {
  if (!open) {
    return null;
  }
  return (
    <aside className="node-drawer" aria-label="Node detail drawer">
      <header className="node-drawer-header">
        <h2>Node Details · {selectedNode?.data.label ?? selectedNodeId}</h2>
        <Button variant="icon" onClick={onClose} aria-label="Close node details">
          ×
        </Button>
      </header>
      <div className="node-drawer-content">
        <p><strong>Role:</strong> {selectedNode?.data.role ?? "Unknown"}</p>
        <p><strong>Status:</strong> {selectedNode?.data.status ?? "unknown"}</p>
        <p><strong>Summary:</strong> {selectedNode?.data.subtitle ?? "Not available yet"}</p>
        <p><strong>Review status:</strong> {reviewDecision === "pending" ? "Pending review" : reviewDecision === "accepted" ? "Accepted" : "Changes requested"}</p>
        <div className="quick-actions">
          <Button variant="secondary" onClick={onToggleRaw}>
            {showRawNodeOutput ? "Hide raw output" : "Show raw output"}
          </Button>
          <Button variant="ghost" onClick={onOpenDiff}>
            Open diff review
          </Button>
        </div>
        {showRawNodeOutput ? (
          <pre className="raw-output" aria-label="Node raw output">
            {nodeRawOutput || "No raw output is available for this node yet."}
          </pre>
        ) : null}
      </div>
    </aside>
  );
}
