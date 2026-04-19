import type { CSSProperties, ReactNode } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
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
    id: "openvibecoding-main",
    repo: "OpenVibeCoding",
    branch: "main",
    path: "current checkout",
    activeAgents: 3
  },
  {
    id: "openvibecoding-feature",
    repo: "OpenVibeCoding",
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

function currentUiLocale(): UiLocale {
  return detectPreferredUiLocale() as UiLocale;
}

export function pmPhasesForLocale(locale: UiLocale = currentUiLocale()): string[] {
  if (locale === "zh-CN") {
    return [
      "理解需求中...",
      "继续深挖中...",
      "调研中...",
      "起草方案中...",
      "等待 TL 分析中...",
      "汇总结果中...",
    ];
  }
  return [...PM_PHASES];
}

export function createSeedTimeline(sessionId: string): ChatMessage[] {
  const isZh = currentUiLocale() === "zh-CN";
  return [
    {
      id: `${sessionId}-intro`,
      role: "pm",
      content: isZh
        ? "OpenVibeCoding Command Tower PM 已就绪。告诉我目标，我会去协调 TL 和各条工程执行线。"
        : "OpenVibeCoding Command Tower PM is ready. Tell me the goal and I will coordinate the TL and engineering agents.",
      embeds: [
        {
          id: `${sessionId}-decision-bootstrap`,
          kind: "decision",
          linkedNodeId: "pm",
          title: isZh ? "决策：执行模式" : "Decision: execution mode",
          description: isZh ? "选择严格验收，或更快探索。" : "Choose strict acceptance or faster exploration.",
          selected: "strict",
          options: [
            {
              id: "strict",
              title: isZh ? "严格验收" : "Strict acceptance",
              summary: isZh ? "把门禁和审计链路端到端保留下来" : "Keep gates and the audit chain in place end to end",
              risk: isZh ? "会稍微慢一些" : "A little slower",
              recommended: true
            },
            {
              id: "fast",
              title: isZh ? "快速探索" : "Fast exploration",
              summary: isZh ? "先验证方向，再补完整门禁路径" : "Validate direction first, then add the full gate path",
              risk: isZh ? "返工风险更高" : "Higher rework risk"
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
  const isZh = currentUiLocale() === "zh-CN";
  if (embed.kind === "decision") {
    return (
      <section key={embed.id} className="embed-card decision-card" aria-label={isZh ? "决策卡片" : "Decision card"}>
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
                <p className="decision-risk">{isZh ? "风险：" : "Risk: "} {option.risk}</p>
                {option.recommended ? <span className="status-badge status-running">{isZh ? "推荐" : "Recommended"}</span> : null}
                <Button
                  variant={selected ? "primary" : "secondary"}
                  onClick={() => chooseDecision(message.id, embed.id, option.id)}
                >
                  {selected ? (isZh ? "已选中" : "Selected") : (isZh ? "选择" : "Choose")}
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
      <section key={embed.id} className="embed-card delegation-card" aria-label={isZh ? "委派卡片" : "Delegation card"}>
        <h2>{embed.title}</h2>
        <p>
          <strong>{isZh ? "任务：" : "Task:"}</strong>
          {embed.task}
        </p>
        <p>
          <strong>{isZh ? "计划：" : "Plan:"}</strong>
          {embed.plan}
        </p>
        <p>
          <strong>{isZh ? "状态：" : "Status:"}</strong>
          {embed.status}
        </p>
      </section>
    );
  }

  if (embed.kind === "progress") {
    return (
      <section key={embed.id} className="embed-card progress-card" aria-label={isZh ? "进度卡片" : "Progress card"}>
        <h2>{embed.title}</h2>
        <ul className="embed-list">
          {embed.updates.map((item) => (
            <li key={`${embed.id}-${item.actor}`}>
              <strong>{item.actor}</strong>
              <span>{item.detail}</span>
              <span
                className={`status-badge status-${item.state === "done" ? "pass" : item.state === "working" ? "running" : "warning"}`}
              >
                {item.state === "done" ? (isZh ? "已完成" : "Done") : item.state === "working" ? (isZh ? "进行中" : "In progress") : (isZh ? "等待中" : "Waiting")}
              </span>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  if (embed.kind === "report") {
    return (
      <section key={embed.id} className="embed-card report-card" aria-label={isZh ? "结果报告卡片" : "Result report card"}>
        <h2>{embed.title}</h2>
        <p>{embed.summary}</p>
        <ul className="file-list" aria-label={isZh ? "变更文件列表" : "Changed files list"}>
          {embed.files.map((file) => (
            <li key={file}>{file}</li>
          ))}
        </ul>
        <p className="report-tests">{embed.tests}</p>
        <div className="embed-actions">
          <Button variant="primary" onClick={() => reportActions?.onAccept?.(embed.id)}>{isZh ? "接受并合并" : "Accept and merge"}</Button>
          <Button variant="secondary" onClick={() => reportActions?.onRework?.(embed.id)}>{isZh ? "要求修改" : "Request changes"}</Button>
          <Button variant="ghost" onClick={() => reportActions?.onViewDiff?.(embed.id)}>{isZh ? "查看完整 diff" : "View full diff"}</Button>
        </div>
      </section>
    );
  }

  return (
    <section
      key={embed.id}
      className={`embed-card alert-card ${embed.level === "critical" ? "is-critical" : ""}`.trim()}
      aria-label={isZh ? "告警卡片" : "Alert card"}
    >
      <h2>{embed.title}</h2>
      <p>{embed.description}</p>
      <p>{embed.action}</p>
    </section>
  );
}
