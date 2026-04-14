// GENERATED FILE. DO NOT EDIT.
// Source: docs/api/openapi.openvibecoding.json

export declare const PM_JOURNEY_STAGES: readonly ["discover", "clarify", "execute", "verify"];
export type PmJourneyStage = "discover" | "clarify" | "execute" | "verify";

export type PmJourneyContext = {
  stage: PmJourneyStage;
  reason: string;
  primaryAction: string;
  secondaryActions: string[];
};

export declare const COMMAND_TOWER_PRIORITY_LANES: readonly ["live", "risk", "actions", "details"];
export type CommandTowerPriorityLane = "live" | "risk" | "actions" | "details";

export declare const DESKTOP_WORK_MODES: readonly ["execute", "observe", "handoff"];
export type DesktopWorkMode = "execute" | "observe" | "handoff";
