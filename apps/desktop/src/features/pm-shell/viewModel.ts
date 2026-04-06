import type { Edge, Node } from "@xyflow/react";
import type { DesktopAlert } from "../../lib/api";
import { buildNodeStyle, type ChainNodeData, type ChainStatus } from "../../lib/desktopUi";

export function getStarterPrompts(): string[] {
  return [
    "Help me break this request into an execution plan with acceptance criteria.",
    "Check the current branch for risk areas and list the highest-priority fixes first.",
    "Turn the current session into a smallest-possible executable change list.",
  ];
}

export function buildComposerPlaceholder(params: {
  hasWorkspace: boolean;
  activeSessionId: string;
  hasActiveGeneration: boolean;
  hasPendingDecision: boolean;
  activeTimelineLength: number;
}): string {
  const { hasWorkspace, activeSessionId, hasActiveGeneration, hasPendingDecision, activeTimelineLength } = params;
  if (!hasWorkspace) return "Choose a workspace before starting the conversation.";
  if (!activeSessionId) return "Click \"Create first session in desktop\" first. If that fails, open Dashboard /pm and create it manually.";
  if (hasActiveGeneration) return "Ask for progress or give the PM another instruction...";
  if (hasPendingDecision) return "Resolve the decision card above, or add more constraints before continuing...";
  if (activeTimelineLength === 0) return "Tell the PM what you want to get done...";
  return "After review, tell the PM to accept and merge or continue revising.";
}

export function buildSendDisabledReason(params: {
  hasWorkspace: boolean;
  activeSessionId: string;
  isOffline: boolean;
  hasActiveGeneration: boolean;
  composerOverLimit: boolean;
  composerInput: string;
  composerMaxChars: number;
}): string | null {
  const {
    hasWorkspace,
    activeSessionId,
    isOffline,
    hasActiveGeneration,
    composerOverLimit,
    composerInput,
    composerMaxChars,
  } = params;
  if (!hasWorkspace) return "Choose a workspace first.";
  if (!activeSessionId) return "Click \"Create first session in desktop\" first. If that fails, open Dashboard /pm and create it manually.";
  if (isOffline) return "Reconnect before sending a message.";
  if (hasActiveGeneration) return "Stop the current generation or wait for it to finish before sending another message.";
  if (composerOverLimit) return `Shorten the input to ${composerMaxChars} characters or fewer before sending.`;
  if (composerInput.trim().length === 0) return "Enter a message before sending.";
  return null;
}

export function buildPmChainGraph(params: {
  alerts: DesktopAlert[];
  activeSessionGenerating: boolean;
  phaseText: string;
  selectedNodeId: string;
}): { nodes: Node<ChainNodeData>[]; edges: Edge[] } {
  const { alerts, activeSessionGenerating, phaseText, selectedNodeId } = params;
  const hasCritical = alerts.some((alert) => String(alert.severity || "").toLowerCase() === "critical");
  const hasWarning = alerts.some((alert) => String(alert.severity || "").toLowerCase() === "warning");
  const pm: ChainStatus = activeSessionGenerating ? "working" : "done";
  const tl: ChainStatus = activeSessionGenerating ? "working" : "done";
  const w: ChainStatus = activeSessionGenerating ? "working" : "done";
  const rv: ChainStatus = hasCritical ? "failed" : activeSessionGenerating ? "waiting" : "done";
  const gate: ChainStatus = hasCritical ? "failed" : hasWarning ? "waiting" : "done";

  const nodes: Node<ChainNodeData>[] = [
    { id: "pm", position: { x: 20, y: 40 }, data: { label: "PM", role: "PM", status: pm, subtitle: activeSessionGenerating ? phaseText : "Standing by" }, style: buildNodeStyle(pm, selectedNodeId === "pm") },
    { id: "tl", position: { x: 220, y: 40 }, data: { label: "TL", role: "TL", status: tl, subtitle: "Task breakdown" }, style: buildNodeStyle(tl, selectedNodeId === "tl") },
    { id: "w1", position: { x: 440, y: -10 }, data: { label: "B-1", role: "Worker", status: w, subtitle: "Backend" }, style: buildNodeStyle(w, selectedNodeId === "w1") },
    { id: "w2", position: { x: 440, y: 95 }, data: { label: "F-1", role: "Worker", status: w, subtitle: "Frontend" }, style: buildNodeStyle(w, selectedNodeId === "w2") },
    { id: "rv", position: { x: 640, y: 40 }, data: { label: "RV", role: "Reviewer", status: rv, subtitle: "Diff Gate" }, style: buildNodeStyle(rv, selectedNodeId === "rv") },
    { id: "gate", position: { x: 830, y: 40 }, data: { label: "Gate", role: "Test", status: gate, subtitle: hasCritical ? "Failed" : "Passed" }, style: { ...buildNodeStyle(gate, selectedNodeId === "gate"), transform: "rotate(45deg)", width: 76, height: 76, borderRadius: 10 } },
  ];
  const activeStroke = "var(--chain-edge-active)";
  const doneStroke = "var(--chain-edge-done)";
  const failedStroke = "var(--chain-edge-failed)";
  const edges: Edge[] = [
    { id: "pm-tl", source: "pm", target: "tl", animated: activeSessionGenerating, style: { stroke: activeSessionGenerating ? activeStroke : doneStroke, strokeWidth: 2 } },
    { id: "tl-w1", source: "tl", target: "w1", animated: activeSessionGenerating, style: { stroke: activeSessionGenerating ? activeStroke : doneStroke, strokeWidth: 2 } },
    { id: "tl-w2", source: "tl", target: "w2", animated: activeSessionGenerating, style: { stroke: activeSessionGenerating ? activeStroke : doneStroke, strokeWidth: 2 } },
    { id: "w1-rv", source: "w1", target: "rv", animated: activeSessionGenerating, style: { stroke: activeSessionGenerating ? activeStroke : doneStroke, strokeWidth: 1.6 } },
    { id: "w2-rv", source: "w2", target: "rv", animated: activeSessionGenerating, style: { stroke: activeSessionGenerating ? activeStroke : doneStroke, strokeWidth: 1.6 } },
    { id: "rv-gate", source: "rv", target: "gate", animated: activeSessionGenerating, style: { stroke: hasCritical ? failedStroke : activeSessionGenerating ? activeStroke : doneStroke, strokeWidth: 2 } },
  ];
  return { nodes, edges };
}
