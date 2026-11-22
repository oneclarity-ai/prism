import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { renderWithApp } from "@/test/render";
import { emit } from "@/lib/events";
import { setPref } from "@/lib/prefs";
import { AgentPage } from "./AgentPage";
import {
  conversationRoutes,
  evidence,
  installFetch,
  job,
  json,
  message,
  PRISM,
  proposal,
  review,
  thread,
  type Conversation,
  type Handler,
} from "./testkit";

function mount(data: Conversation, extra: Record<string, Handler> = {}, appOverrides = {}) {
  const fetcher = installFetch({ ...conversationRoutes("p1", data), ...extra });
  const view = renderWithApp(<AgentPage />, { app: { activeTab: "agent", ...appOverrides } });
  return { ...view, ...fetcher };
}

const open = async (prism: Record<string, unknown> = PRISM) => {
  await act(async () => {
    emit("open-agent", { prism: prism as typeof PRISM });
  });
};

afterEach(() => {
  setPref("enter-newline", null);
});

// The scope editor needs the Prism directory provider and is covered by the prisms feature tests.
vi.mock("@/features/prisms/ScopePanel", () => ({ ScopePanel: () => <div id="prism-policy-dialog" /> }));

const empty = (): Conversation => ({ thread: thread(), messages: [], jobs: [] });

