import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { FormDialogProvider } from "@/components/ui";
import { emit } from "@/lib/events";
import { renderWithApp } from "@/test/render";
import { installDialogPolyfill } from "@/test/dialog";
import { OperationsPage } from "./OperationsPage";
import { mockFetch } from "./test-fetch";
import { resetWorkspaceNav } from "./workspace-nav";
import type { BrainEntry } from "./types";

beforeAll(installDialogPolyfill);

const now = new Date().toISOString();
const overview = {
  agents: [{ id: "agent-1", key: "k", name: "Research Prism", status: "active" }],
  positions: [],
  tasks: [{ id: "t1", title: "Review release", goal: "Check it", agent_id: "agent-1", status: "todo", created_at: now }],
  runs: [
    { id: "run-1234567890", task_title: '<img src=x onerror="window.__xss=1">Hostile run', agent_id: "agent-1", status: "succeeded", created_at: now, started_at: now, ended_at: now, total_tokens: 1200, cost_usd: 0.03 },
  ],
  approvals: [],
  bugs: [],
  targets: [],
};
const organization = { owner_name: "Yash", members: [] as unknown[] };
let brain: BrainEntry[] = [];

function routes(extra: Array<readonly [string, RegExp, (url: URL) => unknown]> = []) {
  return mockFetch([
    ...extra,
    ["GET", /^\/api\/v2\/operations\/overview$/, () => overview],
    ["GET", /^\/api\/v2\/prisms\/organization$/, () => organization],
    ["POST", /^\/api\/v2\/prisms\/adopt-engine-agents$/, () => []],
    ["GET", /^\/api\/v2\/brain$/, () => brain],
    ["GET", /^\/api\/v2\/work\/approvals/, () => []],
  ]);
}

function setup(app = {}) {
  const root = document.createElement("div");
  document.body.append(root);
  const view = renderWithApp(
    <FormDialogProvider>
      <OperationsPage />
    </FormDialogProvider>,
    { app: { activeTab: "operations", pageActionsRoot: root, ...app } },
  );
  return { ...view, actionsRoot: root };
}

beforeEach(() => {
  localStorage.clear();
  resetWorkspaceNav();
  brain = [];
  Reflect.deleteProperty(window, "__xss");
});

