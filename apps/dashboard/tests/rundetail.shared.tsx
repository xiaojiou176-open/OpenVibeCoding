import { vi } from "vitest";

import RunDetail from "../components/RunDetail";

export { RunDetail };

type FetchOptions = {
  events?: any[];
  reports?: any[];
  chainSpec?: any;
  availableRuns?: any[];
  agentStatus?: any[];
  toolCalls?: any[];
  replayOk?: boolean;
  replayStatus?: number;
  runsOk?: boolean;
  eventsOk?: boolean;
  reportsOk?: boolean;
  chainOk?: boolean;
  agentStatusOk?: boolean;
  toolCallsOk?: boolean;
  throwRuns?: boolean;
  throwChain?: boolean;
  throwReplay?: boolean;
  throwAgentStatus?: boolean;
  throwToolCalls?: boolean;
  throwReplayValue?: any;
};

export function mockFetchFactory(options: FetchOptions) {
  const {
    events = [],
    reports = [],
    chainSpec = null,
    availableRuns = [],
    replayOk = true,
    replayStatus = 200,
    runsOk = true,
    eventsOk = true,
    reportsOk = true,
    chainOk = true,
    agentStatus = [],
    toolCalls = [],
    agentStatusOk = true,
    toolCallsOk = true,
    throwRuns = false,
    throwChain = false,
    throwReplay = false,
    throwAgentStatus = false,
    throwToolCalls = false,
    throwReplayValue,
  } = options;

  return vi.fn(async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/runs/") && url.includes("/events")) {
      return { ok: eventsOk, status: eventsOk ? 200 : 500, json: async () => events };
    }
    if (url.includes("/api/runs/") && url.endsWith("/reports")) {
      return { ok: reportsOk, status: reportsOk ? 200 : 500, json: async () => reports };
    }
    if (url.includes("/api/runs/") && url.includes("/artifacts?name=tool_calls.jsonl")) {
      if (throwToolCalls) {
        throw new Error("tool calls failed");
      }
      return { ok: toolCallsOk, status: toolCallsOk ? 200 : 500, json: async () => ({ data: toolCalls }) };
    }
    if (url.includes("/api/runs/") && url.includes("/artifacts")) {
      if (throwChain) {
        throw new Error("chain spec failed");
      }
      return { ok: chainOk, status: chainOk ? 200 : 500, json: async () => ({ data: chainSpec }) };
    }
    if (url.includes("/api/agents/status")) {
      if (throwAgentStatus) {
        throw new Error("agent status failed");
      }
      return { ok: agentStatusOk, status: agentStatusOk ? 200 : 500, json: async () => ({ agents: agentStatus }) };
    }
    if (url.includes("/api/runs") && !url.includes("/api/runs/")) {
      if (throwRuns) {
        throw new Error("load runs failed");
      }
      return { ok: runsOk, status: runsOk ? 200 : 500, json: async () => availableRuns };
    }
    if (url.includes("/replay")) {
      if (throwReplay) {
        if (throwReplayValue !== undefined) {
          throw throwReplayValue;
        }
        throw new Error("replay exception");
      }
      return { ok: replayOk, status: replayStatus, json: async () => ({ ok: replayOk }) };
    }
    return { ok: false, status: 500, json: async () => ({}) };
  });
}

export function flushPromises(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, 0);
  });
}

export class MockEventSource {
  static instances: MockEventSource[] = [];

  onopen: (() => void) | null = null;

  onmessage: ((event: MessageEvent<string>) => void) | null = null;

  onerror: (() => void) | null = null;

  closed = false;

  constructor(public readonly url: string) {
    MockEventSource.instances.push(this);
  }

  emitOpen() {
    this.onopen?.();
  }

  emitMessage(payload: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }

  emitError() {
    this.onerror?.();
  }

  close() {
    this.closed = true;
  }

  static reset() {
    MockEventSource.instances = [];
  }
}

export function setupRunDetailTestEnv() {
  MockEventSource.reset();
  (globalThis as unknown as { EventSource?: unknown }).EventSource = undefined;
}

export function teardownRunDetailTestEnv() {
  vi.useRealTimers();
  vi.restoreAllMocks();
}
