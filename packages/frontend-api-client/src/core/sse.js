import { FRONTEND_API_CONTRACT } from "@openvibecoding/frontend-api-contract";

class FetchEventsStream {
  constructor(url, fetchImpl, headers) {
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this._closed = false;
    this._controller = new AbortController();
    this._consume(url, fetchImpl, headers);
  }

  close() {
    if (this._closed) return;
    this._closed = true;
    this._controller.abort();
  }

  async _consume(url, fetchImpl, headers) {
    try {
      const response = await fetchImpl(url, {
        method: "GET",
        cache: "no-store",
        headers,
        signal: this._controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`SSE connect failed: ${response.status}`);
      }

      this.onopen?.call(this, new Event("open"));
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!this._closed) {
        const { done, value } = await reader.read();
        if (done) {
          // Normal EOF/stream close should not be treated as transport error.
          this._closed = true;
          return;
        }

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split(/\r?\n\r?\n/);
        buffer = chunks.pop() || "";

        for (const chunk of chunks) {
          const lines = chunk.split(/\r?\n/);
          const data = [];
          for (const line of lines) {
            if (line.startsWith("data:")) {
              data.push(line.slice(5).trimStart());
            }
          }
          if (data.length > 0) {
            this.onmessage?.call(this, new MessageEvent("message", { data: data.join("\n") }));
          }
        }
      }
    } catch {
      if (!this._closed) {
        this.onerror?.call(this, new Event("error"));
      }
    }
  }
}

function buildQuery(params = {}) {
  if (params instanceof URLSearchParams) {
    const queryString = params.toString();
    return queryString ? `?${queryString}` : "";
  }

  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    search.set(key, String(value));
  }
  const queryString = search.toString();
  return queryString ? `?${queryString}` : "";
}

export function createSseCore(options) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const auth = options.auth;
  const baseUrl = String(options.baseUrl || "").replace(/\/$/, "");
  const eventSourceCtor = options.eventSourceCtor || globalThis.EventSource;

  function open(path, query, sseOptions = {}) {
    const url = `${baseUrl}${path}${buildQuery(query)}`;
    const token = typeof sseOptions.resolveToken === "function" ? sseOptions.resolveToken() : undefined;

    if (token && fetchImpl) {
      return new FetchEventsStream(url, fetchImpl, auth.authHeaders());
    }

    if (typeof eventSourceCtor !== "function") {
      throw new Error("EventSource is not available and fetch fallback is disabled");
    }

    const withCredentials = Boolean(FRONTEND_API_CONTRACT.network.eventSourceWithCredentials);
    return new eventSourceCtor(url, withCredentials ? { withCredentials } : undefined);
  }

  return {
    open,
  };
}
