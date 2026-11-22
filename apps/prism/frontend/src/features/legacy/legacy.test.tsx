import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emit } from "@/lib/events";
import { useNavCount } from "@/lib/nav-counts";
import { AppContext } from "@/lib/app-context";
import { fakeApp, renderWithApp } from "@/test/render";
import { AskPage } from "./AskPage";
import { JourneyPage } from "./JourneyPage";
import { KnowledgePage } from "./KnowledgePage";
import { LegacyDataProvider } from "./LegacyDataProvider";
import { LegacyDialogs } from "./LegacyDialogs";
import { ManagementPage } from "./ManagementPage";
import { MemoryPage } from "./MemoryPage";
import { OverviewPage } from "./OverviewPage";
import { SetupCallout } from "./SetupCallout";
import { navigation } from "./microsoft";
import { mockFetch, reply } from "./testing";

const iso = (days: number) => new Date(Date.now() + days * 864e5).toISOString();
const ada = { id: "e1", name: "Ada Lovelace", role: "Engineer", email: "ada@example.test", is_active: true };
const bob = { id: "e2", name: "Bob Byte", role: "Designer", email: "bob@example.test", is_active: true };
const page = <T,>(items: T[]) => ({ items, total: items.length, limit: 100, offset: 0 });

const blocker = { id: "b1", description: "Waiting on API keys", severity: "high", status: "open", blocked_employee_id: "e1", dependency_owner_id: "e2", dependency_owner_ids: ["e2"] };
const commitment = { id: "c1", description: "Ship the thing", employee_id: "e1", deadline: iso(2), status: "open" };
const escalation = { id: "x1", reason: "Release at risk", escalation_type: "project_risk", severity: "high", status: "open" };
const knowledge = [
  { id: "k1", category: "team", title: "Team norms", content: "Line one\nLine two", updated_at: iso(-1), created_at: iso(-2), is_active: true },
  { id: "k2", category: "work", title: "Deployment list Q4", content: "a, b", updated_at: iso(-1), created_at: iso(-2), is_active: true },
];
const attention = [
  {
    risk: { id: "r1", severity: "high", summary: "Release slipping" },
    people: ["Ada"],
    agent_actions: [],
    impact: "Customers wait",
    current_expectation: "ETA tomorrow",
    why_visible: "Deadline near",
    manager_options: ["Ask for ETA"],
  },
];
const brief = { date: "2026-11-20", needs_attention: ["Release"], completed: [], new_blockers: ["API keys"] };
const journey = {
  blocker_id: "b1",
  title: "API keys",
  description: "Waiting",
  status: "open",
  severity: "high",
  blocked_employee_name: "Ada Lovelace",
  dependency_owner_name: null,
  started_at: iso(-3),
  last_activity_at: iso(-1),
  events: [{ event_type: "blocker_created", title: "Reported", detail: "Ada reported it", occurred_at: iso(-3) }],
  commitments: [{ id: "c1", owner_name: "Bob Byte", description: "Send keys", deadline: iso(1), status: "open" }],
};
const fact = { id: "f1", subject_text: "Ada", subject_type: "employee", predicate: "works_on", object_text: "Connector", object_type: "project", status: "current", observed_at: iso(-1) };
const episode = { id: "ep1", title: "Outage", summary: "API was down", started_at: iso(-4) };

function routes() {
  return {
    "GET /api/v2/agent/foundation": { enabled: true, threads: 3, jobs: 2, pending_approvals: 2, executions: 5, job_states: [], proposal_states: [] },
    "GET /api/v1/employees": page([ada, bob]),
    "GET /api/v1/projects": page([{ id: "p1", name: "Atlas" }]),
    "GET /api/v1/tasks": page([{ id: "t1", title: "Write docs" }]),
    "GET /api/v1/daily-updates": page([{ id: "u1", employee_id: "e2", today_summary: "Shipped a fix" }]),
    "GET /api/v1/blockers": page([blocker]),
    "GET /api/v1/commitments": page([commitment]),
    "GET /api/v1/escalations": page([escalation]),
    "GET /api/v1/management/rule-findings": [{ rule_code: "stale", reason: "Task is stale", severity: "very_high" }],
    "GET /api/v1/management/journeys": [journey],
    "GET /api/v1/management-context": page(knowledge),
    "GET /api/v1/memory/facts": page([fact]),
    "GET /api/v1/memory/episodes": [episode],
    "GET /api/v2/management/attention": attention,
    "GET /api/v2/management/brief/daily": brief,
  };
}

let net: ReturnType<typeof mockFetch>;
beforeEach(() => {
  localStorage.clear();
  net = mockFetch(routes());
});
afterEach(() => vi.unstubAllGlobals());

function NavProbe() {
  return (
    <output data-testid="counts">
      {useNavCount("today")}/{useNavCount("work")}/{useNavCount("agent")}
    </output>
  );
}

function renderLegacy(ui = <></>, app = {}) {
  const view = renderWithApp(
    <LegacyDataProvider>
      <NavProbe />
      {ui}
    </LegacyDataProvider>,
    { app },
  );
  return view;
}

const el = (id: string) => document.getElementById(id) as HTMLElement;

