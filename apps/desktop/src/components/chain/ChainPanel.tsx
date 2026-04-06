import {
  Background,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { RefObject } from "react";
import { Button } from "../ui/Button";
import { nodeIcon, type ChainNodeData } from "../../lib/desktopUi";

type ChainPanelProps = {
  chainPanelRef: RefObject<HTMLElement | null>;
  chainDisplayMode: "compact" | "detail";
  setChainDisplayMode: (mode: "compact" | "detail") => void;
  focusChainMode: () => void;
  nodes: Node<ChainNodeData>[];
  edges: Edge[];
  onNodeClick: NodeMouseHandler;
  onNodeDoubleClick: NodeMouseHandler;
  selectedNodeId: string;
};

export function ChainPanel({
  chainPanelRef,
  chainDisplayMode,
  setChainDisplayMode,
  focusChainMode,
  nodes,
  edges,
  onNodeClick,
  onNodeDoubleClick,
  selectedNodeId
}: ChainPanelProps) {
  return (
    <section ref={chainPanelRef} className="chain-panel" aria-label="Command Chain panel" tabIndex={-1}>
      <header className="chain-toolbar">
        <h2>Command Chain</h2>
        <div className="quick-actions">
          <Button
          variant={chainDisplayMode === "compact" ? "primary" : "secondary"}
          onClick={() => setChainDisplayMode("compact")}
        >
            Compact view
          </Button>
          <Button
          variant={chainDisplayMode === "detail" ? "primary" : "secondary"}
          onClick={() => setChainDisplayMode("detail")}
        >
            Detailed view
          </Button>
          <Button variant="secondary" onClick={focusChainMode}>
            Chain first
          </Button>
        </div>
      </header>
      <div className={`chain-canvas ${chainDisplayMode === "compact" ? "is-compact" : ""}`.trim()}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          minZoom={0.5}
          maxZoom={1.5}
          onNodeClick={onNodeClick}
          onNodeDoubleClick={onNodeDoubleClick}
          proOptions={{ hideAttribution: true }}
        >
          <MiniMap zoomable pannable />
          <Background gap={16} size={1} color="var(--chain-grid-color)" />
        </ReactFlow>
      </div>
      <ul className="chain-legend" aria-label="Node status legend">
        {nodes.map((node) => (
          <li key={node.id} className={selectedNodeId === node.id ? "is-active" : ""}>
            {nodeIcon(node.data.role)}
            <div>
              <strong>{node.data.label}</strong>
              <span>{node.data.subtitle || ""}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
