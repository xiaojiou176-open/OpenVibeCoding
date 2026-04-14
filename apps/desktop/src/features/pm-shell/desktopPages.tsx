import { lazy, type ReactElement } from "react";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";

export type DesktopPageKey =
  | "overview"
  | "pm"
  | "command-tower"
  | "ct-session-detail"
  | "runs"
  | "run-detail"
  | "run-compare"
  | "workflows"
  | "workflow-detail"
  | "events"
  | "contracts"
  | "reviews"
  | "tests"
  | "policies"
  | "agents"
  | "locks"
  | "worktrees"
  | "god-mode"
  | "search"
  | "change-gates";

const uiCopy = getUiCopy(DEFAULT_UI_LOCALE);

export const PAGE_TITLES: Partial<Record<DesktopPageKey, string>> = {
  overview: uiCopy.desktop.labels.overview,
  pm: uiCopy.desktop.labels.pmIntake,
  "command-tower": uiCopy.desktop.labels.commandTower,
  "ct-session-detail": uiCopy.desktop.labels.sessionView,
  runs: uiCopy.desktop.labels.runs,
  "run-detail": uiCopy.desktop.labels.runDetail,
  "run-compare": uiCopy.desktop.labels.runCompare,
  workflows: uiCopy.desktop.labels.workflowCases,
  "workflow-detail": uiCopy.desktop.labels.workflowCaseDetail,
  events: uiCopy.desktop.labels.events,
  contracts: uiCopy.desktop.labels.contracts,
  reviews: uiCopy.desktop.labels.reviews,
  tests: uiCopy.desktop.labels.tests,
  policies: uiCopy.desktop.labels.policies,
  agents: uiCopy.desktop.labels.agents,
  locks: uiCopy.desktop.labels.locks,
  worktrees: uiCopy.desktop.labels.worktrees,
  "god-mode": uiCopy.desktop.labels.quickApproval,
  search: uiCopy.desktop.labels.search,
  "change-gates": uiCopy.desktop.labels.diffGate,
};

export function getDesktopPageTitle(page: DesktopPageKey, locale: UiLocale): string {
  const localized = getUiCopy(locale).desktop.labels;
  const titles: Partial<Record<DesktopPageKey, string>> = {
    overview: localized.overview,
    pm: localized.pmIntake,
    "command-tower": localized.commandTower,
    "ct-session-detail": localized.sessionView,
    runs: localized.runs,
    "run-detail": localized.runDetail,
    "run-compare": localized.runCompare,
    workflows: localized.workflowCases,
    "workflow-detail": localized.workflowCaseDetail,
    events: localized.events,
    contracts: localized.contracts,
    reviews: localized.reviews,
    tests: localized.tests,
    policies: localized.policies,
    agents: localized.agents,
    locks: localized.locks,
    worktrees: localized.worktrees,
    "god-mode": localized.quickApproval,
    search: localized.search,
    "change-gates": localized.diffGate,
  };
  return titles[page] || "OpenVibeCoding Command Tower";
}

