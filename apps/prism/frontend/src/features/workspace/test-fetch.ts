import { vi } from "vitest";

export type Handler = (url: URL, init: RequestInit) => unknown;
export interface FetchCall {
  method: string;
  path: string;
  body: unknown;
}

/** Fake `fetch`: first matching `[method, pattern, handler]` answers with its JSON; unmatched calls are 404. */
export function mockFetch(routes: Array<readonly [string, RegExp, Handler]>): FetchCall[] {
  const calls: FetchCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = new URL(String(input), "http://localhost");
      const method = (init.method || "GET").toUpperCase();
      calls.push({ method, path: url.pathname + url.search, body: init.body ? JSON.parse(String(init.body)) : undefined });
      const route = routes.find(([m, pattern]) => m === method && pattern.test(url.pathname + url.search));
      if (!route) return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      const result = route[2](url, init);
      return result === null ? new Response(null, { status: 204 }) : new Response(JSON.stringify(result), { status: 200 });
    }),
  );
  return calls;
}