describe("LegacyDataProvider", () => {
  it("loads everything on mount with the old endpoints and pushes the sidebar counts", async () => {
    renderLegacy();
    await waitFor(() => expect(screen.getByTestId("counts")).toHaveTextContent("1/3/2"));
    const paths = net.calls.map((call) => call.url);
    expect(paths).toContain("/api/v1/employees?limit=100&is_active=true");
    expect(paths).toContain("/api/v1/blockers?limit=100&status=open");
    expect(paths).toContain("/api/v1/memory/facts?limit=12&status=current");
    expect(paths.some((url) => url.startsWith("/api/v1/daily-updates?limit=100&update_date=" + new Date().toISOString().slice(0, 10)))).toBe(true);
  });

  it("reloads when the shell's refreshKey changes", async () => {
    const app = fakeApp();
    const tree = (key: number) => (
      <AppContext.Provider value={{ ...app, refreshKey: key }}>
        <LegacyDataProvider>
          <NavProbe />
        </LegacyDataProvider>
      </AppContext.Provider>
    );
    const view = render(tree(0));
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/employees")).toHaveLength(1));
    view.rerender(tree(1));
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/employees")).toHaveLength(2));
  });

  it("shows the old error toast when a request fails", async () => {
    net.set("GET /api/v2/management/attention", reply(500, { detail: "database is down" }));
    const view = renderLegacy();
    await waitFor(() => expect(view.app.setStatus).toHaveBeenCalledWith("database is down. Check that the API and database are running.", true));
  });
});

describe("OverviewPage", () => {
  it("keeps the placeholders until data arrives, then fills stats, attention, brief and lists", async () => {
    renderLegacy(<OverviewPage />);
    expect(el("stat-employees")).toHaveTextContent("—");
    await waitFor(() => expect(el("stat-employees")).toHaveTextContent("2"));
    expect(el("stat-updates")).toHaveTextContent("1");
    expect(el("stat-blockers")).toHaveTextContent("1");
    expect(el("intelligence-attention-count")).toHaveTextContent("1");
    const card = el("intelligence-attention-list").querySelector("article.attention-card") as HTMLElement;
    expect(card).toHaveClass("high");
    expect(card).toHaveTextContent("Release slipping");
    expect(card).toHaveTextContent("No Prism action recorded yet");
    expect(card.querySelector(".risk-level")).toHaveTextContent("High");
    expect(card.querySelector(".manager-options")).toHaveTextContent("Ask for ETA");
    expect(el("intelligence-brief-date")).not.toBeEmptyDOMElement();
    const sections = [...el("intelligence-brief").querySelectorAll(".brief-section h3")].map((node) => node.textContent);
    expect(sections).toEqual(["Needs attention", "New blockers"]);
    expect(el("findings-list")).toHaveTextContent("Task is stale");
    expect(el("findings-list")).toHaveTextContent("very high");
    expect(el("findings-count")).toHaveTextContent("1");
  });

  it("lists people without an update with a reminder action that is recorded, not sent", async () => {
    renderLegacy(<OverviewPage />, { modes: { v21: false, v22: false, v24: false, singleExecutive: false } });
    await waitFor(() => expect(el("missing-updates-count")).toHaveTextContent("1"));
    expect(el("missing-updates-list")).toHaveTextContent("Ada Lovelace");
    expect(el("missing-updates-list")).toHaveTextContent("Engineer has not sent an update today.");
    net.set("POST /api/v1/message-intents", {});
    const button = within(el("missing-updates-list")).getByRole("button", { name: "Record Teams reminder" });
    expect(button).toHaveAttribute("data-action", "daily-reminder");
    expect(button).toHaveAttribute("data-id", "e1");
    expect(button).toHaveAttribute("data-tooltip", "Send this person a simple Teams reminder for today's update.");
    await userEvent.click(button);
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/message-intents")).toHaveLength(1));
    expect(net.callsTo("POST", "/api/v1/message-intents")[0].body).toEqual({
      employee_id: "e1",
      channel: "teams",
      content: "Hi Ada Lovelace, please share your daily update for today: what you completed, what you will deliver today, and any blockers.",
    });
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/employees")).toHaveLength(2));
  });

  it("empty brief and attention show their messages", async () => {
    net.set("GET /api/v2/management/attention", []);
    net.set("GET /api/v2/management/brief/daily", { date: "2026-11-20" });
    renderLegacy(<OverviewPage />);
    await waitFor(() => expect(el("intelligence-brief")).toHaveTextContent("No material management changes recorded today."));
    expect(el("intelligence-attention-list")).toHaveClass("attention-list", "empty-state");
    expect(el("intelligence-attention-list")).toHaveTextContent("Nothing currently needs your intervention.");
  });

  it("Refresh intelligence posts and reports", async () => {
    net.set("POST /api/v2/management/intelligence/run", { active_risks: 2, decisions_created: 1, no_action: 0 });
    const view = renderLegacy(<OverviewPage />, { modes: { v21: false, v22: false, v24: false, singleExecutive: false } });
    await userEvent.click(screen.getByRole("button", { name: "Refresh intelligence" }));
    await waitFor(() =>
      expect(view.app.setStatus).toHaveBeenCalledWith("Intelligence refreshed: 2 active risk(s), 1 new decision(s), 0 no-action decision(s). No Teams messages were sent."),
    );
  });

  it("gates the v2.1 panel and the legacy block by mode", async () => {
    renderLegacy(<OverviewPage />, { modes: { v21: true, v22: false, v24: false, singleExecutive: false } });
    expect(document.querySelector(".today-agent")).not.toHaveAttribute("hidden");
    expect(el("legacy-today")).not.toHaveAttribute("hidden");
  });

  it("hides the legacy block with v2.2 and the Prism panel without v2.1", () => {
    renderLegacy(<OverviewPage />);
    expect(el("legacy-today")).toHaveAttribute("hidden");
    expect(document.querySelector(".today-agent")).toHaveAttribute("hidden");
    expect(document.querySelector(".today-agent")).toHaveAttribute("data-v21-only");
  });
});

