import type { CSSProperties, ReactNode } from "react";
import {
  Compass,
  FlaskConical,
  SearchCheck,
  Shield,
  Telescope,
  Wrench
} from "lucide-react";
import { Button } from "../components/ui/Button";

export type LayoutMode = "dialog" | "split" | "chain" | "focus";
export type ChainStatus = "idle" | "waiting" | "working" | "done" | "failed";
export type ChatRole = "user" | "pm";

export type DecisionOption = {
  id: string;
  title: string;
  summary: string;
  risk: string;
  recommended?: boolean;
};

export type ChatEmbed =
  | {
      id: string;
      kind: "decision";
      linkedNodeId: "pm";
      title: string;
      description: string;
      selected?: string;
      options: DecisionOption[];
    }
  | {
      id: string;
      kind: "delegation";
      linkedNodeId: "tl";
      title: string;
      task: string;
      plan: string;
      status: string;
    }
  | {
      id: string;
      kind: "progress";
      linkedNodeId: "w1" | "w2" | "rv";
      title: string;
      updates: Array<{ actor: string; detail: string; state: "pending" | "working" | "done" }>;
    }
  | {
      id: string;
      kind: "report";
      linkedNodeId: "rv";
      title: string;
      summary: string;
      files: string[];
      tests: string;
    }
  | {
      id: string;
      kind: "alert";
      linkedNodeId: "gate";
      title: string;
      level: "warning" | "critical";
      description: string;
      action: string;
    };

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  embeds?: ChatEmbed[];
};

export type Workspace = {
  id: string;
  repo: string;
  branch: string;
  path: string;
  activeAgents: number;
};

export type ChainNodeData = {
  label: string;
  role: string;
  status: ChainStatus;
  subtitle?: string;
};

export const WORKSPACES: Workspace[] = [
  {
    id: "cortexpilot-main",
    repo: "CortexPilot",
    branch: "main",
    path: "current checkout",
    activeAgents: 3
  },
  {
    id: "cortexpilot-feature",
    repo: "CortexPilot",
    branch: "feature/pm-chat",
    path: "current checkout",
    activeAgents: 2
  }
];

export const PM_PHASES = [
  "Understanding the request...",
  "Digging deeper...",
  "Researching...",
  "Drafting the plan...",
  "Waiting for TL analysis...",
  "Summarizing results..."
] as const;

export function createSeedTimeline(sessionId: string): ChatMessage[] {
  return [
    {
      id: `${sessionId}-intro`,
      role: "pm",
      content: "CortexPilot Command Tower PM is ready. Tell me the goal and I will coordinate the TL and engineering agents.",
      embeds: [
        {
          id: `${sessionId}-decision-bootstrap`,
          kind: "decision",
          linkedNodeId: "pm",
          title: "Decision: execution mode",
          description: "Choose strict acceptance or faster exploration.",
          selected: "strict",
          options: [
            {
              id: "strict",
              title: "Strict acceptance",
              summary: "Keep gates and the audit chain in place end to end",
              risk: "A little slower",
              recommended: true
            },
            {
              id: "fast",
              title: "Fast exploration",
              summary: "Validate direction first, then add the full gate path",
              risk: "Higher rework risk"
            }
          ]
        }
      ]
    }
  ];
}

export function nextLayoutMode(current: LayoutMode): LayoutMode {
  if (current === "dialog") {
    return "split";
  }
  return "dialog";
}

export function buildNodeStyle(status: ChainStatus, selected: boolean): CSSProperties {
  if (status === "working") {
    return {
      border: "2px solid var(--chain-node-working-border)",
      background: "var(--chain-node-working-surface)",
      boxShadow: selected ? "0 0 0 3px var(--chain-node-working-shadow)" : "none"
    };
  }
  if (status === "done") {
    return {
      border: "1.5px solid var(--chain-node-done-border)",
      background: "var(--chain-node-done-surface)",
      boxShadow: selected ? "0 0 0 3px var(--chain-node-done-shadow)" : "none"
    };
  }
  if (status === "failed") {
    return {
      border: "2px solid var(--chain-node-failed-border)",
      background: "var(--chain-node-failed-surface)",
      boxShadow: selected ? "0 0 0 3px var(--chain-node-failed-shadow)" : "none"
    };
  }
  if (status === "waiting") {
    return {
      border: "1.5px dashed var(--chain-node-waiting-border)",
      background: "var(--chain-node-waiting-surface)",
      boxShadow: selected ? "0 0 0 3px var(--chain-node-waiting-shadow)" : "none"
    };
  }
  return {
    border: "1.5px solid var(--chain-node-idle-border)",
    background: "var(--chain-node-idle-surface)",
    boxShadow: selected ? "0 0 0 3px var(--chain-node-idle-shadow)" : "none"
  };
}