describe("OperationsPage", () => {
  it("shows the loading status, then the dashboard with actions and the URL report", async () => {
    routes();
    const { app, actionsRoot } = setup();
    expect(screen.getByRole("status")).toHaveTextContent("Loading workspace…");
    expect(await screen.findByText("Active Prisms")).toBeInTheDocument();
    expect(within(actionsRoot).getByRole("button", { name: "New task" })).toBeInTheDocument();
    expect(within(actionsRoot).getByRole("button", { name: "Refresh workspace" })).toBeInTheDocument();
    expect(app.routes.workspace).toHaveBeenCalledWith(expect.objectContaining({ page: "overview" }));
    expect(app.setPageHeading).toHaveBeenCalledWith(expect.objectContaining({ title: expect.stringMatching(/^Good (morning|afternoon|evening)/) }));
  });

  it("switches pages on the workspace-navigate bus event and reports the page", async () => {
    routes();
    const { app } = setup();
    await screen.findByText("Active Prisms");
    act(() => emit("workspace-navigate", { page: "runs" }));
    expect(app.setActiveTab).toHaveBeenCalledWith("operations");
    await screen.findByRole("table");
    expect(app.routes.workspace).toHaveBeenLastCalledWith(expect.objectContaining({ page: "runs" }));
    expect(app.setPageHeading).toHaveBeenLastCalledWith(expect.objectContaining({ title: "Runs" }));
  });

  it("lists runs, opens run detail with hostile text escaped, and goes back", async () => {
    routes([["GET", /^\/api\/v2\/operations\/runs\/run-1234567890$/, () => ({ run: { id: "run-1234567890", task_title: "<script>window.__xss=1</script>", status: "succeeded", summary: "<b>done</b>" }, events: [{ created_at: now, tool: "<i>tool</i>" }], artifacts: [] })]]);
    const { app } = setup();
    await screen.findByText("Active Prisms");
    act(() => emit("workspace-navigate", { page: "runs" }));
    const link = await screen.findByRole("button", { name: /Hostile run/ });
    expect(link).toHaveTextContent('<img src=x onerror="window.__xss=1">Hostile run');
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getAllByText("Succeeded").length).toBeGreaterThan(0);
    await userEvent.click(link);
    expect(await screen.findByText("<script>window.__xss=1</script>")).toBeInTheDocument();
    expect(screen.getByText(/<i>tool<\/i>/)).toBeInTheDocument();
    expect(document.querySelector("script[src], b")).toBeNull();
    expect(app.routes.workspace).toHaveBeenLastCalledWith(expect.objectContaining({ page: "runs", runId: "run-1234567890" }));
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
    await userEvent.click(screen.getByRole("button", { name: "← Back to runs" }));
    await screen.findByRole("table");
  });

  it("shows the error state with a retry", async () => {
    mockFetch([
      ["GET", /overview$/, () => overview],
      ["GET", /prisms\/organization$/, () => { throw new Error("unused"); }],
    ]);
    setup();
    expect(await screen.findByText("Workspace could not load")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("decides a managed approval after confirmation and reloads", async () => {
    const managed = { id: "m1", engine_approval_id: null, prism_id: "p1", prism_name: "Sales", run_id: "r1", run_title: "Outreach", kind: "tool", status: "pending", can_decide_here: true, created_at: now, payload: { summary: "Send email <b>x</b>" } };
    const calls = routes([
      ["GET", /^\/api\/v2\/work\/approvals/, () => [managed]],
      ["POST", /^\/api\/v2\/qa\/approvals\/m1\/decision$/, () => ({})],
    ]);
    const { app } = setup();
    await screen.findByText("Active Prisms");
    act(() => emit("workspace-navigate", { page: "approvals" }));
    expect(await screen.findByText("Send email <b>x</b>")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(app.askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Approve this action?", message: "Send email <b>x</b>" }));
    await waitFor(() => expect(calls.find((c) => c.path.includes("/decision"))?.body).toEqual({ decision: "approve" }));
    await waitFor(() => expect(calls.filter((c) => c.path.startsWith("/api/v2/work/approvals")).length).toBeGreaterThan(1));
  });

  it("does nothing when the confirmation is declined", async () => {
    const managed = { id: "m1", prism_id: "p1", run_id: "r1", kind: "tool", status: "pending", can_decide_here: true, created_at: now, payload: { summary: "S" } };
    const calls = routes([["GET", /^\/api\/v2\/work\/approvals/, () => [managed]]]);
    const { app } = setup({ askDialog: vi.fn(async () => null) });
    await screen.findByText("Active Prisms");
    act(() => emit("workspace-navigate", { page: "approvals" }));
    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));
    expect(app.askDialog).toHaveBeenCalled();
    expect(calls.some((c) => c.path.includes("/decision"))).toBe(false);
  });

  it("approves and removes Brain entries with a confirmation", async () => {
    brain = [
      { id: "b1", title: "Proposed fact", body: "Learned <b>this</b>", source: "chat", status: "proposed", prism_id: null, updated_at: now },
      { id: "b2", title: "Known fact", body: "We sell widgets", source: "user", status: "approved", prism_id: null, updated_at: now },
    ];
    const calls = routes([
      ["POST", /^\/api\/v2\/brain\/b1\/approve$/, () => ({})],
      ["DELETE", /^\/api\/v2\/brain\/b2$/, () => null],
    ]);
    const { app } = setup();
    await screen.findByText("Active Prisms");
    act(() => emit("workspace-navigate", { page: "brain" }));
    expect(await screen.findByText("Learned <b>this</b>")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/v2/brain/b1/approve")).toBe(true));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(app.askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Remove from the Brain?", danger: true }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/v2/brain/b2")).toBe(true));
  });
});