describe("agent foundation", () => {
  it("shows the counters, the approvals banner and the nav badge", async () => {
    renderLegacy(<OverviewPage />, { modes: { v21: true, v22: false, v24: false, singleExecutive: false } });
    const panel = el("agent-foundation-panel");
    expect(panel).toHaveAttribute("hidden");
    await waitFor(() => expect(panel).not.toHaveAttribute("hidden"));
    expect(el("foundation-thread-count")).toHaveTextContent("3");
    expect(el("foundation-job-count")).toHaveTextContent("2");
    expect(el("foundation-approval-count")).toHaveTextContent("2");
    expect(el("foundation-execution-count")).toHaveTextContent("5");
    expect(el("approval-banner-title")).toHaveTextContent("2 drafts waiting for your approval");
    expect(el("approval-banner-text")).toHaveTextContent("Open Prism to review each draft");
    expect(el("approval-banner-button")).toHaveTextContent("Review drafts");
    expect(el("approval-banner-button")).not.toHaveClass("secondary");
  });

  it("the banner button opens the agent when drafts wait, or starts a chat otherwise", async () => {
    const view = renderLegacy(<OverviewPage />, { modes: { v21: true, v22: false, v24: false, singleExecutive: false } });
    await waitFor(() => expect(el("approval-banner-button")).toHaveTextContent("Review drafts"));
    await userEvent.click(el("approval-banner-button"));
    expect(view.app.setActiveTab).toHaveBeenCalledWith("agent");
  });

  it("starts a review when nothing waits and follows agent-changed events", async () => {
    net.set("GET /api/v2/agent/foundation", { enabled: true, threads: 0, jobs: 0, pending_approvals: 0, executions: 0, job_states: [], proposal_states: [] });
    const started = vi.fn();
    const { on } = await import("@/lib/events");
    const off = on("new-chat", started);
    renderLegacy(<OverviewPage />, { modes: { v21: true, v22: false, v24: false, singleExecutive: false } });
    await waitFor(() => expect(el("approval-banner-title")).toHaveTextContent("No drafts waiting"));
    expect(el("approval-banner-button")).toHaveTextContent("Start a review");
    expect(el("approval-banner-button")).toHaveClass("secondary");
    await userEvent.click(el("approval-banner-button"));
    expect(started).toHaveBeenCalled();
    net.set("GET /api/v2/agent/foundation", { enabled: true, threads: 1, jobs: 1, pending_approvals: 1, executions: 0, job_states: [], proposal_states: [] });
    act(() => emit("agent-changed"));
    await waitFor(() => expect(el("approval-banner-title")).toHaveTextContent("1 draft waiting for your approval"));
    expect(screen.getByTestId("counts")).toHaveTextContent("/1");
    off();
  });

  it("shows the single Prism conversation row and opens the agent from it", async () => {
    net.set("GET /api/v2/agent/conversation", { id: "th1", source_label: "Chat with Bob", updated_at: iso(-1) });
    const view = renderLegacy(<OverviewPage />, { modes: { v21: true, v22: false, v24: false, singleExecutive: false } });
    const row = await screen.findByText("Continue with Prism");
    expect(el("today-thread-list")).toHaveClass("list");
    expect(el("today-thread-list")).toHaveTextContent("Source constraint: Chat with Bob");
    await userEvent.click(row);
    expect(view.app.setActiveTab).toHaveBeenCalledWith("agent");
  });

  it("hides the panel when the foundation is unavailable", async () => {
    net.set("GET /api/v2/agent/foundation", reply(404, { detail: "off" }));
    renderLegacy(<OverviewPage />);
    await waitFor(() => expect(el("stat-employees")).toHaveTextContent("2"));
    expect(el("agent-foundation-panel")).toHaveAttribute("hidden");
  });
});

describe("setup callout", () => {
  it("lists the Microsoft step with a Connect button", async () => {
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    renderLegacy(<SetupCallout />, { microsoft: { is_connected: false, is_auth_configured: true, connection: null } });
    const box = document.querySelector("[data-setup]") as HTMLElement;
    expect(box).not.toHaveAttribute("hidden");
    expect(box).toHaveTextContent("Finish setting up Prism");
    await userEvent.click(within(box).getByRole("button", { name: "Connect Microsoft account" }));
    expect(assign).toHaveBeenCalledWith("/api/v1/microsoft/auth/start");
  });

  it("explains missing Microsoft configuration without a button", () => {
    renderLegacy(<SetupCallout />, { microsoft: { is_connected: false, is_auth_configured: false, connection: null } });
    const box = document.querySelector("[data-setup]") as HTMLElement;
    expect(box).toHaveTextContent("Add the Microsoft settings to .env and restart the API to connect Teams.");
    expect(within(box).queryByRole("button")).toBeNull();
  });

  it("adds the provider step for v2.1 and opens settings on it", async () => {
    const view = renderLegacy(<SetupCallout />, {
      modes: { v21: true, v22: false, v24: false, singleExecutive: false },
      microsoft: { is_connected: true, is_auth_configured: true, connection: {} },
      providerStatus: { provider: "openai", model: null, state: "not_configured", ready: false, detail: "No key" },
    });
    expect(document.querySelector("[data-setup]")).toHaveTextContent("AI provider: No key");
    await userEvent.click(screen.getByRole("button", { name: "Open settings" }));
    expect(view.app.settings.open).toHaveBeenCalledWith("provider");
  });

  it("is hidden when everything is ready", () => {
    renderLegacy(<SetupCallout />, { microsoft: { is_connected: true, is_auth_configured: true, connection: {} } });
    expect(document.querySelector("[data-setup]")).toHaveAttribute("hidden");
  });
});

