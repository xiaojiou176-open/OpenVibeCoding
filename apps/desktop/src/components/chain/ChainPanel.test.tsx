import { createRef, type ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import { ChainPanel } from "./ChainPanel";
import type { ChainNodeData } from "../../lib/desktopUi";

vi.mock("@xyflow/react", () => {
  return {
    ReactFlow: ({ children }: { children?: ReactNode }) => <div data-testid="mock-react-flow">{children}</div>,
    MiniMap: () => <div data-testid="mock-mini-map" />,
    Background: () => <div data-testid="mock-background" />
  };
});

function buildNodes(): Node<ChainNodeData>[] {
  return [
    {
      id: "n1",
      position: { x: 0, y: 0 },
      data: { label: "PM", role: "PM", status: "working", subtitle: "分析中" }
    },
    {
      id: "n2",
      position: { x: 10, y: 10 },
      data: { label: "TL", role: "TL", status: "waiting" }
    }
  ] as Node<ChainNodeData>[];
}

describe("ChainPanel", () => {
  it("toggles compact/detail modes and preserves chain focus action", () => {
    const setChainDisplayMode = vi.fn();
    const focusChainMode = vi.fn();
    const onNodeClick = vi.fn();
    const onNodeDoubleClick = vi.fn();
    const nodes = buildNodes();
    const edges = [{ id: "e1", source: "n1", target: "n2" }] as Edge[];

    render(
      <ChainPanel
        chainPanelRef={createRef<HTMLElement>()}
        chainDisplayMode="compact"
        setChainDisplayMode={setChainDisplayMode}
        focusChainMode={focusChainMode}
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        selectedNodeId="n1"
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Compact view" }));
    fireEvent.click(screen.getByRole("button", { name: "Detailed view" }));
    fireEvent.click(screen.getByRole("button", { name: "Chain first" }));

    expect(setChainDisplayMode).toHaveBeenCalledWith("compact");
    expect(setChainDisplayMode).toHaveBeenCalledWith("detail");
    expect(focusChainMode).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("mock-react-flow")).toBeInTheDocument();
    expect(screen.getByTestId("mock-mini-map")).toBeInTheDocument();
    expect(screen.getByTestId("mock-background")).toBeInTheDocument();
  });

  it("renders legend entries with selected state and empty subtitle fallback", () => {
    const nodes = buildNodes();
    render(
      <ChainPanel
        chainPanelRef={createRef<HTMLElement>()}
        chainDisplayMode="detail"
        setChainDisplayMode={vi.fn()}
        focusChainMode={vi.fn()}
        nodes={nodes}
        edges={[]}
        onNodeClick={vi.fn()}
        onNodeDoubleClick={vi.fn()}
        selectedNodeId="n1"
      />
    );

    const legend = screen.getByLabelText("Node status legend");
    const items = legend.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveClass("is-active");
    expect(items[1]).not.toHaveClass("is-active");
    expect(screen.getByText("分析中")).toBeInTheDocument();
    const subtitleSpans = legend.querySelectorAll("span");
    expect(subtitleSpans[1]?.textContent).toBe("");
  });
});
