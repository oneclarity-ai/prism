import type { Job, Message, Proposal, Review, Thread } from "./types";

export interface FakeRequest {
  method: string;
  url: string;
  body: Record<string, unknown> | undefined;
}
type Reply = object | Response | null;
export type Handler = (request: FakeRequest) => Reply | Promise<Reply>;

export const json = (value: unknown, status = 200): Response =>
  new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });

/** Routes are keyed "METHOD /path" (query ignored); unknown routes answer 404 so they surface in assertions. */
export function installFetch(routes: Record<string, Handler>) {
  const calls: FakeRequest[] = [];
  const fake = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const request: FakeRequest = {
      method: (init.method ?? "GET").toUpperCase(),
      url,
      body: typeof init.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : undefined,
    };
    calls.push(request);
    const handler = routes[`${request.method} ${url.split("?")[0]}`];
    if (!handler) return json({ detail: `no route for ${request.method} ${url}` }, 404);
    const reply = await handler(request);
    return reply instanceof Response ? reply : json(reply);
  });
  vi.stubGlobal("fetch", fake);
  return { calls, count: (key: string) => calls.filter((call) => `${call.method} ${call.url.split("?")[0]}` === key).length };
}

export const PRISM = { id: "p1", name: "Release Prism", code: "pAbc12", description: "Tracks the release.", state: "active", lifecycle_version: 3 };

export const thread = (overrides: Partial<Thread> = {}): Thread => ({
  id: "t1",
  title: "Prism",
  is_canonical: true,
  source_external_id: null,
  source_kind: null,
  source_label: null,
  source_metadata: {},
  created_at: "2026-01-01T10:00:00Z",
  updated_at: "2026-01-01T10:00:00Z",
  ...overrides,
});

export const job = (id: string, overrides: Partial<Job> = {}): Job => ({
  id,
  thread_id: "t1",
  goal: `goal ${id}`,
  state: "completed",
  version: 1,
  scope_mode: "auto",
  sources: [
    { external_id: "c1", label: "Release group", selection_reason: "auto", source_metadata: { chat_type: "group", participants: ["Parv", "Meera"] } },
    { external_id: "c2", label: "Parv Pareek", selection_reason: "auto", source_metadata: { chat_type: "oneonone" } },
  ],
  requested_scope: {},
  steps: [],
  created_at: "2026-01-01T10:00:00Z",
  ...overrides,
});

export const message = (id: string, role: "manager" | "assistant", content: string, jobId: string | null, minute: number, metadata: Record<string, unknown> = {}): Message => ({
  id,
  role,
  content,
  job_id: jobId,
  thread_id: "t1",
  message_metadata: metadata,
  created_at: `2026-01-01T10:${String(minute).padStart(2, "0")}:00Z`,
  updated_at: `2026-01-01T10:${String(minute).padStart(2, "0")}:00Z`,
});

export const proposal = (id: string, jobId: string, label: string, overrides: Partial<Proposal> = {}): Proposal => ({
  id,
  job_id: jobId,
  state: "pending",
  body: `Hello ${label}`,
  reason: "Because it is due.",
  revision: 1,
  payload_hash: `hash-${id}`,
  sequence: 1,
  destination: { label },
  evidence_ids: ["e1"],
  depends_on_logical_action_ids: [],
  created_at: "2026-01-01T10:02:00Z",
  approval: null,
  ...overrides,
});

export const review = (overrides: Partial<Review> = {}): Review => ({
  summary: "The release schema is the open dependency.",
  attention_items: [],
  manager_questions: [],
  limitations: [],
  confidence: 0.8,
  requires_reply: false,
  summary_evidence_ids: ["e1"],
  provider: "fake",
  model: "fake-1",
  created_at: "2026-01-01T10:01:00Z",
  ...overrides,
});

export const evidence = (id = "e1", excerpt = "Schema lands Friday") => ({
  id,
  excerpt,
  quoted_excerpt: null,
  reply_to_source_id: null,
  sender_display_name: "Parv Pareek",
  sent_at: "2026-01-01T09:59:00Z",
  source_external_id: "c1",
  source_label: "Release group",
  source_message_id: `m-${id}`,
});

export interface Conversation {
  thread: Thread;
  messages: Message[];
  jobs: Job[];
  reviews?: Record<string, Review>;
  evidence?: Record<string, ReturnType<typeof evidence>[]>;
}

/** Routes that open a Prism's conversation; spread first, then override the pieces under test. */
export function conversationRoutes(prismId: string, data: Conversation): Record<string, Handler> {
  const routes: Record<string, Handler> = {
    "GET /api/v2/qa/status": () => ({ available: false, computers: false }),
    [`GET /api/v2/prisms/${prismId}/conversation`]: () => ({ thread: data.thread }),
    [`GET /api/v2/agent/threads/${data.thread.id}/messages`]: () => data.messages,
    [`GET /api/v2/agent/threads/${data.thread.id}/jobs`]: () => data.jobs,
    [`GET /api/v2/prisms/${prismId}/observations`]: () => ({ items: [] }),
    [`GET /api/v2/prisms/${prismId}/preferences`]: () => [],
    "GET /api/v2/agent/preferences": () => [],
  };
  data.jobs.forEach((item) => {
    routes[`GET /api/v2/agent/jobs/${item.id}`] = () => item;
    routes[`GET /api/v2/agent/jobs/${item.id}/evidence`] = () => data.evidence?.[item.id] ?? [];
    routes[`GET /api/v2/agent/jobs/${item.id}/review`] = () => {
      const found = data.reviews?.[item.id];
      return found ?? json({ detail: "No review yet" }, 404);
    };
  });
  return routes;
}
