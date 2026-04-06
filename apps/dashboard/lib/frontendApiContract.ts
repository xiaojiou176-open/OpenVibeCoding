import {
  FRONTEND_API_CONTRACT as PACKAGE_FRONTEND_API_CONTRACT,
  PM_JOURNEY_STAGES as PACKAGE_PM_JOURNEY_STAGES,
} from "@cortexpilot/frontend-api-contract";

export const FRONTEND_API_CONTRACT = PACKAGE_FRONTEND_API_CONTRACT;
export const PM_JOURNEY_STAGES = PACKAGE_PM_JOURNEY_STAGES;

export type { FrontendApiContract } from "@cortexpilot/frontend-api-contract";
export type {
  PmJourneyContext,
  PmJourneyStage,
  CommandTowerPriorityLane,
  DesktopWorkMode,
} from "@cortexpilot/frontend-api-contract/ui-flow";
