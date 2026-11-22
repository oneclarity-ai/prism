import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  checkAvailability,
  computersEnabled,
  focusRun,
  getState,
  initQa,
  onPrism,
  planRequest,
  resetComputers,
  setOpen,
  startRun,
  cancelRun,
  decideApproval,
  isQaPrism,
} from "./store";
import { fakeHost, installFetch, json, makeRun, makeWorkRun, plainPrism, qaPrism, stubBlobUrls } from "./testkit";
import { emit, on } from "@/lib/events";

const planned = makeRun();
const running = makeRun({ state: "running", active: true, started_at: "2026-01-01T00:00:00Z", turn: 2 });
const done = makeRun({
  state: "succeeded",
  active: false,
  cases: { total: 3, pass: 2, fail: 1 },
  report: { counts: { pass: 2, fail: 1 }, cases: [], bugs: [], pages: ["/"], cost_usd: 0.4 },
});

const sse = (...events: Array<[string, unknown]>) =>
  new Response(events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""), {
    headers: { "Content-Type": "text/event-stream" },
  });

beforeEach(() => {
  stubBlobUrls();
});
afterEach(() => {
  resetComputers();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("availability and Prism gating", () => {
  it("reads /qa/status and survives an error", async () => {
    const net = installFetch({ "GET /api/v2/qa/status": () => ({ available: true, computers: true }) });
    expect(await checkAvailability()).toBe(true);
    expect(computersEnabled()).toBe(true);
    expect(net.count("GET /api/v2/qa/status")).toBe(1);
    installFetch({ "GET /api/v2/qa/status": () => json({ detail: "down" }, 503) });
    expect(await checkAvailability()).toBeNull();
  });

  it("only QA Prisms (or every Prism when computers are on) use a computer", async () => {
    installFetch({ "GET /api/v2/prisms/p2/qa/runs": () => [], "GET /api/v2/prisms/p1/qa/runs": () => [] });
    expect(isQaPrism(qaPrism)).toBe(true);
    expect(isQaPrism(plainPrism)).toBe(false);
    onPrism(plainPrism);
    setOpen(true);
    expect(getState().open).toBe(false);
    onPrism(qaPrism);
    setOpen(true);
    expect(getState().open).toBe(true);
    onPrism(plainPrism);
    expect(getState().open).toBe(false);
  });

  it("initQa probes availability and loads runs once computers are on", async () => {
    const net = installFetch({
      "GET /api/v2/qa/status": () => ({ available: true, computers: true }),
      "GET /api/v2/prisms/p2/qa/runs": () => [],
    });
    onPrism(plainPrism);
    initQa(fakeHost());
    await vi.waitFor(() => expect(net.count("GET /api/v2/prisms/p2/qa/runs")).toBe(1));
  });
});

describe("planRequest", () => {
  it("posts the task to the Prism's plan endpoint and reports whether it was handled", async () => {
    const net = installFetch({ "POST /api/v2/prisms/p1/qa/plan": () => ({ handled: true, qa_run_id: "run-1" }) });
    expect(await planRequest(qaPrism, "thread-1", "test example.com")).toBe(true);
    expect(net.calls[0]?.body).toEqual({ thread_id: "thread-1", content: "test example.com" });
    expect(await planRequest(plainPrism, "t", "hi")).toBe(false);
    expect(net.count("POST /api/v2/prisms/p1/qa/plan")).toBe(1);
  });
});

describe("run lifecycle: plan -> approved -> running -> report", () => {
  it("loads runs, follows a started run until it ends and refreshes the chat on card changes", async () => {
    const host = fakeHost();
    const events: string[] = [];
    const off = on("computer-opened", () => events.push("opened"));
    let listed = [planned]; // what the server lists follows the run, like the real endpoint
    const net = installFetch({
      "GET /api/v2/prisms/p1/qa/runs": () => listed,
      "GET /api/v2/prisms/p1/computer": () => ({ state: "asleep" }),
      "POST /api/v2/qa/runs/run-1/start": () => {
        listed = [running];
        return running;
      },
      "GET /api/v2/qa/runs/run-1/stream": () => {
        listed = [done];
        return sse(["state", { ...running, state: "waiting_approval" }], ["state", done], ["end", {}]);
      },
    });
    initQa(host);
    onPrism(qaPrism);
    await vi.waitFor(() => expect(getState().order).toEqual(["run-1"]));
    expect(getState().focus).toBe("run-1");
    expect(getState().runs.get("run-1")?.state).toBe("planned");

    expect(await startRun(planned, { max_turns: 10 })).toBe(true);
    expect(net.calls.find((call) => call.url.endsWith("/start"))?.body).toEqual({ max_turns: 10 });
    expect(getState().open).toBe(true);
    expect(getState().focus).toBe("run-1");
    expect(events).toContain("opened");
    expect(host.rerenderChat).toHaveBeenCalledWith({ scroll: "bottom" });

    await vi.waitFor(() => expect(getState().runs.get("run-1")?.state).toBe("succeeded"));
    await vi.waitFor(() => expect(getState().streams.size).toBe(0));
    expect(getState().runs.get("run-1")?.report).toBeTruthy();
    // waiting_approval and succeeded each changed what the chat cards show
    expect(host.refreshMessages).toHaveBeenCalled();
    expect(host.rerenderChat).toHaveBeenCalledWith({ scroll: "auto" });
    off();
  });

  it("falls back to a plain read when the stream is unavailable", async () => {
    installFetch({
      "GET /api/v2/prisms/p1/qa/runs": () => [running],
      "GET /api/v2/qa/runs/run-1/stream": () => json({ detail: "no" }, 500),
      "GET /api/v2/qa/runs/run-1": () => done,
    });
    initQa(fakeHost());
    onPrism(qaPrism);
    await vi.waitFor(() => expect(getState().runs.get("run-1")?.state).toBe("succeeded"));
    await vi.waitFor(() => expect(getState().streams.size).toBe(0));
  });

  it("start failure reports through the host and keeps the run unstarted", async () => {
    const host = fakeHost();
    installFetch({
      "GET /api/v2/prisms/p1/qa/runs": () => [planned],
      "POST /api/v2/qa/runs/run-1/start": () => json({ detail: "Budget too high" }, 422),
    });
    initQa(host);
    onPrism(qaPrism);
    await vi.waitFor(() => expect(getState().order).toEqual(["run-1"]));
    expect(await startRun(planned, {})).toBe(false);
    expect(host.setStatus).toHaveBeenCalledWith("Budget too high", true);
    expect(getState().runs.get("run-1")?.state).toBe("planned");
  });

  it("cancel applies the stopped run; decisions post to the approval endpoint", async () => {
    const host = fakeHost();
    const net = installFetch({
      "GET /api/v2/prisms/p1/qa/runs": () => [running],
      "GET /api/v2/qa/runs/run-1/stream": () => sse(["end", {}]),
      "POST /api/v2/qa/runs/run-1/cancel": () => ({ ...running, state: "cancelled", active: false }),
      "POST /api/v2/qa/approvals/a1/decision": () => ({ ...running, approvals: [{ id: "a1", kind: "login", status: "approved" }] }),
    });
    initQa(host);
    onPrism(qaPrism);
    await vi.waitFor(() => expect(getState().order).toEqual(["run-1"]));
    await cancelRun(running);
    expect(getState().runs.get("run-1")?.state).toBe("cancelled");
    expect(await decideApproval({ id: "a1", kind: "login", status: "pending" }, { decision: "approve", login: { username: "u", password: "p", remember: true } })).toBe(true);
    expect(net.calls.at(-1)?.body).toEqual({ decision: "approve", login: { username: "u", password: "p", remember: true } });
    expect(getState().runs.get("run-1")?.approvals[0]?.status).toBe("approved");
  });

  it("failed decision reports and resolves false", async () => {
    const host = fakeHost();
    installFetch({ "POST /api/v2/qa/approvals/a1/decision": () => json({ detail: "Nope" }, 409) });
    initQa(host);
    expect(await decideApproval({ id: "a1", kind: "login", status: "pending" }, { decision: "reject" })).toBe(false);
    expect(host.setStatus).toHaveBeenCalledWith("Nope", true);
  });
});

describe("focusRun and prism changes", () => {
  it("loads an unknown run, focuses it and opens the panel", async () => {
    const net = installFetch({
      "GET /api/v2/prisms/p1/qa/runs": () => [],
      "GET /api/v2/qa/runs/work-1": () => makeWorkRun({ prism_id: "p1" }),
    });
    initQa(fakeHost());
    onPrism(qaPrism);
    await vi.waitFor(() => expect(net.count("GET /api/v2/prisms/p1/qa/runs")).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await focusRun("work-1");
    expect(getState().focus).toBe("work-1");
    expect(getState().open).toBe(true);
    await focusRun(undefined);
    expect(getState().focus).toBe("work-1");
  });

  it("resets focus and order when the Prism changes, and ignores stale run lists", async () => {
    let release: (value: object) => void = () => {};
    installFetch({
      "GET /api/v2/prisms/p1/qa/runs": () => new Promise<object>((resolve) => (release = resolve)),
      "GET /api/v2/qa/status": () => ({ available: true, computers: true }),
      "GET /api/v2/prisms/p2/qa/runs": () => [],
    });
    await checkAvailability();
    onPrism(qaPrism);
    onPrism(plainPrism);
    release([planned]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(getState().order).toEqual([]);
    expect(getState().prism?.id).toBe("p2");
  });

  it("emits focus requests only through the bus (chat owns the listener)", () => {
    const seen: string[] = [];
    const off = on("focus-computer-run", ({ runId }) => seen.push(runId));
    emit("focus-computer-run", { runId: "r9" });
    off();
    expect(seen).toEqual(["r9"]);
  });
});