describe("ManagementPage lists and actions", () => {
  async function ready() {
    const view = renderLegacy(<><ManagementPage /><LegacyDialogs /></>);
    await waitFor(() => expect(el("blockers-list")).toHaveTextContent("Waiting on API keys"));
    return view;
  }

  it("renders every list with names resolved and counts in the badges", async () => {
    await ready();
    expect(el("blockers-list")).toHaveTextContent("Blocked: Ada Lovelace · Dependency owner: Bob Byte · Severity: high");
    expect(el("commitments-list")).toHaveTextContent("Responsible: Ada Lovelace · Deadline:");
    expect(el("commitments-list")).toHaveTextContent("Status: open");
    expect(el("escalations-list")).toHaveTextContent("project risk · high");
    expect(el("updates-list")).toHaveTextContent("Bob Byte");
    expect(el("updates-list")).toHaveTextContent("Shipped a fix");
    for (const id of ["blockers-count", "commitments-count", "escalations-count", "updates-count"]) expect(el(id)).toHaveTextContent("1");
    expect(el("blockers-list")).toHaveClass("list");
  });

  it("shows the empty texts", async () => {
    net.set("GET /api/v1/blockers", page([]));
    net.set("GET /api/v1/escalations", page([]));
    renderLegacy(<ManagementPage />);
    await waitFor(() => expect(el("blockers-list")).toHaveTextContent("No open blockers."));
    expect(el("blockers-list")).toHaveClass("empty-state");
    expect(el("escalations-list")).toHaveTextContent("No open escalations.");
  });

  it("Mark resolved confirms, PATCHes and reloads", async () => {
    net.set("PATCH /api/v1/blockers/b1", {});
    const view = await ready();
    await userEvent.click(screen.getByRole("button", { name: "Mark resolved" }));
    expect(view.app.askDialog).toHaveBeenCalledWith({ title: "Mark blocker as resolved?", confirmLabel: "Resolve" });
    await waitFor(() => expect(net.callsTo("PATCH", "/api/v1/blockers/b1")).toHaveLength(1));
    expect(net.callsTo("PATCH", "/api/v1/blockers/b1")[0].body).toEqual({ status: "resolved" });
    expect(view.app.setStatus).toHaveBeenCalledWith("Blocker marked as resolved. Update the task status separately when work resumes.");
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/blockers")).toHaveLength(2));
  });

  it("does nothing when the confirmation is declined", async () => {
    const view = renderLegacy(<ManagementPage />, { askDialog: vi.fn(async () => null) });
    await waitFor(() => expect(el("blockers-list")).toHaveTextContent("Waiting on API keys"));
    await userEvent.click(screen.getByRole("button", { name: "Mark resolved" }));
    expect(net.callsTo("PATCH", "/api/v1/blockers/b1")).toHaveLength(0);
    expect(view.app.setStatus).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Mark resolved" })).toBeEnabled();
  });

  it("records a follow-up message intent for the dependency owner", async () => {
    net.set("POST /api/v1/message-intents", {});
    await ready();
    await userEvent.click(screen.getByRole("button", { name: "Record Teams follow-up" }));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/message-intents")).toHaveLength(1));
    expect(net.callsTo("POST", "/api/v1/message-intents")[0].body).toEqual({
      employee_id: "e2",
      channel: "teams",
      content: "Hi Bob Byte, Ada Lovelace is blocked: Waiting on API keys Please share a specific ETA.",
    });
  });

  it("Mark missed sends the trimmed reason, or an empty body when blank", async () => {
    net.set("POST /api/v1/commitments/c1/mark-missed", {});
    const view = renderLegacy(<ManagementPage />, { askDialog: vi.fn(async () => "  slipped  ") });
    await waitFor(() => expect(el("commitments-list")).toHaveTextContent("Ship the thing"));
    await userEvent.click(screen.getByRole("button", { name: "Mark missed" }));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/commitments/c1/mark-missed")).toHaveLength(1));
    expect(net.callsTo("POST", "/api/v1/commitments/c1/mark-missed")[0].body).toEqual({ reason: "slipped" });
    expect(view.app.setStatus).toHaveBeenCalledWith("Commitment marked as missed. It remains in its history.");
    (view.app.askDialog as ReturnType<typeof vi.fn>).mockResolvedValue("");
    await userEvent.click(screen.getByRole("button", { name: "Mark missed" }));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/commitments/c1/mark-missed")).toHaveLength(2));
    expect(net.callsTo("POST", "/api/v1/commitments/c1/mark-missed")[1].body).toEqual({});
  });

  it("Acknowledge and Resolve escalations", async () => {
    net.set("POST /api/v1/escalations/x1/acknowledge", {});
    net.set("POST /api/v1/escalations/x1/resolve", {});
    const view = await ready();
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(view.app.setStatus).toHaveBeenCalledWith("Escalation acknowledged."));
    await userEvent.click(within(el("escalations-list")).getByRole("button", { name: "Resolve" }));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/escalations/x1/resolve")).toHaveLength(1));
    expect(view.app.setStatus).toHaveBeenCalledWith("Escalation resolved.");
  });

  it("surfaces a failed action and re-enables the button", async () => {
    net.set("POST /api/v1/escalations/x1/acknowledge", reply(409, { detail: "Already handled" }));
    const view = await ready();
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(view.app.setStatus).toHaveBeenCalledWith("Already handled", true));
    expect(screen.getByRole("button", { name: "Acknowledge" })).toBeEnabled();
  });

  it("Missed + revised ETA opens the revision dialog and saves both steps", async () => {
    net.set("POST /api/v1/commitments/c1/mark-missed", {});
    net.set("POST /api/v1/commitments/c1/revisions", {});
    const view = await ready();
    const dialog = el("revision-dialog") as HTMLDialogElement;
    expect(dialog).not.toHaveAttribute("open");
    await userEvent.click(screen.getByRole("button", { name: "Missed + revised ETA" }));
    expect(dialog).toHaveAttribute("open");
    await userEvent.type(el("revision-reason"), "Vendor delay");
    await userEvent.type(el("revision-description"), "Ship next week");
    await userEvent.type(el("revision-deadline"), "2026-12-01T10:00");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save revised ETA" }));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/commitments/c1/revisions")).toHaveLength(1));
    expect(net.callsTo("POST", "/api/v1/commitments/c1/mark-missed")[0].body).toEqual({ reason: "Vendor delay" });
    const revision = net.callsTo("POST", "/api/v1/commitments/c1/revisions")[0].body as Record<string, string>;
    expect(revision.description).toBe("Ship next week");
    expect(revision.missed_reason).toBe("Vendor delay");
    expect(revision.deadline).toBe(new Date("2026-12-01T10:00").toISOString());
    expect(view.app.setStatus).toHaveBeenCalledWith("Missed commitment and revised ETA saved with full history.");
    await waitFor(() => expect(dialog).not.toHaveAttribute("open"));
  });

  it("Cancel closes the revision dialog and the next open starts empty", async () => {
    await ready();
    await userEvent.click(screen.getByRole("button", { name: "Missed + revised ETA" }));
    await userEvent.type(el("revision-reason"), "typed");
    await userEvent.click(el("revision-cancel"));
    expect(el("revision-dialog")).not.toHaveAttribute("open");
    await userEvent.click(screen.getByRole("button", { name: "Missed + revised ETA" }));
    expect(el("revision-reason")).toHaveValue("");
  });
});

