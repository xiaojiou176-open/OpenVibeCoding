import { vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  fetchCommandTowerAlerts: vi.fn(),
  fetchCommandTowerOverview: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionConversationGraph: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessionMetrics: vi.fn(),
  fetchPmSessions: vi.fn(),
  openEventsStream: vi.fn(),
  postPmSessionMessage: vi.fn(),
}));

import "./command_tower_async_home.suite";
import "./command_tower_async_session.suite";
