import { vi } from "vitest";

export interface FetchCall {
  method: string;
  path: string;
  url: string;
  body: unknown;
}

export interface FetchReply {
  status?: number;
  json?: unknown;
}

type Route = unknown | FetchReply | ((call: FetchCall) => unknown);

/**
 * Replaces `fetch` with a router keyed by `"METHOD /path"` (query string ignored). A route is a JSON value or a
 * function of the call; return `{ __status, json }` through `reply()` for non-200 answers. Unknown routes answer 404.
 */
export function mockFetch(routes: Record<string, Route>) {
  const calls: FetchCall[] = [];
  const table = new Map(Object.entries(routes));
  const fake = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const parsed = new URL(url, "http://localhost");
    const method = (init?.method || "GET").toUpperCase();
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    const call: FetchCall = { method, path: parsed.pathname, url, body };
    calls.push(call);
    const key = `${method} ${url.startsWith("http") ? url : parsed.pathname}`;
    const route = table.get(key) ?? table.get(`${method} ${parsed.pathname}`);
    if (route === undefined) return jsonResponse(404, { detail: `No route for ${key}` });
    const value = typeof route === "function" ? (route as (call: FetchCall) => unknown)(call) : route;
    if (value && typeof value === "object" && "__reply" in value) {
      const { status, json } = (value as { __reply: FetchReply }).__reply;
      return jsonResponse(status ?? 200, json ?? null);
    }
    return jsonResponse(200, value ?? null);
  });
  vi.stubGlobal("fetch", fake);
  return {
    calls,
    set(key: string, route: Route) {
      table.set(key, route);
    },
    callsTo(method: string, path: string): FetchCall[] {
      return calls.filter((call) => call.method === method && call.path === path);
    },
  };
}

export const reply = (status: number, json: unknown) => ({ __reply: { status, json } });

function jsonResponse(status: number, json: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(json), { status, headers: { "Content-Type": "application/json" } });
}