describe("record dialog", () => {
  async function openRecord() {
    const view = renderLegacy(<><ManagementPage /><LegacyDialogs /></>);
    await waitFor(() => expect(el("blockers-list")).toHaveTextContent("Waiting on API keys"));
    await userEvent.click(el("new-record-button"));
    return view;
  }

  it("opens with the employee form and offers all seven kinds", async () => {
    await openRecord();
    expect(el("record-dialog")).toHaveAttribute("open");
    expect(el("record-dialog")).toHaveClass("wide");
    expect([...(el("form-selector") as HTMLSelectElement).options].map((option) => option.value)).toEqual([
      "employee",
      "project",
      "task",
      "daily-update",
      "blocker",
      "commitment",
      "escalation",
    ]);
    expect(el("form-container").querySelector("form")).toHaveAttribute("data-endpoint", "/api/v1/employees");
  });

  it("fills select options from the loaded records", async () => {
    await openRecord();
    await userEvent.selectOptions(el("form-selector"), "task");
    const owner = el("form-container").querySelector("select[name=owner_id]") as HTMLSelectElement;
    expect([...owner.options].map((option) => option.textContent)).toEqual(["Choose an employee", "Ada Lovelace — Engineer", "Bob Byte — Designer"]);
    expect(owner).toBeRequired();
    const project = el("form-container").querySelector("select[name=project_id]") as HTMLSelectElement;
    expect([...project.options].map((option) => option.textContent)).toEqual(["No project", "Atlas"]);
    await userEvent.selectOptions(el("form-selector"), "commitment");
    const blockerSelect = el("form-container").querySelector("select[name=blocker_id]") as HTMLSelectElement;
    expect([...blockerSelect.options].map((option) => option.textContent)).toEqual(["Not linked to a blocker", "Waiting on API keys"]);
  });

  it("prefills today's date on daily updates", async () => {
    await openRecord();
    await userEvent.selectOptions(el("form-selector"), "daily-update");
    expect(el("form-container").querySelector("input[name=update_date]")).toHaveValue(new Date().toISOString().slice(0, 10));
  });

  it("submits trimmed non-empty values, then closes, toasts and reloads", async () => {
    net.set("POST /api/v1/employees", {});
    const view = await openRecord();
    const form = el("form-container");
    await userEvent.type(form.querySelector("input[name=name]") as HTMLElement, "  New Hire ");
    await userEvent.type(form.querySelector("input[name=email]") as HTMLElement, "new@example.test");
    await userEvent.type(form.querySelector("input[name=role]") as HTMLElement, "Engineer");
    await userEvent.click(within(form).getByRole("button", { name: "Add employee" }));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/employees")).toHaveLength(1));
    expect(net.callsTo("POST", "/api/v1/employees")[0].body).toEqual({ name: "New Hire", email: "new@example.test", role: "Engineer" });
    expect(view.app.setStatus).toHaveBeenCalledWith("Saved successfully.");
    await waitFor(() => expect(el("record-dialog")).not.toHaveAttribute("open"));
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/employees")).toHaveLength(2));
  });

  it("converts the deadline to an ISO timestamp", async () => {
    net.set("POST /api/v1/tasks", {});
    await openRecord();
    await userEvent.selectOptions(el("form-selector"), "task");
    const form = el("form-container");
    await userEvent.type(form.querySelector("input[name=title]") as HTMLElement, "T");
    await userEvent.type(form.querySelector("textarea[name=expected_outcome]") as HTMLElement, "Done");
    await userEvent.selectOptions(form.querySelector("select[name=owner_id]") as HTMLElement, "e1");
    await userEvent.type(form.querySelector("input[name=deadline]") as HTMLElement, "2026-12-01T10:00");
    await userEvent.click(within(form).getByRole("button", { name: "Add task" }));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/tasks")).toHaveLength(1));
    expect(net.callsTo("POST", "/api/v1/tasks")[0].body).toEqual({
      title: "T",
      expected_outcome: "Done",
      owner_id: "e1",
      priority: "medium",
      deadline: new Date("2026-12-01T10:00").toISOString(),
    });
  });

  it("closes with the Close button", async () => {
    await openRecord();
    await userEvent.click(el("record-close"));
    expect(el("record-dialog")).not.toHaveAttribute("open");
  });
});

