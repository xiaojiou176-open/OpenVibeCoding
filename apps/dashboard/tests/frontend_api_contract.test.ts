import { describe, expect, it, expectTypeOf } from "vitest";

import type {
  AgentCatalogPayload as CanonicalAgentCatalogPayload,
  AgentStatusPayload as CanonicalAgentStatusPayload,
  BindingValidationMode as CanonicalBindingValidationMode,
  ContractCatalogRecord as CanonicalContractCatalogRecord,
  McpBundleReadModel as CanonicalMcpBundleReadModel,
  RoleBindingReadModel as CanonicalRoleBindingReadModel,
  RoleConfigApplyResponse as CanonicalRoleConfigApplyResponse,
  RoleConfigPreviewResponse as CanonicalRoleConfigPreviewResponse,
  RoleConfigSurface as CanonicalRoleConfigSurface,
  RuntimeBindingReadModel as CanonicalRuntimeBindingReadModel,
  SkillsBundleReadModel as CanonicalSkillsBundleReadModel,
  WorkflowCaseReadModel as CanonicalWorkflowCaseReadModel,
} from "../../../packages/frontend-api-contract/index";

import type {
  AgentCatalogPayload as SharedAgentCatalogPayload,
  AgentStatusPayload as SharedAgentStatusPayload,
  ContractRecord as SharedContractCatalogRecord,
  McpBundleReadModel as SharedMcpBundleReadModel,
  RoleBindingReadModel as SharedRoleBindingReadModel,
  RoleConfigApplyResponse as SharedRoleConfigApplyResponse,
  RoleConfigPreviewResponse as SharedRoleConfigPreviewResponse,
  RoleConfigSurface as SharedRoleConfigSurface,
  RuntimeBindingReadModel as SharedRuntimeBindingReadModel,
  SkillsBundleReadModel as SharedSkillsBundleReadModel,
  WorkflowCaseReadModel as SharedWorkflowCaseReadModel,
} from "@cortexpilot/frontend-shared/types";

import {
  FRONTEND_API_CONTRACT as localContract,
  PM_JOURNEY_STAGES as localStages,
  type FrontendApiContract as LocalFrontendApiContract,
  type PmJourneyContext as LocalPmJourneyContext,
  type PmJourneyStage as LocalPmJourneyStage,
} from "../lib/frontendApiContract";

import {
  FRONTEND_API_CONTRACT as packageContract,
  PM_JOURNEY_STAGES as packageStages,
  type FrontendApiContract as PackageFrontendApiContract,
  type PmJourneyContext as PackagePmJourneyContext,
  type PmJourneyStage as PackagePmJourneyStage,
} from "@cortexpilot/frontend-api-contract";

describe("frontendApiContract re-export mapping", () => {
  it("re-exports the same contract object to prevent drift", () => {
    expect(localContract).toBe(packageContract);
    expect(localContract.paths.runs).toBe("/api/runs");
    expect(localContract.paths.runDetail).toBe("/api/runs/{run_id}");
    expect(localContract.paths.runEvents).toBe("/api/runs/{run_id}/events");
    expect(localContract.paths.runEventsStream).toBe("/api/runs/{run_id}/events/stream");
    expect(localContract.paths.runDiff).toBe("/api/runs/{run_id}/diff");
    expect(localContract.paths.runReports).toBe("/api/runs/{run_id}/reports");
    expect(localContract.paths.agents).toBe("/api/agents");
    expect(localContract.paths.agentStatus).toBe("/api/agents/status");
    expect(localContract.paths.roleConfig).toBe("/api/agents/roles/{role}/config");
    expect(localContract.paths.roleConfigPreview).toBe("/api/agents/roles/{role}/config/preview");
    expect(localContract.paths.roleConfigApply).toBe("/api/agents/roles/{role}/config/apply");
    expect(localContract.paths.contracts).toBe("/api/contracts");
    expect(localContract.paths.workflows).toBe("/api/workflows");
    expect(localContract.paths.workflowDetail).toBe("/api/workflows/{workflow_id}");
    expect(localContract.paths.pmSessions).toBe("/api/pm/sessions");
    expect(localContract.paths.pmSessionMessages).toBe("/api/pm/sessions/{pm_session_id}/messages");
    expect(localContract.headers.requestId).toBe("x-request-id");
    expect(localContract.headers.traceId).toBe("x-trace-id");
    expect(localContract.headers.traceparent).toBe("traceparent");
    expect(localContract.headers.runId).toBe("x-cortexpilot-run-id");
  });

  it("re-exports PM journey stages without mutation", () => {
    expect(localStages).toBe(packageStages);
    expect(localStages).toEqual(["discover", "clarify", "execute", "verify"]);
  });

  it("keeps exported type aliases aligned with the package contract", () => {
    expectTypeOf<LocalFrontendApiContract>().toEqualTypeOf<PackageFrontendApiContract>();
    expectTypeOf<LocalPmJourneyContext>().toEqualTypeOf<PackagePmJourneyContext>();
    expectTypeOf<LocalPmJourneyStage>().toEqualTypeOf<PackagePmJourneyStage>();
  });

  it("keeps shared read-model type aliases aligned with the contract package", () => {
    expectTypeOf<SharedSkillsBundleReadModel>().toEqualTypeOf<CanonicalSkillsBundleReadModel>();
    expectTypeOf<SharedMcpBundleReadModel>().toEqualTypeOf<CanonicalMcpBundleReadModel>();
    expectTypeOf<SharedRuntimeBindingReadModel>().toEqualTypeOf<CanonicalRuntimeBindingReadModel>();
    expectTypeOf<SharedRoleBindingReadModel>().toEqualTypeOf<CanonicalRoleBindingReadModel>();
    expectTypeOf<SharedWorkflowCaseReadModel>().toEqualTypeOf<CanonicalWorkflowCaseReadModel>();
    expectTypeOf<SharedAgentCatalogPayload>().toEqualTypeOf<CanonicalAgentCatalogPayload>();
    expectTypeOf<SharedAgentStatusPayload>().toEqualTypeOf<CanonicalAgentStatusPayload>();
    expectTypeOf<SharedContractCatalogRecord>().toEqualTypeOf<CanonicalContractCatalogRecord>();
    expectTypeOf<SharedRoleConfigSurface>().toEqualTypeOf<CanonicalRoleConfigSurface>();
    expectTypeOf<SharedRoleConfigPreviewResponse>().toEqualTypeOf<CanonicalRoleConfigPreviewResponse>();
    expectTypeOf<SharedRoleConfigApplyResponse>().toEqualTypeOf<CanonicalRoleConfigApplyResponse>();
    expectTypeOf<SharedSkillsBundleReadModel["validation"]>().toEqualTypeOf<CanonicalBindingValidationMode>();
  });
});
