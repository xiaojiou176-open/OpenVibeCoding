import type { OperatorCopilotBrief as SharedOperatorCopilotBrief } from "@openvibecoding/frontend-shared/types";

export * from "@openvibecoding/frontend-shared/types";
export {
  GENERAL_TASK_TEMPLATE,
  buildTaskPackFieldStateForPack,
  buildTaskPackTemplatePayload,
  findTaskPackByTemplate,
  formatBindingReadModelLabel,
  formatRoleBindingRuntimeCapabilitySummary,
  formatRoleBindingRuntimeSummary,
  hydrateTaskPackFieldStateFromPayload,
  mergeTaskPackFieldStateByTemplate,
} from "@openvibecoding/frontend-shared/types";

export type OperatorCopilotBrief = SharedOperatorCopilotBrief;
