import { render, screen, within } from "@testing-library/react";

import ContractViewer from "../components/ContractViewer";

test("renders contract payload", () => {
  const contract = {
    task_id: "task-123",
    owner_agent: { role: "PM" },
    acceptance_tests: ["pnpm test"],
  };
  render(<ContractViewer contract={contract} />);

  expect(screen.getByText("Contract")).toBeInTheDocument();
  expect(screen.getByText("Owner agent")).toBeInTheDocument();
  expect(screen.getByText("PM")).toBeInTheDocument();
  expect(screen.getByText("Acceptance tests")).toBeInTheDocument();
  expect(screen.getByText("1 test")).toBeInTheDocument();
  expect(screen.getByText(/task-123/)).toBeInTheDocument();
});

test("renders empty contract fallback", () => {
  render(<ContractViewer contract={null} />);

  expect(screen.getByText("Contract")).toBeInTheDocument();
  expect(screen.getByText("v1")).toBeInTheDocument();
  expect(screen.getByText("Tool permissions")).toBeInTheDocument();
  expect(screen.getByText("None")).toBeInTheDocument();
  expect(screen.queryByText("View full contract JSON")).toBeNull();
});

test("covers schema/agent/tool permissions branches", () => {
  render(
    <ContractViewer
      schemaVersion="v9"
      contract={{
        task_id: "task-999",
        allowed_paths: ["apps/"],
        acceptance_tests: ["pytest -q"],
        owner_agent: { role: "PM", agent_id: "pm-1" },
        assigned_agent: { role: "Worker", agent_id: "wk-1" },
        tool_permissions: { shell: "allow" },
      }}
    />,
  );

  expect(screen.getByText("v9")).toBeInTheDocument();

  const ownerRow = screen.getByText("Owner agent").closest(".contract-field-row");
  expect(ownerRow).not.toBeNull();
  expect(within(ownerRow as HTMLElement).getByText("PM (pm-1)")).toBeInTheDocument();

  const assignedRow = screen.getByText("Assigned agent").closest(".contract-field-row");
  expect(assignedRow).not.toBeNull();
  expect(within(assignedRow as HTMLElement).getByText("Worker (wk-1)")).toBeInTheDocument();

  expect(screen.getByText("1 permission")).toBeInTheDocument();
  expect(screen.getByText("View full contract JSON")).toBeInTheDocument();
  expect(screen.getByText(/"shell": "allow"/)).toBeInTheDocument();
});
