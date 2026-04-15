import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";

const ROLE_PURPOSE_ZH: Record<string, string> = {
  AI: "负责在受控边界内接入模型、运行时与工具能力，不扩大产品范围。",
  BACKEND: "负责实现后端能力、接口与数据流，不越过前端或产品边界。",
  FRONTEND: "负责实现前端界面与交互，不越过后端或运行时边界。",
  INFRA: "负责基础设施、环境与部署通道，不扩大到业务实现层。",
  OPS: "负责运行治理、值守与恢复动作，让系统保持可操作状态。",
  PM: "负责把需求收成可执行任务包，并维护规划节奏与交付边界。",
  RESEARCHER: "负责做有边界的调研，把结论和证据整理给执行链路使用。",
  REVIEWER: "负责只读审查，识别 blocker、风险和未闭合证据。",
  SEARCHER: "负责受控外部检索，只返回有证据支撑的结果。",
  SECURITY: "负责安全检查和护栏收口，不扩大 blast radius。",
  TECH_LEAD: "负责把产品意图拆成可执行合同、依赖关系和集成检查点。",
  TEST: "负责执行受合同约束的验证，并回传确定性的测试证据。",
  TEST_RUNNER: "负责跑验证命令与测试链路，只汇报可复核的结果。",
  UI_UX: "负责界面与体验改动，在前端边界内交付更清晰的操作面。",
  WORKER: "负责在允许路径内完成具体改动，并按结构化方式交付证据。",
};

export function localizeRolePurpose(role: string | null | undefined, purpose: string | null | undefined, locale: UiLocale): string {
  const rawPurpose = String(purpose || "").trim();
  if (locale !== "zh-CN") {
    return rawPurpose;
  }
  const normalizedRole = String(role || "").trim().toUpperCase();
  return ROLE_PURPOSE_ZH[normalizedRole] || rawPurpose;
}