describe("JourneyPage", () => {
  it("renders cards with status, people and an ordered event trail", async () => {
    renderLegacy(<JourneyPage />);
    await waitFor(() => expect(el("journeys-count")).toHaveTextContent("1"));
    const card = el("journeys-list").querySelector("details.journey-card") as HTMLElement;
    expect(card.querySelector(".journey-status")).toHaveClass("open");
    expect(card.querySelector(".journey-status")).toHaveTextContent("Open");
    expect(card).toHaveTextContent("Blocked: Ada");
    expect(card).toHaveTextContent("Dependency: owner");
    expect(card.querySelector(".journey-event.blocker_created .journey-tag")).toHaveTextContent("blocker created");
    expect(card.querySelector(".journey-number")).toHaveTextContent("1");
    expect(card.querySelector(".journey-commitments")).toHaveTextContent("Bob Byte committed: Send keys · due");
  });

  it("the dummy preview adds a journey and keeps the button label", async () => {
    net.set("POST /api/v1/management/dummy-journey", { blocker_id: "dummy", created: true, message: "Preview ready", journey: { ...journey, blocker_id: "dummy", title: "Sample flow" } });
    const view = renderLegacy(<JourneyPage />);
    await waitFor(() => expect(el("journeys-count")).toHaveTextContent("1"));
    await userEvent.click(el("create-dummy-journey-button"));
    await waitFor(() => expect(el("journeys-count")).toHaveTextContent("2"));
    expect(el("create-dummy-journey-button")).toHaveTextContent("Preview created");
    expect(el("journeys-list").querySelector("details")).toHaveTextContent("Sample flow");
    expect(view.app.setStatus).toHaveBeenCalledWith("Preview ready");
  });

  it("shows the empty state", async () => {
    net.set("GET /api/v1/management/journeys", []);
    renderLegacy(<JourneyPage />);
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/management/journeys")).toHaveLength(1));
    expect(el("journeys-list")).toHaveTextContent("No blocker journeys recorded yet.");
  });
});

