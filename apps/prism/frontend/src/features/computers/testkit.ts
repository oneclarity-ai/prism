import type { PrismLike } from "@/lib/events";
import type { ComputersHost, QaRun } from "./types";

/** Test helpers: a routing fake `fetch`, run factories and a fake chat host. */

export interface FakeRequest {
  url: string;
  method: string;
  body: unknown;
  headers: Record<string, string>;
  signal: AbortSignal | null | undefined;
}
type Reply = Response | object | null;
export type Handler = (request: FakeRequest) => Reply | Promise<Reply>;

export const json = (value: unknown, status = 200): Response =>
  new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });

/** Routes are keyed by `"METHOD /path"` (query string ignored); unknown routes answer 404. */
export function installFetch(routes: Record<string, Handler>) {
  const calls: FakeRequest[] = [];
  const fake = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const request: FakeRequest = {
      url,
      method: (init.method ?? "GET").toUpperCase(),
      body: typeof init.body === "string" ? (JSON.parse(init.body) as unknown) : undefined,
      headers: (init.headers as Record<string, string> | undefined) ?? {},
      signal: init.signal,
    };
    calls.push(request);
    const handler = routes[`${request.method} ${url.split("?")[0]}`];
    if (!handler) return json({ detail: `no route for ${request.method} ${url}` }, 404);
    const reply = await handler(request);
    if (reply instanceof Response) return reply;
    return json(reply);
  });
  vi.stubGlobal("fetch", fake);
  return { calls, fetch: fake, count: (key: string) => calls.filter((call) => `${call.method} ${call.url.split("?")[0]}` === key).length };
}

export const stubBlobUrls = () => {
  let n = 0;
  const create = vi.fn(() => `blob:fake-${(n += 1)}`);
  const revoke = vi.fn();
  URL.createObjectURL = create;
  URL.revokeObjectURL = revoke;
  return { create, revoke };
};

export const makeRun = (over: Partial<QaRun> = {}): QaRun => ({
  id: "run-1",
  prism_id: "p1",
  state: "planned",
  active: false,
  kind: "qa",
  site: "example.com",
  approvals: [],
  plan: {
    title: "Website test",
    host: "example.com",
    environment: "production",
    discovery_mode: "automatic",
    pages: ["/"],
    features: ["contact form"],
    acceptance_criteria: ["Form validates"],
    max_turns: 60,
    budget_usd: 1,
    allow_bug_filing: false,
    may_file_bugs: true,
  },
  turn: 0,
  cost_usd: 0,
  started_at: null,
  ended_at: null,
  ...over,
});

export const makeWorkRun = (over: Partial<QaRun> = {}): QaRun =>
  makeRun({
    id: "work-1",
    kind: "work",
    site: null,
    plan: {
      title: "Find leads",
      steps: ["Search the web", "List sites"],
      sites: ["https://linkedin.com"],
      any_public_site: true,
      uses: ["browser"],
      asks_first: ["login"],
      max_turns: 40,
      budget_usd: 1.5,
      max_minutes: 20,
    },
    ...over,
  });

export const qaPrism: PrismLike = { id: "p1", name: "Quinn", template_key: "qa_tester" };
export const plainPrism: PrismLike = { id: "p2", name: "Riya" };

export function fakeHost(over: Partial<ComputersHost> = {}): ComputersHost {
  return { refreshMessages: vi.fn(async () => {}), rerenderChat: vi.fn(), setStatus: vi.fn(), ...over };
}

export const message = (kind: string, runId = "run-1", extra: Record<string, unknown> = {}) => ({
  content: `lead for ${kind}`,
  message_metadata: { kind, qa_run_id: runId, ...extra },
});