const OverviewPage = lazy(async () => {
  const module = await import("../../pages/OverviewPage");
  return { default: module.OverviewPage };
});
const CommandTowerPage = lazy(async () => {
  const module = await import("../../pages/CommandTowerPage");
  return { default: module.CommandTowerPage };
});
const RunsPage = lazy(async () => {
  const module = await import("../../pages/RunsPage");
  return { default: module.RunsPage };
});
const RunDetailPage = lazy(async () => {
  const module = await import("../../pages/RunDetailPage");
  return { default: module.RunDetailPage };
});
const RunComparePage = lazy(async () => {
  const module = await import("../../pages/RunComparePage");
  return { default: module.RunComparePage };
});
const WorkflowsPage = lazy(async () => {
  const module = await import("../../pages/WorkflowsPage");
  return { default: module.WorkflowsPage };
});
const WorkflowDetailPage = lazy(async () => {
  const module = await import("../../pages/WorkflowDetailPage");
  return { default: module.WorkflowDetailPage };
});
const EventsPage = lazy(async () => {
  const module = await import("../../pages/EventsPage");
  return { default: module.EventsPage };
});
const ContractsPage = lazy(async () => {
  const module = await import("../../pages/ContractsPage");
  return { default: module.ContractsPage };
});
const ReviewsPage = lazy(async () => {
  const module = await import("../../pages/ReviewsPage");
  return { default: module.ReviewsPage };
});
const TestsPage = lazy(async () => {
  const module = await import("../../pages/TestsPage");
  return { default: module.TestsPage };
});
const PoliciesPage = lazy(async () => {
  const module = await import("../../pages/PoliciesPage");
  return { default: module.PoliciesPage };
});
const AgentsPage = lazy(async () => {
  const module = await import("../../pages/AgentsPage");
  return { default: module.AgentsPage };
});
const LocksPage = lazy(async () => {
  const module = await import("../../pages/LocksPage");
  return { default: module.LocksPage };
});
const WorktreesPage = lazy(async () => {
  const module = await import("../../pages/WorktreesPage");
  return { default: module.WorktreesPage };
});
const GodModePage = lazy(async () => {
  const module = await import("../../pages/GodModePage");
  return { default: module.GodModePage };
});
const SearchPage = lazy(async () => {
  const module = await import("../../pages/SearchPage");
  return { default: module.SearchPage };
});
const ChangeGatesPage = lazy(async () => {
  const module = await import("../../pages/ChangeGatesPage");
  return { default: module.ChangeGatesPage };
});
const CTSessionDetailPage = lazy(async () => {
  const module = await import("../../pages/CTSessionDetailPage");
  return { default: module.CTSessionDetailPage };
});

type RenderDesktopPageArgs = {
  activePage: DesktopPageKey;
  uiLocale: UiLocale;
  pmPageContent: ReactElement;
  detailRunId: string;
  detailWorkflowId: string;
  detailSessionId: string;
  navigate: (page: DesktopPageKey) => void;
  navigateToRun: (runId: string) => void;
  navigateToWorkflow: (workflowId: string) => void;
  navigateToSession: (sessionId: string) => void;
  setActivePage: (page: DesktopPageKey) => void;
};

export function renderDesktopPage({
  activePage,
  uiLocale,
  pmPageContent,
  detailRunId,
  detailWorkflowId,
  detailSessionId,
  navigate,
  navigateToRun,
  navigateToWorkflow,
  navigateToSession,
  setActivePage,
}: RenderDesktopPageArgs): ReactElement {
  switch (activePage) {
    case "overview":
      return <OverviewPage onNavigate={navigate} onNavigateToRun={navigateToRun} locale={uiLocale} />;
    case "pm":
      return pmPageContent;
    case "command-tower":
      return <CommandTowerPage onNavigateToSession={navigateToSession} locale={uiLocale} />;
    case "ct-session-detail":
      return <CTSessionDetailPage sessionId={detailSessionId} onBack={() => setActivePage("command-tower")} />;
    case "runs":
      return <RunsPage onNavigateToRun={navigateToRun} />;
    case "run-detail":
      return <RunDetailPage runId={detailRunId} onBack={() => setActivePage("runs")} onOpenCompare={() => setActivePage("run-compare")} locale={uiLocale} />;
    case "run-compare":
      return <RunComparePage runId={detailRunId} onBack={() => setActivePage("run-detail")} />;
    case "workflows":
      return <WorkflowsPage onNavigateToWorkflow={navigateToWorkflow} />;
    case "workflow-detail":
      return (
        <WorkflowDetailPage
          workflowId={detailWorkflowId}
          onBack={() => setActivePage("workflows")}
          onNavigateToRun={navigateToRun}
          locale={uiLocale}
        />
      );
    case "events":
      return <EventsPage />;
    case "contracts":
      return <ContractsPage onNavigate={navigate} onNavigateToRun={navigateToRun} />;
    case "reviews":
      return <ReviewsPage />;
    case "tests":
      return <TestsPage />;
    case "policies":
      return <PoliciesPage />;
    case "agents":
      return <AgentsPage onNavigate={navigate} onNavigateToRun={navigateToRun} />;
    case "locks":
      return <LocksPage />;
    case "worktrees":
      return <WorktreesPage />;
    case "god-mode":
      return <GodModePage locale={uiLocale} />;
    case "search":
      return <SearchPage />;
    case "change-gates":
      return <ChangeGatesPage />;
    default:
      return <OverviewPage onNavigate={navigate} onNavigateToRun={navigateToRun} locale={uiLocale} />;
  }
}