describe("KnowledgePage", () => {
  async function ready(app = {}) {
    const view = renderLegacy(<KnowledgePage />, app);
    await waitFor(() => expect(el("knowledge-count")).toHaveTextContent("2"));
    return view;
  }
  const field = (name: string) => document.querySelector(`#knowledge-context-form [name=${name}]`) as HTMLInputElement;

  it("lists entries with category, multi-line content and per-entry actions", async () => {
    await ready();
    const entries = el("knowledge-list").querySelectorAll("article.knowledge-entry");
    expect(entries).toHaveLength(2);
    expect(entries[0].querySelector(".knowledge-category")).toHaveClass("knowledge-category", "team");
    expect(entries[0].querySelector(".knowledge-category")).toHaveTextContent("Team context");
    expect(entries[0].querySelector("p")?.innerHTML).toBe("Line one<br>Line two");
    expect(within(entries[0] as HTMLElement).queryByRole("button", { name: "Distribute list" })).toBeNull();
    expect(within(entries[1] as HTMLElement).getByRole("button", { name: "Distribute list" })).toHaveAttribute("data-knowledge-action", "distribute");
    expect(within(entries[0] as HTMLElement).getByRole("button", { name: "Delete" })).toHaveClass("mini-button", "danger-button");
  });

  it("creates an entry with the trimmed values and resets the form", async () => {
    net.set("POST /api/v1/management-context", {});
    await ready();
    await userEvent.selectOptions(field("category"), "people");
    await userEvent.type(field("title"), "  New title ");
    await userEvent.type(field("content"), "Body text ");
    await userEvent.click(el("knowledge-submit-button"));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/management-context")).toHaveLength(1));
    expect(net.callsTo("POST", "/api/v1/management-context")[0].body).toEqual({ category: "people", title: "New title", content: "Body text" });
    await waitFor(() => expect(field("title")).toHaveValue(""));
    expect(field("category")).toHaveValue("team");
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/management-context")).toHaveLength(2));
  });

  it("Edit loads the entry, switches the button labels and PATCHes", async () => {
    net.set("PATCH /api/v1/management-context/k1", {});
    await ready();
    expect(el("cancel-knowledge-edit")).toHaveAttribute("hidden");
    await userEvent.click(within(el("knowledge-list")).getAllByRole("button", { name: "Edit" })[0]);
    expect(field("title")).toHaveValue("Team norms");
    expect(field("content")).toHaveValue("Line one\nLine two");
    expect(el("knowledge-submit-button")).toHaveTextContent("Update context");
    expect(el("cancel-knowledge-edit")).not.toHaveAttribute("hidden");
    await userEvent.clear(field("title"));
    await userEvent.type(field("title"), "Renamed");
    await userEvent.click(el("knowledge-submit-button"));
    await waitFor(() => expect(net.callsTo("PATCH", "/api/v1/management-context/k1")).toHaveLength(1));
    expect(net.callsTo("PATCH", "/api/v1/management-context/k1")[0].body).toEqual({ category: "team", title: "Renamed", content: "Line one\nLine two" });
    await waitFor(() => expect(el("knowledge-submit-button")).toHaveTextContent("Save context"));
  });

  it("Cancel leaves edit mode", async () => {
    await ready();
    await userEvent.click(within(el("knowledge-list")).getAllByRole("button", { name: "Edit" })[0]);
    await userEvent.click(el("cancel-knowledge-edit"));
    expect(field("title")).toHaveValue("");
    expect(el("knowledge-submit-button")).toHaveTextContent("Save context");
  });

  it("Delete asks with the entry title, then DELETEs and reloads", async () => {
    net.set("DELETE /api/v1/management-context/k1", null);
    const view = await ready();
    await userEvent.click(within(el("knowledge-list")).getAllByRole("button", { name: "Delete" })[0]);
    expect(view.app.askDialog).toHaveBeenCalledWith({
      title: "Delete “Team norms”?",
      message: "It will be removed from Prism's saved knowledge.",
      confirmLabel: "Delete",
      danger: true,
    });
    await waitFor(() => expect(net.callsTo("DELETE", "/api/v1/management-context/k1")).toHaveLength(1));
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/management-context")).toHaveLength(2));
  });

  it("Delete does nothing when declined", async () => {
    await ready({ askDialog: vi.fn(async () => null) });
    await userEvent.click(within(el("knowledge-list")).getAllByRole("button", { name: "Delete" })[0]);
    expect(net.callsTo("DELETE", "/api/v1/management-context/k1")).toHaveLength(0);
  });

  it("Distribute list reports delivered, skipped and failures", async () => {
    net.set("POST /api/v1/management-context/k2/distribute-deployment-list", { delivered: [1, 2], skipped: [3], failures: [4], task_changes: 5 });
    const view = await ready();
    await userEvent.click(screen.getByRole("button", { name: "Distribute list" }));
    expect(view.app.askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Distribute “Deployment list Q4”?", confirmLabel: "Distribute" }));
    await waitFor(() =>
      expect(view.app.setStatus).toHaveBeenCalledWith(
        "Deployment list: 2 delivered, 1 already delivered, 5 task change(s). 1 delivery failure(s); task state was not changed.",
        true,
      ),
    );
  });

  it("shows an error toast when saving fails", async () => {
    net.set("POST /api/v1/management-context", reply(422, { detail: "Title too long" }));
    const view = await ready();
    await userEvent.type(field("title"), "T");
    await userEvent.type(field("content"), "C");
    await userEvent.click(el("knowledge-submit-button"));
    await waitFor(() => expect(view.app.setStatus).toHaveBeenCalledWith("Title too long", true));
    expect(field("title")).toHaveValue("T");
  });

  it("empty list uses the old texts before and after the first load", async () => {
    net.set("GET /api/v1/management-context", page([]));
    renderLegacy(<KnowledgePage />);
    expect(el("knowledge-list")).toHaveTextContent("No context saved yet.");
    await waitFor(() => expect(el("knowledge-list")).toHaveTextContent("No context saved yet. Add something Prism should remember."));
  });
});

describe("AskPage", () => {
  it("posts the trimmed question and renders type, answer, uncertainty and evidence", async () => {
    net.set("POST /api/v2/management/query", { answer_type: "blocked_people", answer: "Ada is blocked.", uncertainty: "Not sure about Bob", evidence: ["Msg 1", "Msg 2"] });
    renderLegacy(<AskPage />);
    expect(el("management-query-results")).toHaveAttribute("hidden");
    await userEvent.type(el("management-query-input"), "  Who is blocked?  {Enter}");
    await waitFor(() => expect(el("management-query-results")).not.toHaveAttribute("hidden"));
    expect(net.callsTo("POST", "/api/v2/management/query")[0].body).toEqual({ question: "Who is blocked?" });
    const box = el("management-query-results");
    expect(box.querySelector(".answer-type")).toHaveTextContent("Blocked People");
    expect(box).toHaveTextContent("Ada is blocked.");
    expect(box.querySelector(".query-uncertainty")).toHaveTextContent("Not sure about Bob");
    expect(box.querySelector("summary")).toHaveTextContent("Evidence (2)");
  });

  it("suggestions fill the box and ask immediately", async () => {
    net.set("POST /api/v2/management/query", { answer_type: "x", answer: "ok" });
    renderLegacy(<AskPage />);
    await userEvent.click(screen.getByRole("button", { name: "What changed today?" }));
    expect(el("management-query-input")).toHaveValue("What changed today?");
    await waitFor(() => expect(net.callsTo("POST", "/api/v2/management/query")).toHaveLength(1));
  });

  it("an empty question asks nothing, errors toast", async () => {
    net.set("POST /api/v2/management/query", reply(500, { detail: "model offline" }));
    const view = renderLegacy(<AskPage />);
    await userEvent.type(el("management-query-input"), "Anything{Enter}");
    await waitFor(() => expect(view.app.setStatus).toHaveBeenCalledWith("model offline", true));
  });
});

describe("MemoryPage", () => {
  it("renders facts and episodes, and fills the team member select", async () => {
    renderLegacy(<MemoryPage />);
    await waitFor(() => expect(el("memory-facts-list")).toHaveTextContent("Ada works on Connector"));
    expect(el("memory-facts-list")).toHaveTextContent("current · observed");
    expect(el("memory-episodes-list")).toHaveTextContent("Outage");
    expect(el("memory-episodes-list")).toHaveTextContent("API was down ·");
    expect([...(el("memory-employee-select") as HTMLSelectElement).options].map((option) => option.textContent)).toEqual(["Choose a team member", "Ada Lovelace", "Bob Byte"]);
  });

  it("search shows facts and past situations, or the empty text", async () => {
    net.set("GET /api/v1/memory/search", { facts: [fact], episodes: [episode], relations: [] });
    renderLegacy(<MemoryPage />);
    await userEvent.type(el("memory-search-input"), "connector api{Enter}");
    await waitFor(() => expect(el("memory-search-results")).not.toHaveAttribute("hidden"));
    expect(net.callsTo("GET", "/api/v1/memory/search")[0].url).toBe("/api/v1/memory/search?q=connector%20api&include_history=true");
    expect(el("memory-search-results")).toHaveTextContent("Facts");
    expect(el("memory-search-results")).toHaveTextContent("Past situations");
    net.set("GET /api/v1/memory/search", { facts: [], episodes: [], relations: [] });
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(el("memory-search-results")).toHaveTextContent("Nothing matched that search yet."));
  });

  it("Update memory backfills then consolidates and reports the totals", async () => {
    net.set("POST /api/v1/memory/backfill", { messages: 3, tasks: 2 });
    net.set("POST /api/v1/memory/consolidate", { processed: 7, facts: 4, episodes: 1, relations: 2 });
    const view = renderLegacy(<MemoryPage />);
    await userEvent.click(el("consolidate-memory-button"));
    await waitFor(() =>
      expect(view.app.setStatus).toHaveBeenCalledWith(
        "Memory updated: 5 existing record(s) queued; 7 event(s) processed, 4 fact(s), 1 situation(s), and 2 relationship(s) added.",
      ),
    );
  });

  it("loads the context preview as plain text sections", async () => {
    net.set("GET /api/v1/memory/context/e1", { employee_id: "e1", current_work: ["Atlas"], current_blockers: [], relevant_facts: ["Likes tests"] });
    renderLegacy(<MemoryPage />);
    await waitFor(() => expect(within(el("memory-employee-select")).getByRole("option", { name: "Ada Lovelace" })).toBeInTheDocument());
    expect(el("memory-context-output")).toHaveTextContent("Choose a team member to see their limited working context.");
    await userEvent.click(el("load-memory-context-button"));
    expect(net.callsTo("GET", "/api/v1/memory/context/e1")).toHaveLength(0);
    await userEvent.selectOptions(el("memory-employee-select"), "e1");
    await userEvent.click(el("load-memory-context-button"));
    await waitFor(() => expect(el("memory-context-output").textContent).toBe("Current work\n- Atlas\n\nRelevant memory\n- Likes tests"));
  });

  it("says when there is no context and when loading failed", async () => {
    net.set("GET /api/v1/memory/context/e1", { employee_id: "e1" });
    const view = renderLegacy(<MemoryPage />);
    await waitFor(() => expect(within(el("memory-employee-select")).getByRole("option", { name: "Ada Lovelace" })).toBeInTheDocument());
    await userEvent.selectOptions(el("memory-employee-select"), "e1");
    await userEvent.click(el("load-memory-context-button"));
    await waitFor(() => expect(el("memory-context-output")).toHaveTextContent("No relevant context is available yet."));
    net.set("GET /api/v1/memory/context/e1", reply(500, { detail: "boom" }));
    await userEvent.click(el("load-memory-context-button"));
    await waitFor(() => expect(el("memory-context-output")).toHaveTextContent("Could not load context."));
    expect(view.app.setStatus).toHaveBeenCalledWith("boom", true);
  });
});

