import type { PmSessionConversationGraphPayload } from "../../lib/types";
import { Badge, type BadgeVariant } from "../ui/badge";
import { Card } from "../ui/card";

type ConversationGraphProps = {
  graph: PmSessionConversationGraphPayload;
};

type NodeTraffic = {
  node: string;
  inbound: number;
  outbound: number;
  loops: number;
  runCount: number;
  latestTs: string;
};

type EdgeSummary = {
  path: string;
  from: string;
  to: string;
  count: number;
  runs: string[];
  latestTs: string;
};

function roleLabel(role: string | undefined): string {
  return String(role || "").trim() || "-";
}

function nodeBadgeVariant(node: NodeTraffic): BadgeVariant {
  if (node.loops > 0 || node.inbound + node.outbound >= 6) {
    return "warning";
  }
  if (node.inbound + node.outbound >= 3) {
    return "running";
  }
  return "default";
}

function toLocalTs(rawTs: string): string {
  if (!rawTs) {
    return "-";
  }
  const parsed = Date.parse(rawTs);
  if (Number.isNaN(parsed)) {
    return rawTs;
  }
  return new Date(parsed).toLocaleString();
}

function buildNodeTraffic(graph: PmSessionConversationGraphPayload): NodeTraffic[] {
  const nodeMap = new Map<string, NodeTraffic>();
  for (const node of graph.nodes) {
    const label = roleLabel(node);
    if (!nodeMap.has(label)) {
      nodeMap.set(label, {
        node: label,
        inbound: 0,
        outbound: 0,
        loops: 0,
        runCount: 0,
        latestTs: "",
      });
    }
  }

  for (const edge of graph.edges) {
    const from = roleLabel(edge.from_role);
    const to = roleLabel(edge.to_role);
    const ts = edge.ts || "";
    const runId = String(edge.run_id || "").trim();

    if (!nodeMap.has(from)) {
      nodeMap.set(from, { node: from, inbound: 0, outbound: 0, loops: 0, runCount: 0, latestTs: "" });
    }
    if (!nodeMap.has(to)) {
      nodeMap.set(to, { node: to, inbound: 0, outbound: 0, loops: 0, runCount: 0, latestTs: "" });
    }

    const fromNode = nodeMap.get(from);
    const toNode = nodeMap.get(to);
    if (!fromNode || !toNode) {
      continue;
    }

    fromNode.outbound += 1;
    toNode.inbound += 1;
    if (from === to) {
      fromNode.loops += 1;
    }

    if (runId) {
      fromNode.runCount += 1;
      if (from !== to) {
        toNode.runCount += 1;
      }
    }
    if (ts && (!fromNode.latestTs || ts > fromNode.latestTs)) {
      fromNode.latestTs = ts;
    }
    if (ts && (!toNode.latestTs || ts > toNode.latestTs)) {
      toNode.latestTs = ts;
    }
  }

  return Array.from(nodeMap.values()).sort((left, right) => {
    const degreeRight = right.inbound + right.outbound;
    const degreeLeft = left.inbound + left.outbound;
    if (degreeRight === degreeLeft) {
      return left.node.localeCompare(right.node);
    }
    return degreeRight - degreeLeft;
  });
}

function buildEdgeSummary(graph: PmSessionConversationGraphPayload): EdgeSummary[] {
  const summary = new Map<string, EdgeSummary>();
  for (const edge of graph.edges) {
    const from = roleLabel(edge.from_role);
    const to = roleLabel(edge.to_role);
    const path = `${from} → ${to}`;
    const ts = edge.ts || "";
    const runId = String(edge.run_id || "").trim();
    if (!summary.has(path)) {
      summary.set(path, {
        path,
        from,
        to,
        count: 0,
        runs: [],
        latestTs: "",
      });
    }
    const item = summary.get(path);
    if (!item) {
      continue;
    }
    item.count += edge.count && edge.count > 0 ? edge.count : 1;
    if (runId && !item.runs.includes(runId)) {
      item.runs.push(runId);
    }
    if (ts && (!item.latestTs || ts > item.latestTs)) {
      item.latestTs = ts;
    }
  }

  return Array.from(summary.values()).sort((left, right) => {
    if (right.count === left.count) {
      return left.path.localeCompare(right.path);
    }
    return right.count - left.count;
  });
}