export function nodeIcon(role: string): ReactNode {
  if (role === "PM") return <Shield size={16} aria-hidden="true" />;
  if (role === "TL") return <Compass size={16} aria-hidden="true" />;
  if (role === "Worker") return <Wrench size={16} aria-hidden="true" />;
  if (role === "Reviewer") return <SearchCheck size={16} aria-hidden="true" />;
  if (role === "Test") return <FlaskConical size={16} aria-hidden="true" />;
  return <Telescope size={16} aria-hidden="true" />;
}

export function renderChatEmbed(
  message: ChatMessage,
  embed: ChatEmbed,
  chooseDecision: (messageId: string, embedId: string, optionId: string) => void,
  reportActions?: {
    onAccept?: (embedId: string) => void;
    onRework?: (embedId: string) => void;
    onViewDiff?: (embedId: string) => void;
  }
) {
  if (embed.kind === "decision") {
    return (
      <section key={embed.id} className="embed-card decision-card" aria-label="Decision card">
        <header>
          <h2>{embed.title}</h2>
          <p>{embed.description}</p>
        </header>
        <div className="decision-grid">
          {embed.options.map((option) => {
            const selected = embed.selected === option.id;
            return (
              <article key={option.id} className={`decision-option ${selected ? "is-selected" : ""}`.trim()}>
                <p className="decision-title">{option.title}</p>
                <p>{option.summary}</p>
                <p className="decision-risk">Risk: {option.risk}</p>
                {option.recommended ? <span className="status-badge status-running">Recommended</span> : null}
                <Button
                  variant={selected ? "primary" : "secondary"}
                  onClick={() => chooseDecision(message.id, embed.id, option.id)}
                >
                  {selected ? "Selected" : "Choose"}
                </Button>
              </article>
            );
          })}
        </div>
      </section>
    );
  }

  if (embed.kind === "delegation") {
    return (
      <section key={embed.id} className="embed-card delegation-card" aria-label="Delegation card">
        <h2>{embed.title}</h2>
        <p>
          <strong>Task:</strong>
          {embed.task}
        </p>
        <p>
          <strong>Plan:</strong>
          {embed.plan}
        </p>
        <p>
          <strong>Status:</strong>
          {embed.status}
        </p>
      </section>
    );
  }

  if (embed.kind === "progress") {
    return (
      <section key={embed.id} className="embed-card progress-card" aria-label="Progress card">
        <h2>{embed.title}</h2>
        <ul className="embed-list">
          {embed.updates.map((item) => (
            <li key={`${embed.id}-${item.actor}`}>
              <strong>{item.actor}</strong>
              <span>{item.detail}</span>
              <span
                className={`status-badge status-${item.state === "done" ? "pass" : item.state === "working" ? "running" : "warning"}`}
              >
                {item.state === "done" ? "Done" : item.state === "working" ? "In progress" : "Waiting"}
              </span>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  if (embed.kind === "report") {
    return (
      <section key={embed.id} className="embed-card report-card" aria-label="Result report card">
        <h2>{embed.title}</h2>
        <p>{embed.summary}</p>
        <ul className="file-list" aria-label="Changed files list">
          {embed.files.map((file) => (
            <li key={file}>{file}</li>
          ))}
        </ul>
        <p className="report-tests">{embed.tests}</p>
        <div className="embed-actions">
          <Button variant="primary" onClick={() => reportActions?.onAccept?.(embed.id)}>Accept and merge</Button>
          <Button variant="secondary" onClick={() => reportActions?.onRework?.(embed.id)}>Request changes</Button>
          <Button variant="ghost" onClick={() => reportActions?.onViewDiff?.(embed.id)}>View full diff</Button>
        </div>
      </section>
    );
  }

  return (
    <section
      key={embed.id}
      className={`embed-card alert-card ${embed.level === "critical" ? "is-critical" : ""}`.trim()}
      aria-label="Alert card"
    >
      <h2>{embed.title}</h2>
      <p>{embed.description}</p>
      <p>{embed.action}</p>
    </section>
  );
}
