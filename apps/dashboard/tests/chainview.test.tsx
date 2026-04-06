import { fireEvent, render, screen, within } from "@testing-library/react";

import ChainView, { pickContextLabel } from "../components/ChainView";

describe("ChainView", () => {
  it("shows empty state when report missing", () => {
    render(<ChainView chainReport={null} chainSpec={null} events={[]} />);
    expect(screen.getByText("No chain report yet")).toBeInTheDocument();
  });

  it("renders steps, policies, and handoffs", () => {
    const chainReport = {
      chain_id: "chain-1",
      status: "SUCCESS",
      steps: [
        {
          index: 0,
          name: "step_1",
          kind: "contract",
          task_id: "t1",
          run_id: "r1",
          status: "FAILED",
          failure_reason: "diff_gate_fail",
        },
      ],
    };
    const chainSpec = {
      steps: [
        {
          name: "step_1",
          depends_on: ["root"],
          exclusive_paths: ["apps/"],
          context_policy: { mode: "summary-only" },
          parallel_group: "group_a",
        },
      ],
    };
    const events = [{ ts: "t1", event: "CHAIN_HANDOFF", context: { from: "root", to: "t1" } }];
    render(<ChainView chainReport={chainReport} chainSpec={chainSpec} events={events} />);

    expect(screen.getByText("chain-1")).toBeInTheDocument();
    expect(screen.getByText(/Steps \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("diff_gate_fail")).toBeInTheDocument();
    expect(screen.getAllByText("root").length).toBeGreaterThan(0);
    expect(screen.getAllByText("t1").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByText("Spec details"));
    expect(screen.getByText("Depends on:")).toBeInTheDocument();
    expect(screen.getByText("group: group_a")).toBeInTheDocument();
    expect(screen.getByText(/summary-only/)).toBeInTheDocument();
  });

  it("renders empty steps and no handoff events", () => {
    const chainReport = { chain_id: "chain-empty", status: "RUNNING", steps: [] };
    render(<ChainView chainReport={chainReport} chainSpec={{ steps: [] }} events={[]} />);

    expect(screen.getByText(/Steps \(0\)/)).toBeInTheDocument();
    expect(screen.getByText("No step records yet")).toBeInTheDocument();
    expect(screen.getByText(/Handoffs \(0\)/)).toBeInTheDocument();
    expect(screen.getByText("No handoff events yet")).toBeInTheDocument();
  });

  it("handles non-array steps and missing spec metadata", () => {
    const chainReport = {
      chain_id: "chain-weird",
      status: "RUNNING",
      steps: [{ index: 1, name: "step_no_spec", kind: "contract", task_id: "t2", run_id: "r2", status: "RUNNING" }],
    };
    render(<ChainView chainReport={chainReport} chainSpec={{ steps: [{ name: "" }] }} events={undefined as any} />);

    expect(screen.getByText(/Steps \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/step_no_spec/)).toBeInTheDocument();
    expect(screen.queryByText("Spec details")).toBeNull();
  });

  it("handles non-array chain steps safely", () => {
    const chainReport = { chain_id: "chain-null", status: "RUNNING", steps: null };
    render(<ChainView chainReport={chainReport} chainSpec={{ steps: null }} events={[]} />);

    expect(screen.getByText(/Steps \(0\)/)).toBeInTheDocument();
    expect(screen.getByText("No step records yet")).toBeInTheDocument();
  });

  it("covers context label helpers for number/boolean/fallback", () => {
    expect(pickContextLabel({ context: { value: "x" } } as any, "value")).toBe("x");
    expect(pickContextLabel({ context: { value: 1 } } as any, "value")).toBe("1");
    expect(pickContextLabel({ context: { value: false } } as any, "value")).toBe("false");
    expect(pickContextLabel({ context: {} } as any, "value")).toBe("-");
  });

  it("renders handoff fallback labels when context keys are missing", () => {
    render(
      <ChainView
        chainReport={{ chain_id: "chain-fallback", status: "RUNNING", steps: [] }}
        chainSpec={{ steps: [] }}
        events={[{ ts: "t2", event: "CHAIN_HANDOFF", context: { from: 7, to: true } } as any]}
      />
    );

    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
  });

  it("renders fallback placeholders for missing chain and step fields", () => {
    render(
      <ChainView
        chainReport={{
          chain_id: "",
          status: "",
          steps: [{ index: undefined, name: "", kind: "", task_id: "", run_id: "", status: "" }],
        }}
        chainSpec={{ steps: [] }}
        events={[]}
      />,
    );

    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
    expect(screen.getByText("#- unnamed")).toBeInTheDocument();
    expect(screen.getByText("Chain ID").closest(".chain-summary-meta-group")).not.toBeNull();
    expect(screen.getByText("Chain ID").parentElement).toHaveTextContent("-");

    const stepCard = screen.getByText("#- unnamed").closest(".chain-step-card");
    expect(stepCard).not.toBeNull();
    expect(within(stepCard as HTMLElement).queryByText(/^task:/)).toBeNull();
    expect(within(stepCard as HTMLElement).queryByText(/^run:/)).toBeNull();
  });
});