export default function ConversationGraph({ graph }: ConversationGraphProps) {
  const nodeTraffic = buildNodeTraffic(graph);
  const edgeSummary = buildEdgeSummary(graph);
  const hottestEdge = edgeSummary[0];
  const totalTransitions = edgeSummary.reduce((acc, edge) => acc + edge.count, 0);

  return (
    <section className="app-section">
      <div className="section-header">
        <div>
          <h3>Conversation graph</h3>
          <p>
            Window {graph.window}, nodes {graph.stats.node_count}, edges {graph.stats.edge_count}. Use it to inspect handoff density and the hottest operator paths.
          </p>
        </div>
      </div>

      <Card aria-live="polite">
        <p className="muted">
          Reading tip: start with node traffic (inbound/outbound), then check hot paths. The table lets you trace evidence by run and `event_ref`.
        </p>
        <div className="run-detail-chip-row" role="list" aria-label="Graph summary metrics">
          <Badge>Window {graph.window}</Badge>
          <Badge variant={graph.stats.node_count > 0 ? "running" : "default"}>Nodes {graph.stats.node_count}</Badge>
          <Badge variant={graph.stats.edge_count > 0 ? "running" : "default"}>Edges {graph.stats.edge_count}</Badge>
          <Badge variant={totalTransitions >= 6 ? "warning" : "default"}>
            Traffic {totalTransitions}
          </Badge>
          <Badge variant={hottestEdge ? "warning" : "default"}>
            Hot path {hottestEdge ? `${hottestEdge.path} × ${hottestEdge.count}` : "-"}
          </Badge>
        </div>
      </Card>

      <div className="grid ct-panel-group">
        <Card>
          <div className="section-header section-header--spaced">
            <div>
              <h4>Node traffic</h4>
              <p className="muted">Prioritize nodes with unusual inbound/outbound volume or loops.</p>
            </div>
          </div>
          {nodeTraffic.length === 0 ? (
            <div className="empty-state-stack">
              <span className="muted">No graph nodes yet</span>
              <span className="mono muted">Nodes appear automatically after the session emits handoff events.</span>
            </div>
          ) : (
            <ul aria-label="Node traffic list" className="unstyled-list unstyled-list-grid">
              {nodeTraffic.map((node) => (
                <li key={node.node} className="list-divider">
                  <div className="run-detail-chip-row">
                    <Badge
                      variant={nodeBadgeVariant(node)}
                      title={`In ${node.inbound} / Out ${node.outbound} / Loops ${node.loops} / Runs ${node.runCount}`}
                    >
                      {node.node}
                    </Badge>
                    <Badge>In {node.inbound}</Badge>
                    <Badge>Out {node.outbound}</Badge>
                    <Badge variant={node.loops > 0 ? "warning" : "default"}>Loops {node.loops}</Badge>
                    <Badge>Runs {node.runCount}</Badge>
                  </div>
                  <p className="mono muted run-detail-inline-gap">
                    Latest activity {toLocalTs(node.latestTs)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <div className="section-header section-header--spaced">
            <div>
              <h4>Hot paths</h4>
              <p className="muted">Sorted by handoff count, showing the top 6 paths.</p>
            </div>
          </div>
          {edgeSummary.length === 0 ? (
            <div className="empty-state-stack">
              <span className="muted">No hot paths yet</span>
              <span className="mono muted">There are no role paths to summarize in the current window.</span>
            </div>
          ) : (
            <ol aria-label="Hot path list" className="ordered-list-grid">
              {edgeSummary.slice(0, 6).map((edge) => (
                <li key={edge.path}>
                  <div className="run-detail-chip-row">
                    <Badge variant={edge.count >= 3 ? "warning" : "running"}>
                      {edge.path} × {edge.count}
                    </Badge>
                    <Badge>Runs {edge.runs.length || 0}</Badge>
                  </div>
                  <p className="mono muted run-detail-inline-gap">
                    Latest time {toLocalTs(edge.latestTs)} | runs {edge.runs.join(", ") || "-"}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      <Card variant="table">
        <div className="section-header section-header--spaced">
          <div>
            <h4>Graph details</h4>
            <p className="muted">Each handoff edge is listed so you can trace evidence by run and `event_ref`.</p>
          </div>
        </div>
        <table className="run-table">
          <caption className="sr-only">Session handoff edges, including source role, target role, runs, and timestamps.</caption>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Target</th>
              <th scope="col">Count</th>
              <th scope="col">Run</th>
              <th scope="col">Timestamp</th>
              <th scope="col">Reference</th>
            </tr>
          </thead>
          <tbody>
            {graph.edges.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted">
                  No handoff edges yet
                </td>
              </tr>
            ) : (
              graph.edges.map((edge) => (
                <tr key={`${edge.event_ref}-${edge.ts}`}>
                  <td className="mono">{roleLabel(edge.from_role)}</td>
                  <td className="mono">{roleLabel(edge.to_role)}</td>
                  <td className="mono">{edge.count && edge.count > 0 ? edge.count : 1}</td>
                  <td className="mono">{edge.run_id || "-"}</td>
                  <td className="mono" title={toLocalTs(edge.ts || "")}>
                    {edge.ts || "-"}
                  </td>
                  <td className="mono">{edge.event_ref || "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </section>
  );
}