describe("message stream", () => {
  it("renders every message kind", async () => {
    const jobs = [
      job("j1", { sources: [{ external_id: "c1", label: "Release group", selection_reason: "auto" }] }),
      job("j2"),
      job("j3"),
      job("j4", { state: "failed", safe_error_code: "microsoft_reconnect_required", safe_error_detail: "Reconnect" }),
    ];
    const planActions = [
      { proposal: proposal("a1", "j3", "Parv Pareek", { sequence: 1 }), execution: null },
      { proposal: proposal("a2", "j3", "Meera Shah", { sequence: 2 }), execution: null },
    ];
    const data: Conversation = {
      thread: thread(),
      jobs,
      messages: [
        message("m0", "assistant", "Hello, I am ready.", null, 0),
        message("m1", "manager", "What needs my attention?", "j1", 1),
        message("m2", "assistant", "x", "j1", 2, { kind: "conversation_review" }),
        message("m3", "manager", "Draft to Parv", "j2", 3),
        message("m4", "assistant", "x", "j2", 4, { kind: "conversation_review" }),
        message("m5", "manager", "Draft to both", "j3", 5),
        message("m6", "assistant", "x", "j3", 6, { kind: "conversation_review" }),
        message("m7", "manager", "Anything else?", "j4", 7),
      ],
      evidence: { j1: [evidence()], j2: [evidence()], j3: [evidence()] },
      reviews: {
        j1: review({
          attention_items: [
            { kind: "direct", title: "Schema is late", detail: "Parv promised Friday", evidence_ids: ["e1"] },
            { kind: "conflict", title: "Two dates", detail: "", evidence_ids: [] },
          ],
          manager_questions: [{ question: "Who owns the rollout?", evidence_ids: [] }],
        }),
        j2: review({ proposal: proposal("p-one", "j2", "Parv Pareek"), execution: null }),
        j3: review({ action_plan: { id: "plan1", job_id: "j3", state: "pending", summary: "Two messages", actions: planActions } }),
      },
    };
    mount(data);
    await open();

    expect(await screen.findByText("What needs my attention?")).toBeInTheDocument();
    expect(screen.getByText("Hello, I am ready.")).toBeInTheDocument();

    // Review with attention items: bubble list plus findings in details.
    expect(screen.getByText("The release schema is the open dependency.", { selector: "p.review-summary" })).toBeInTheDocument();
    expect(screen.getByText("What needs you:")).toBeInTheDocument();
    expect(screen.getAllByText("Schema is late").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".finding").length).toBe(3);
    expect(document.querySelector(".finding.conflict .tag.orange")).toHaveTextContent("Conflicting updates");
    expect(screen.getByText("Who owns the rollout?", { selector: ".say p" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Draft a follow-up" })).toBeInTheDocument();

    // Single draft card.
    expect(screen.getByText("Here’s a draft for Parv Pareek. Have a look before it goes out.")).toBeInTheDocument();
    // One single draft card plus the two cards of the plan.
    const cards = document.querySelectorAll(".draft-card");
    expect(cards.length).toBe(3);
    expect(within(cards[0] as HTMLElement).getByRole("button", { name: "Approve and send" })).toBeEnabled();
    expect(within(cards[0] as HTMLElement).getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(within(cards[0] as HTMLElement).getByText("Awaiting approval")).toBeInTheDocument();

    // Action plan with a bulk approve.
    expect(document.querySelector(".action-plan.plan-pending")).toHaveTextContent("2 messages are ready for you to check.");
    expect(screen.getByRole("button", { name: "Approve all 2 visible drafts" })).toBeInTheDocument();
    expect(document.querySelectorAll(".planned-action .draft-card").length).toBe(2);

    // Failure card for a job that failed with a recovery code.
    const failed = document.querySelector("[data-progress='j4']") as HTMLElement;
    expect(failed).toHaveClass("turn", "assistant", "working");
    expect(within(failed).getByRole("alert")).toHaveTextContent("Reconnect Microsoft to continue");
    expect(within(failed).getByRole("button", { name: "Reconnect Microsoft" })).toBeInTheDocument();
    expect(within(failed).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(failed).queryByRole("button", { name: "Resume" })).toBeNull();
  });

  it("shows a topic separator when the source set changes and a stamp after a long pause", async () => {
    const other = job("j2", { sources: [{ external_id: "c9", label: "Budget chat", selection_reason: "auto" }] });
    mount({
      thread: thread(),
      jobs: [job("j1"), other],
      messages: [message("m1", "manager", "first", "j1", 0), message("m2", "assistant", "ok", null, 1), message("m3", "manager", "second", "j2", 59)],
    });
    await open();
    expect(await screen.findByRole("separator")).toHaveTextContent("New topic · Budget chat");
    expect(document.querySelectorAll("time.chat-stamp").length).toBe(2);
  });

  it("renders Teams and model text as text, never markup", async () => {
    const hostile = "<img src=x onerror=\"window.__xss=1\"><script>window.__xss=2</script><b>bold</b>";
    mount({
      thread: thread(),
      jobs: [job("j1")],
      messages: [message("m1", "manager", hostile, "j1", 1), message("m2", "assistant", "x", "j1", 2, { kind: "conversation_review" })],
      evidence: { j1: [evidence("e1", hostile)] },
      reviews: { j1: review({ summary: hostile, attention_items: [{ title: hostile, detail: hostile, evidence_ids: ["e1"] }] }) },
    });
    await open();
    await screen.findAllByText(hostile, { selector: ".bubble p" });
    const timeline = document.getElementById("agent-timeline") as HTMLElement;
    expect(timeline.querySelectorAll("img, script, b").length).toBe(0);
    expect(timeline.textContent).toContain("<img src=x");
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });
});

describe("composer", () => {
  const sendFlow = (state: { messages: ReturnType<typeof message>[] }): Record<string, Handler> => {
    const created = job("j9", { state: "queued", goal: "What needs my attention?" });
    return {
      "GET /api/v2/agent/threads/t1/messages": () => state.messages,
      "POST /api/v2/agent/threads/t1/chat-reply": () => ({ handled: false }),
      "POST /api/v2/agent/threads/t1/messages": () => {
        state.messages = [message("u1", "manager", "What needs my attention?", "j9", 1)];
        return created;
      },
      "GET /api/v2/agent/jobs/j9": () => created,
      "POST /api/v2/agent/jobs/j9/evidence/sync": () => ({ evidence: [evidence()] }),
      "POST /api/v2/agent/jobs/j9/review": () => {
        state.messages = [...state.messages, message("a1", "assistant", "x", "j9", 2, { kind: "conversation_review" })];
        return review();
      },
      "GET /api/v2/agent/jobs/j9/review": () => review(),
      "GET /api/v2/agent/jobs/j9/evidence": () => [evidence()],
    };
  };

  it("creates a job, polls and renders the review", async () => {
    const state = { messages: [] as ReturnType<typeof message>[] };
    const { calls, count } = mount(empty(), sendFlow(state));
    await open();
    const user = userEvent.setup();
    const input = await screen.findByLabelText("Message Prism");
    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.getByRole("button", { name: "Ask Prism" })).toBeDisabled();

    await user.type(input, "What needs my attention?");
    await user.click(screen.getByRole("button", { name: "Ask Prism" }));

    expect(await screen.findByText("The release schema is the open dependency.", { selector: "p.review-summary" })).toBeInTheDocument();
    expect(count("POST /api/v2/agent/threads/t1/messages")).toBe(1);
    expect(calls.find((call) => call.url.endsWith("/chat-reply"))?.body).toEqual({ content: "What needs my attention?" });
    expect(calls.find((call) => call.method === "POST" && call.url.endsWith("/threads/t1/messages"))?.body).toEqual({
      content: "What needs my attention?",
      source_external_id: null,
    });
    // The question left the composer and the source chip still says "All chats".
    await waitFor(() => expect(input).toHaveValue(""));
    expect(document.getElementById("agent-source-chip-label")).toHaveTextContent("All chats");
    expect(document.querySelectorAll("#agent-timeline [data-message]").length).toBe(1);
  });

  it("keeps the question in the composer and shows a recovery step when sending fails", async () => {
    const routes = sendFlow({ messages: [] });
    routes["POST /api/v2/agent/threads/t1/messages"] = () =>
      json({ detail: "Reconnect", code: "microsoft_reconnect_required" }, 401);
    mount(empty(), routes);
    await open();
    const user = userEvent.setup();
    const input = await screen.findByLabelText("Message Prism");
    await waitFor(() => expect(input).toBeEnabled());
    await user.type(input, "Ask");
    await user.click(screen.getByRole("button", { name: "Ask Prism" }));
    const notice = document.getElementById("agent-composer-notice") as HTMLElement;
    await waitFor(() => expect(notice).toHaveTextContent("Reconnect Microsoft to continue"));
    expect(notice).toHaveTextContent("Nothing was sent");
    expect(input).toHaveValue("Ask");
  });

  it("sends on Enter, adds a line on Shift+Enter", async () => {
    const { count } = mount(empty(), sendFlow({ messages: [] }));
    await open();
    const user = userEvent.setup();
    const input = await screen.findByLabelText("Message Prism");
    await waitFor(() => expect(input).toBeEnabled());
    await user.type(input, "line one{Shift>}{Enter}{/Shift}line two");
    expect(input).toHaveValue("line one\nline two");
    expect(count("POST /api/v2/agent/threads/t1/chat-reply")).toBe(0);
    await user.type(input, "{Enter}");
    await waitFor(() => expect(count("POST /api/v2/agent/threads/t1/chat-reply")).toBe(1));
  });

  it("uses Ctrl+Enter to send when 'Enter adds a new line' is on", async () => {
    setPref("enter-newline", "1");
    const { count } = mount(empty(), sendFlow({ messages: [] }));
    await open();
    const user = userEvent.setup();
    const input = await screen.findByLabelText("Message Prism");
    await waitFor(() => expect(input).toBeEnabled());
    await user.type(input, "hello{Enter}");
    expect(input).toHaveValue("hello\n");
    expect(count("POST /api/v2/agent/threads/t1/chat-reply")).toBe(0);
    await user.type(input, "{Control>}{Enter}{/Control}");
    await waitFor(() => expect(count("POST /api/v2/agent/threads/t1/chat-reply")).toBe(1));
  });
});

describe("draft approval", () => {
  const data = (): Conversation => ({
    thread: thread(),
    jobs: [job("j2")],
    messages: [message("m1", "manager", "Draft", "j2", 1), message("m2", "assistant", "x", "j2", 2, { kind: "conversation_review" })],
    evidence: { j2: [evidence()] },
    reviews: { j2: review({ proposal: proposal("p1x", "j2", "Parv Pareek"), execution: null }) },
  });

  it("requires saving an edit before approving, then approves and sends once", async () => {
    let decided = false;
    let sent = false;
    // After approval the server reports the approved proposal, then its delivery.
    const fresh = () =>
      review({
        proposal: decided ? proposal("p1x", "j2", "Parv Pareek", { state: "approved", body: "Edited text", revision: 2 }) : proposal("p1x", "j2", "Parv Pareek"),
        execution: sent ? { state: "succeeded", created_at: "2026-01-01T10:03:00Z", completed_at: "2026-01-01T10:03:00Z" } : null,
      });
    const { count, calls } = mount(data(), {
      "GET /api/v2/agent/jobs/j2/review": () => fresh(),
      "POST /api/v2/agent/proposals/p1x/revisions": () => proposal("p1x", "j2", "Parv Pareek", { body: "Edited text", revision: 2 }),
      "POST /api/v2/agent/proposals/p1x/decision": () => {
        decided = true;
        return {};
      },
      "POST /api/v2/agent/proposals/p1x/execution": () => {
        sent = true;
        return {};
      },
    });
    await open();
    const user = userEvent.setup();
    const area = await screen.findByLabelText("Reply that will be sent to Teams");
    await user.type(area, " and more");
    expect(screen.getByRole("button", { name: "Approve and send" })).toBeDisabled();
    expect(screen.getByText("You edited this draft. Save the edit, then approve it.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save edit" }));
    await waitFor(() => expect(count("POST /api/v2/agent/proposals/p1x/revisions")).toBe(1));
    expect(calls.find((call) => call.url.endsWith("/revisions"))?.body).toEqual({
      body: "Hello Parv Pareek and more",
      reason: "Edited by manager in Prism workspace",
    });
    await waitFor(() => expect(screen.getByLabelText("Reply that will be sent to Teams")).toHaveValue("Edited text"));
    expect(screen.getByRole("button", { name: "Approve and send" })).toBeEnabled();

    // Approve with a double click: exactly one decision and one execution.
    await user.dblClick(screen.getByRole("button", { name: "Approve and send" }));
    await waitFor(() => expect(document.querySelector(".draft-card .draft-state")).toHaveTextContent("Sent"));
    expect(count("POST /api/v2/agent/proposals/p1x/decision")).toBe(1);
    expect(count("POST /api/v2/agent/proposals/p1x/execution")).toBe(1);
    expect(calls.find((call) => call.url.endsWith("/decision"))?.body).toEqual({
      decision: "approved",
      expected_revision: 2,
      expected_payload_hash: "hash-p1x",
    });
  });

  it("rejects with an optional reason after confirming", async () => {
    const askDialog = vi.fn(async () => "not now" as const);
    const { calls } = mount(
      data(),
      { "POST /api/v2/agent/proposals/p1x/decision": () => ({}) },
      { askDialog },
    );
    await open();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Reject" }));
    await waitFor(() => expect(calls.some((call) => call.url.endsWith("/decision"))).toBe(true));
    expect(askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Reject this draft?", danger: true }));
    expect(calls.find((call) => call.url.endsWith("/decision"))?.body).toMatchObject({ decision: "rejected", reason: "not now" });
  });

  it("does nothing when the reject confirmation is cancelled", async () => {
    const askDialog = vi.fn(async () => null);
    const { count } = mount(data(), {}, { askDialog });
    await open();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Reject" }));
    expect(askDialog).toHaveBeenCalled();
    expect(count("POST /api/v2/agent/proposals/p1x/decision")).toBe(0);
  });
});

describe("threads", () => {
  it("switches Prism and ignores the stale one", async () => {
    const first = conversationRoutes("p1", { thread: thread(), jobs: [], messages: [message("m1", "manager", "from first", null, 1)] });
    const secondThread = thread({ id: "t2" });
    const second = conversationRoutes("p2", { thread: secondThread, jobs: [], messages: [message("n1", "manager", "from second", null, 1)] });
    installFetch({ ...first, ...second });
    renderWithApp(<AgentPage />, { app: { activeTab: "agent" } });
    await open();
    expect(await screen.findByText("from first")).toBeInTheDocument();
    expect(document.getElementById("agent-thread-title")).toHaveTextContent("Release Prism");
    expect(document.getElementById("agent-thread-code")).toHaveTextContent("pAbc12");

    await open({ id: "p2", name: "Budget Prism", code: "pZz999" });
    expect(await screen.findByText("from second")).toBeInTheDocument();
    expect(screen.queryByText("from first")).toBeNull();
    expect(document.getElementById("agent-thread-title")).toHaveTextContent("Budget Prism");
    expect(screen.getByLabelText("Message Prism")).toHaveAttribute("placeholder", "Message Budget Prism");
  });

  it("shows the welcome screen for an empty conversation and the legacy title without a Prism", async () => {
    installFetch({ ...conversationRoutes("p1", empty()), "GET /api/v2/agent/conversation": () => thread(), "GET /api/v2/agent/threads/t1/messages": () => [] });
    renderWithApp(<AgentPage />, { app: { activeTab: "agent", modes: { v21: true, v22: false, v24: false, singleExecutive: false } } });
    expect(await screen.findByRole("heading", { name: "Talk to your manager Prism" })).toBeInTheDocument();
    expect(document.getElementById("agent-thread-code")).not.toBeVisible();
  });
});

describe("source constraint, search and drawer", () => {
  it("chooses a chat and returns to all chats", async () => {
    let current = thread();
    const { calls } = mount(empty(), {
      "GET /api/v2/agent/sources/teams": () => ({ items: [{ external_id: "c1", label: "Parv Pareek", chat_type: "oneonone", participants: ["Parv"] }], total: 1 }),
      "PUT /api/v2/agent/threads/t1/source/teams": () => {
        current = thread({ source_external_id: "c1", source_label: "Parv Pareek" });
        return current;
      },
      "DELETE /api/v2/agent/threads/t1/source/teams": () => {
        current = thread();
        return current;
      },
    });
    await open();
    const user = userEvent.setup();
    const chip = await screen.findByRole("button", { name: /All chats/ });
    await waitFor(() => expect(chip).toBeEnabled());
    await user.click(chip);
    const dialog = document.getElementById("agent-source-dialog") as HTMLDialogElement;
    expect(dialog).toHaveAttribute("open");
    await user.click(await within(dialog).findByRole("button", { name: /Parv Pareek/ }));
    await waitFor(() => expect(document.getElementById("agent-source-chip-label")).toHaveTextContent("Parv Pareek"));
    expect(calls.find((call) => call.method === "PUT")?.body).toEqual({ external_id: "c1" });
    expect(dialog).not.toHaveAttribute("open");

    await user.click(screen.getByRole("button", { name: /Parv Pareek/, description: /limited to this chat/ }));
    await user.click(await within(dialog).findByRole("button", { name: /All chats/ }));
    await waitFor(() => expect(document.getElementById("agent-source-chip-label")).toHaveTextContent("All chats"));
  });

  it("searches the conversation and jumps into history", async () => {
    const found = [message("m1", "manager", "What needs my attention", null, 1)];
    const { calls } = mount(
      { thread: thread(), jobs: [], messages: [message("m1", "manager", "What needs my attention", null, 1), message("m2", "manager", "What else", null, 2)] },
      { "GET /api/v2/agent/threads/t1/messages": (request) => (request.url.includes("q=") ? found : [message("m2", "manager", "What else", null, 2)]) },
    );
    await open();
    const user = userEvent.setup();
    await screen.findByText("What else");
    await user.click(screen.getByRole("button", { name: "Search" }));
    const box = screen.getByLabelText("Search your conversation with Prism");
    await waitFor(() => expect(box).toHaveFocus());
    await user.type(box, "What needs");
    await user.click(await screen.findByRole("button", { name: /You/ }, { timeout: 2000 }));
    expect(await screen.findByText("Viewing earlier history.")).toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("before="))).toBe(true);
    expect(document.getElementById("agent-search-panel")).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Back to latest" }));
    await waitFor(() => expect(screen.queryByText("Viewing earlier history.")).toBeNull());
    await waitFor(() => expect(screen.getByLabelText("Message Prism")).toHaveFocus());
  });

  it("adds a preference in the drawer", async () => {
    let items: unknown[] = [];
    const { calls } = mount(empty(), {
      "GET /api/v2/prisms/p1/preferences": () => items,
      "POST /api/v2/prisms/p1/preferences": () => {
        items = [{ id: "pf1", instruction: "Keep replies short", is_active: true, scope: "general", created_at: "2026-01-01T10:00:00Z" }];
        return {};
      },
    });
    await open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Preferences and settings" }));
    expect(document.getElementById("agent-preferences-panel")).toHaveClass("open");
    expect(document.getElementById("agent-chat")).toHaveClass("drawer-open");
    expect(document.getElementById("agent-preferences-intro")).toHaveTextContent("Release Prism only");
    await user.type(screen.getByLabelText("New instruction"), "Keep replies short");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(document.getElementById("agent-preference-list")).toHaveTextContent("Keep replies short"));
    expect(calls.find((call) => call.method === "POST" && call.url.endsWith("/preferences"))?.body).toEqual({ instruction: "Keep replies short" });
    expect(document.getElementById("agent-preferences-count")).toHaveTextContent("1");
    await user.click(screen.getByRole("button", { name: "Close settings" }));
    expect(document.getElementById("agent-preferences-panel")).not.toHaveClass("open");
  });
});
