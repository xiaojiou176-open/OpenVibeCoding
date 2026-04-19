import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
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
  const isZh = detectPreferredUiLocale() === "zh-CN";
  return (
    <aside className="node-drawer" aria-label={isZh ? "节点详情抽屉" : "Node detail drawer"}>
      <header className="node-drawer-header">
        <h2>{isZh ? "节点详情" : "Node Details"} · {selectedNode?.data.label ?? selectedNodeId}</h2>
        <Button variant="icon" onClick={onClose} aria-label={isZh ? "关闭节点详情" : "Close node details"}>
          ×
        </Button>
      </header>
      <div className="node-drawer-content">
        <p><strong>{isZh ? "角色：" : "Role:"}</strong> {selectedNode?.data.role ?? (isZh ? "未知" : "Unknown")}</p>
        <p><strong>{isZh ? "状态：" : "Status:"}</strong> {selectedNode?.data.status ?? (isZh ? "未知" : "unknown")}</p>
        <p><strong>{isZh ? "摘要：" : "Summary:"}</strong> {selectedNode?.data.subtitle ?? (isZh ? "暂未提供" : "Not available yet")}</p>
        <p><strong>{isZh ? "审查状态：" : "Review status:"}</strong> {reviewDecision === "pending" ? (isZh ? "待审查" : "Pending review") : reviewDecision === "accepted" ? (isZh ? "已接受" : "Accepted") : (isZh ? "要求修改" : "Changes requested")}</p>
        <div className="quick-actions">
          <Button variant="secondary" onClick={onToggleRaw}>
            {showRawNodeOutput ? (isZh ? "隐藏原始输出" : "Hide raw output") : (isZh ? "显示原始输出" : "Show raw output")}
          </Button>
          <Button variant="ghost" onClick={onOpenDiff}>
            {isZh ? "打开 Diff 审查" : "Open diff review"}
          </Button>
        </div>
        {showRawNodeOutput ? (
          <pre className="raw-output" aria-label={isZh ? "节点原始输出" : "Node raw output"}>
            {nodeRawOutput || (isZh ? "当前节点还没有原始输出。" : "No raw output is available for this node yet.")}
          </pre>
        ) : null}
      </div>
    </aside>
  );
}