describe("untrusted text stays text", () => {
  const evil = `<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script>`;

  it("never turns Teams/model strings into markup anywhere", async () => {
    net.set("GET /api/v1/employees", page([{ ...ada, name: evil, role: evil }]));
    net.set("GET /api/v1/blockers", page([{ ...blocker, description: evil }]));
    net.set("GET /api/v1/commitments", page([{ ...commitment, description: evil }]));
    net.set("GET /api/v1/escalations", page([{ ...escalation, reason: evil }]));
    net.set("GET /api/v1/management-context", page([{ ...knowledge[0], title: evil, content: evil, category: "team" }]));
    net.set("GET /api/v2/management/attention", [{ ...attention[0], risk: { ...attention[0].risk, summary: evil, severity: "high" }, impact: evil, people: [evil], manager_options: [evil] }]);
    net.set("GET /api/v2/management/brief/daily", { date: "2026-11-20", needs_attention: [evil] });
    net.set("GET /api/v1/management/journeys", [{ ...journey, title: evil, description: evil, events: [{ ...journey.events[0], title: evil, detail: evil }] }]);
    net.set("GET /api/v1/memory/facts", page([{ ...fact, subject_text: evil }]));
    renderLegacy(
      <>
        <OverviewPage />
        <ManagementPage />
        <KnowledgePage />
        <JourneyPage />
        <MemoryPage />
      </>,
    );
    await waitFor(() => expect(el("knowledge-count")).toHaveTextContent("1"));
    await waitFor(() => expect(el("blockers-list")).toHaveTextContent("<img src=x"));
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    expect(el("intelligence-brief")).toHaveTextContent("<img");
    expect(el("knowledge-list")).toHaveTextContent("<img");
    expect(el("journeys-list")).toHaveTextContent("<img");
    expect(el("memory-facts-list")).toHaveTextContent("<img");
  });
});
