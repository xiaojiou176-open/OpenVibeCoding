import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockCookies } = vi.hoisted(() => ({
  mockCookies: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/headers", () => ({
  cookies: mockCookies,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: vi.fn(),
  }),
}));

vi.mock("../lib/api", () => ({
  fetchRuns: vi.fn(),
  fetchRun: vi.fn(),
  fetchArtifact: vi.fn(),
  fetchReports: vi.fn(),
  mutationExecutionCapability: vi.fn(() => ({ executable: false, operatorRole: null })),
  enqueueRunQueue: vi.fn(),
  runNextQueue: vi.fn(),
}));

import PlannerPage from "../app/planner/page";
import { fetchArtifact, fetchReports, fetchRun, fetchRuns } from "../lib/api";

describe("planner page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCookies.mockResolvedValue({
      get: () => undefined,
      toString: () => "",
    });
    vi.mocked(fetchRuns).mockResolvedValue([
      { run_id: "run-plan-1", task_id: "task-plan-1", status: "SUCCESS" },
    ] as never);
    vi.mocked(fetchRun).mockResolvedValue({
      run_id: "run-plan-1",
      task_id: "task-plan-1",
      status: "SUCCESS",
      manifest: {
        artifacts: [
          { name: "planning_wave_plan", path: "artifacts/planning_wave_plan.json" },
          { name: "planning_worker_prompt_contracts", path: "artifacts/planning_worker_prompt_contracts.json" },
          { name: "planning_unblock_tasks", path: "artifacts/planning_unblock_tasks.json" },
        ],
      },
    } as never);
    vi.mocked(fetchArtifact).mockImplementation(async (_runId: string, name: string) => {
      if (name === "planning_wave_plan.json") {
        return {
          name,
          data: {
            objective: "Ship one planning bridge",
            worker_count: 3,
            wake_policy_ref: "policies/control_plane_runtime_policy.json#/wake_policy",
          },
        } as never;
      }
      if (name === "planning_worker_prompt_contracts.json") {
        return {
          name,
          data: [{ prompt_contract_id: "worker-1" }, { prompt_contract_id: "worker-2" }],
        } as never;
      }
      return {
        name,
        data: [{ unblock_task_id: "unblock-1" }],
      } as never;
    });
    vi.mocked(fetchReports).mockResolvedValue([
      {
        name: "completion_governance_report.json",
        data: {
          overall_verdict: "continue_same_session",
          continuation_decision: { selected_action: "reply_auditor_reprompt_and_continue_same_session" },
        },
      },
    ] as never);
  });

  it("renders a triage-first planner desk from planning artifacts", async () => {
    render(await PlannerPage());

    expect(screen.getByRole("heading", { name: "Planner desk" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Planner triage queue" })).toBeInTheDocument();
    expect(screen.getAllByText("Ship one planning bridge")).toHaveLength(2);
    expect(screen.getAllByText(/Wake policy:/)).toHaveLength(2);
    expect(screen.getByText("Missing worker prompt contract")).toBeInTheDocument();
    expect(screen.getByText("Planned workers: 3 · Worker contracts: 2 · Unblock tasks: 1")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open PM intake" })[0]).toHaveAttribute("href", "/pm");
    expect(screen.getAllByRole("link", { name: "Open Command Tower" })[0]).toHaveAttribute("href", "/command-tower");
    expect(screen.getAllByRole("link", { name: "Open Workflow Cases" })[0]).toHaveAttribute("href", "/workflows");
    expect(screen.getByRole("link", { name: "run-plan-1" })).toHaveAttribute("href", "/runs/run-plan-1");
    expect(screen.getAllByRole("button", { name: "Queue latest run contract" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Run next queued task" })).toHaveLength(2);
    expect(screen.getByText("Planning inspection archive")).toBeInTheDocument();
  });

  it("renders the launch-stage empty planner desk when no planning artifacts exist", async () => {
    vi.mocked(fetchRuns).mockResolvedValue([] as never);

    render(await PlannerPage());

    expect(screen.getByText("Seed the first planning wave")).toBeInTheDocument();
    expect(screen.getByText("Planner launch checklist")).toBeInTheDocument();
    expect(screen.getByText("Start the first planning wave, then come back for real triage.")).toBeInTheDocument();
    expect(screen.getByText("Lock the objective and the done signal")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open PM intake" })).toHaveAttribute("href", "/pm");
    expect(screen.getByRole("link", { name: "Open Command Tower" })).toHaveAttribute("href", "/command-tower");
    expect(screen.getByRole("link", { name: "Open Workflow Cases" })).toHaveAttribute("href", "/workflows");
  });

  it("surfaces continuation-selected waves as ready-to-resume planning rows", async () => {
    vi.mocked(fetchArtifact).mockImplementation(async (_runId: string, name: string) => {
      if (name === "planning_wave_plan.json") {
        return {
          name,
          data: {
            objective: "Resume the continuation lane",
            worker_count: 1,
            wake_policy_ref: "policies/control_plane_runtime_policy.json#/wake_policy",
          },
        } as never;
      }
      if (name === "planning_worker_prompt_contracts.json") {
        return {
          name,
          data: [{ prompt_contract_id: "worker-1" }],
        } as never;
      }
      return {
        name,
        data: [],
      } as never;
    });
    vi.mocked(fetchReports).mockResolvedValue([
      {
        name: "completion_governance_report.json",
        data: {
          overall_verdict: "continue_same_session",
          continuation_decision: { selected_action: "continue_same_session" },
        },
      },
    ] as never);

    render(await PlannerPage());

    expect(screen.getByText("Priority queue: Continuation already selected: continue_same_session")).toBeInTheDocument();
    expect(screen.getAllByText("Resume the continuation lane").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open run detail" })[0]).toHaveAttribute("href", "/runs/run-plan-1");
  });
});
