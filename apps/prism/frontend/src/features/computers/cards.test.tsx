import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { installDialogPolyfill } from "@/test/dialog";
import { renderQaMessage } from "./renderQaMessage";
import { getState, initQa, notify, onPrism, resetComputers } from "./store";
import { fakeHost, installFetch, json, makeRun, makeWorkRun, message, qaPrism, stubBlobUrls, type Handler } from "./testkit";
import type { ChatMessageLike, QaApproval, QaRun } from "./types";

beforeAll(installDialogPolyfill);

let host = fakeHost();
stubBlobUrls();

function setup(routes: Record<string, Handler> = {}) {
  host = fakeHost();
  stubBlobUrls();
  const net = installFetch({ "GET /api/v2/prisms/p1/qa/runs": () => [], "GET /api/v2/qa/status": () => ({ available: true, computers: false }), ...routes });
  initQa(host);
  onPrism(qaPrism);
  return net;
}
const seed = (run: QaRun) =>
  act(() => {
    getState().runs.set(run.id, run);
    notify();
  });
const Card = ({ msg }: { msg: ChatMessageLike }) => <>{renderQaMessage(msg)?.card}</>;
const show = (msg: ChatMessageLike) => render(<Card msg={msg} />);

beforeEach(() => setup());
afterEach(() => {
  cleanup();
  resetComputers();
  vi.unstubAllGlobals();
});

describe("renderQaMessage", () => {
  it("returns null for ordinary and unknown messages", () => {
    expect(renderQaMessage({ content: "hi" })).toBeNull();
    expect(renderQaMessage({ content: "hi", message_metadata: { kind: "mystery" } })).toBeNull();
    expect(renderQaMessage({ content: "hi", message_metadata: null })).toBeNull();
  });

  it.each(["qa_plan", "qa_approval", "qa_report", "work_plan", "work_approval", "work_report", "work_busy"])("returns the lead text and a card for %s", (kind) => {
    const result = renderQaMessage(message(kind));
    expect(result?.lead).toBe(`lead for ${kind}`);
    expect(result?.card).toBeTruthy();
  });
});

describe("plan card", () => {
  it("loads an unknown run, then shows the QA plan", async () => {
    const net = setup({ "GET /api/v2/qa/runs/run-1": () => makeRun() });
    show(message("qa_plan"));
    expect(screen.getByText("Loading the plan…")).toBeInTheDocument();
    expect(await screen.findByText("example.com")).toBeInTheDocument();
    expect(net.count("GET /api/v2/qa/runs/run-1")).toBe(1);
    const plan = document.querySelector(".qa-plan") as HTMLElement;
    expect(plan).toHaveTextContent("Live site · dummy data");
    expect(plan).toHaveTextContent("Discover pages automatically");
    expect(plan).toHaveTextContent("Starting pages/");
    expect(plan).toHaveTextContent("Bug filingOff");
    expect(plan).toHaveTextContent("up to 60 steps · $1.00 budget");
    expect(within(plan).getByText("Form validates")).toBeInTheDocument();
    expect(within(plan).getByRole("button", { name: "Start testing" })).toBeInTheDocument();
    expect(within(plan).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(within(plan).getByRole("button", { name: "Not now" })).toBeInTheDocument();
  });

  it("shows the work plan with sites and limits and a plain Start button", () => {
    seed(makeWorkRun());
    show(message("work_plan", "work-1"));
    const plan = document.querySelector(".qa-plan") as HTMLElement;
    expect(plan).toHaveTextContent("Find leads");
    expect(plan.textContent).toContain("Siteslinkedin.com  ·  any public website"); // separators keep their double spaces
    expect(plan).toHaveTextContent("Asks you firstlogin");
    expect(plan).toHaveTextContent("up to 40 steps · $1.50 · 20 min at most");
    expect(screen.getByRole("button", { name: "Start" })).toBeInTheDocument();
  });

  it("Start posts the saved edits, disables itself and re-enables on failure", async () => {
    let fail = true;
    const net = setup({
      "POST /api/v2/qa/runs/run-1/start": () => (fail ? json({ detail: "Not allowed" }, 403) : { ...makeRun(), state: "running", active: true }),
    });
    seed(makeRun());
    show(message("qa_plan"));
    const start = screen.getByRole("button", { name: "Start testing" });
    await userEvent.click(start);
    await waitFor(() => expect(host.setStatus).toHaveBeenCalledWith("Not allowed", true));
    await waitFor(() => expect(start).toBeEnabled());
    fail = false;
    await userEvent.click(start);
    await waitFor(() => expect(getState().runs.get("run-1")?.state).toBe("running"));
    expect(net.calls.filter((call) => call.url.endsWith("/start")).at(-1)?.body).toEqual({});
    expect(getState().open).toBe(true);
    expect(await screen.findByText("Testing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Watch" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
  });

  it("Edit opens the form; Save keeps the changes for Start and updates the plan", async () => {
    const net = setup({ "POST /api/v2/qa/runs/run-1/start": () => ({ ...makeRun(), state: "running", active: true }) });
    seed(makeRun({ plan: { ...makeRun().plan, environment: "staging", discovery_mode: "automatic" } }));
    show(message("qa_plan"));
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.queryByRole("button", { name: "Start testing" })).toBeNull();
    const pages = screen.getByLabelText("Starting pages (optional; I'll discover the rest)");
    await userEvent.clear(pages);
    await userEvent.type(pages, "/contact, /about");
    const turns = screen.getByLabelText("Max steps");
    await userEvent.clear(turns);
    await userEvent.type(turns, "20");
    await userEvent.click(screen.getByLabelText("Let me ask to file bugs"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(getState().edits.get("run-1")).toEqual({
      pages: ["/contact", "/about"],
      acceptance_criteria: ["Form validates"],
      max_turns: 20,
      budget_usd: 1,
      allow_bug_filing: true,
    });
    expect(screen.getByText(/up to 20 steps/)).toBeInTheDocument();
    expect(host.rerenderChat).toHaveBeenCalledWith({ scroll: "keep" });
    await userEvent.click(screen.getByRole("button", { name: "Start testing" }));
    await waitFor(() => expect(net.calls.some((call) => call.url.endsWith("/start"))).toBe(true));
    expect(net.calls.find((call) => call.url.endsWith("/start"))?.body).toMatchObject({ max_turns: 20, pages: ["/contact", "/about"] });
  });

  it("Cancel in the edit form discards the edits; the work form saves steps and sites", async () => {
    seed(makeWorkRun());
    show(message("work_plan", "work-1"));
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(getState().edits.size).toBe(0);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const steps = screen.getByLabelText("Steps (one per line)");
    await userEvent.clear(steps);
    await userEvent.type(steps, "One{enter}Two{enter}");
    await userEvent.click(screen.getByLabelText("Any public website, if needed"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(getState().edits.get("work-1")).toMatchObject({ steps: ["One", "Two"], sites: ["https://linkedin.com"], any_public_site: false });
  });

  it("Not now cancels the run", async () => {
    setup({ "POST /api/v2/qa/runs/run-1/cancel": () => ({ ...makeRun(), state: "cancelled", active: false }) });
    seed(makeRun());
    show(message("qa_plan"));
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(await screen.findByText("Stopped")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start testing" })).toBeNull();
  });

  it("summarises checks on a finished run", () => {
    seed(makeRun({ state: "succeeded", cases: { total: 4, pass: 3, fail: 1 } }));
    show(message("qa_plan"));
    expect(screen.getByText("Finished")).toHaveClass("qa-chip", "tag-green");
    expect(screen.getByText("4 checks · 3 passed · 1 failed")).toBeInTheDocument();
  });
});

describe("approval cards", () => {
  const approvalMessage = (id: string) => message("qa_approval", "run-1", { qa_approval_id: id });
  const withApproval = (approval: QaApproval, extra: Partial<QaRun> = {}) => seed(makeRun({ state: "waiting_approval", active: true, approvals: [approval], ...extra }));

  it("renders an empty card while the run or approval is unknown", () => {
    show(approvalMessage("a1"));
    expect(document.querySelector(".qa-plan")).toBeEmptyDOMElement();
    seed(makeRun());
    expect(document.querySelector(".qa-plan")).toBeEmptyDOMElement();
  });

  it("outward action: Allow/Don't post decisions; decided text afterwards", async () => {
    const net = setup({
      "POST /api/v2/qa/approvals/a1/decision": () => makeRun({ approvals: [{ id: "a1", kind: "outward_action", status: "approved" }] }),
      "GET /api/v2/qa/runs/run-1/frame": () => new Response("x"),
    });
    withApproval({ id: "a1", kind: "outward_action", status: "pending", view: { summary: "send the form", site: "example.com", details: "name=Test", frame: true } }, { frame: 3 });
    show(approvalMessage("a1"));
    expect(screen.getByText("Before I go ahead")).toBeInTheDocument();
    expect(screen.getByText("send the form")).toBeInTheDocument();
    expect(screen.getByText("Where")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByAltText("What the screen shows right now")).toHaveAttribute("src", "blob:fake-1"));
    await userEvent.click(screen.getByRole("button", { name: "Allow" }));
    expect(net.calls.find((call) => call.url.endsWith("/decision"))?.body).toEqual({ decision: "approve" });
    expect(await screen.findByText("You allowed it.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Allow" })).toBeNull();
  });

  it("site access rejected shows the refusal text", async () => {
    withApproval({ id: "a1", kind: "site_access", status: "rejected", view: { site: "other.com" } });
    show(approvalMessage("a1"));
    expect(screen.getByText("You said no, so I didn't do it.")).toBeInTheDocument();
  });

  it("failed decisions re-enable the buttons and report the error", async () => {
    setup({ "POST /api/v2/qa/approvals/a1/decision": () => json({ detail: "Too late" }, 409) });
    withApproval({ id: "a1", kind: "outward_action", status: "pending", view: { summary: "x" } });
    show(approvalMessage("a1"));
    await userEvent.click(screen.getByRole("button", { name: "Don't" }));
    await waitFor(() => expect(host.setStatus).toHaveBeenCalledWith("Too late", true));
    await waitFor(() => expect(screen.getByRole("button", { name: "Don't" })).toBeEnabled());
  });

  it("budget extension", async () => {
    const net = setup({ "POST /api/v2/qa/approvals/a1/decision": () => makeRun({ approvals: [{ id: "a1", kind: "budget_extension", status: "rejected" }] }) });
    withApproval({ id: "a1", kind: "budget_extension", status: "pending", view: { reason: "More internal pages remain.", max_turns: 120, budget_usd: 2 } });
    show(approvalMessage("a1"));
    expect(screen.getByText("More pages remain to test")).toBeInTheDocument();
    expect(screen.getByText("More internal pages remain.")).toBeInTheDocument();
    expect(screen.getByText("120 steps · $2.00 total budget")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Finish with partial report" }));
    expect(net.calls.find((call) => call.url.endsWith("/decision"))?.body).toEqual({ decision: "reject" });
    expect(await screen.findByText("You finished with a partial report.")).toBeInTheDocument();
  });

  it("question: sends the answer; blank answers are not sent; Skip rejects", async () => {
    const net = setup({ "POST /api/v2/qa/approvals/a1/decision": () => makeRun({ approvals: [{ id: "a1", kind: "question", status: "approved" }] }) });
    withApproval({ id: "a1", kind: "question", status: "pending", view: { question: "Which plan?" } });
    show(approvalMessage("a1"));
    const answer = screen.getByLabelText("Your answer");
    expect(answer).toBeRequired();
    expect(answer).toHaveAttribute("maxlength", "1000");
    fireEvent.change(answer, { target: { value: "   " } });
    fireEvent.submit(answer.closest("form") as HTMLFormElement);
    expect(net.calls.filter((call) => call.url.endsWith("/decision"))).toHaveLength(0);
    await userEvent.clear(answer);
    await userEvent.type(answer, "The pro plan");
    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));
    await waitFor(() => expect(net.calls.find((call) => call.url.endsWith("/decision"))?.body).toEqual({ decision: "approve", answer: "The pro plan" }));
    expect(await screen.findByText("You answered.")).toBeInTheDocument();
  });

  it("login: secure form, posts the credentials once, clears the password and shows the decided state", async () => {
    const net = setup({ "POST /api/v2/qa/approvals/a1/decision": () => makeRun({ approvals: [{ id: "a1", kind: "login", status: "approved" }] }) });
    withApproval({ id: "a1", kind: "login", status: "pending", view: { site: "https://linkedin.com", reason: "to find people" } });
    show(approvalMessage("a1"));
    expect(screen.getByText("Quinn needs to sign in to linkedin.com")).toBeInTheDocument();
    expect(screen.getByText("to find people")).toBeInTheDocument();
    expect(screen.getByText("Only Quinn's computer uses this. It is encrypted, never shown in chat, and never seen by the AI model.")).toBeInTheDocument();
    const form = document.querySelector("form.qa-edit.qa-login") as HTMLFormElement;
    const user = form.querySelector("input[type=text]") as HTMLInputElement;
    const pass = form.querySelector("input[type=password]") as HTMLInputElement;
    expect(user).toHaveAttribute("name", "prism-site-username");
    expect(pass).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByRole("option", { name: "Remember for Quinn" })).toBeInTheDocument();
    await userEvent.type(user, "bob@example.com");
    await userEvent.type(pass, "hunter2-secret");
    await userEvent.selectOptions(screen.getByLabelText("How long to keep it"), "false");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(pass).toHaveValue("");
    await waitFor(() => expect(net.calls.find((call) => call.url.endsWith("/decision"))?.body).toEqual({ decision: "approve", login: { username: "bob@example.com", password: "hunter2-secret", remember: false } }));
    expect(await screen.findByText("You gave a login.")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("hunter2-secret");
  });

  it("login skip button names the site", async () => {
    const net = setup({ "POST /api/v2/qa/approvals/a1/decision": () => makeRun({ approvals: [{ id: "a1", kind: "login", status: "rejected" }] }) });
    withApproval({ id: "a1", kind: "login", status: "pending", view: { site: "https://linkedin.com" } });
    show(approvalMessage("a1"));
    await userEvent.click(screen.getByRole("button", { name: "Skip linkedin.com" }));
    expect(net.calls.find((call) => call.url.endsWith("/decision"))?.body).toEqual({ decision: "reject" });
    expect(await screen.findByText("You skipped signing in.")).toBeInTheDocument();
  });

  it("bug approval: File it / Don't file and the decided lines", async () => {
    const net = setup({ "POST /api/v2/qa/approvals/a1/decision": () => makeRun({ approvals: [{ id: "a1", kind: "bug", status: "approved" }] }) });
    withApproval({ id: "a1", kind: "bug", status: "pending", title: "Empty email accepted", severity: "high", steps: "Submit empty", expected: "Error", actual: "Nothing" });
    show(approvalMessage("a1"));
    expect(screen.getByText("Empty email accepted")).toBeInTheDocument();
    expect(screen.getByText("high")).toHaveClass("tag-red");
    expect(screen.getByText("Actually")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "File it" }));
    expect(net.calls.find((call) => call.url.endsWith("/decision"))?.body).toEqual({ decision: "approve" });
    expect(await screen.findByText("You approved filing this.")).toBeInTheDocument();
  });

  it("bug rejected", () => {
    withApproval({ id: "a1", kind: "bug", status: "rejected", title: "", severity: "" });
    show(approvalMessage("a1"));
    expect(screen.getByText("A bug I found")).toBeInTheDocument();
    expect(screen.getByText("medium")).toHaveClass("tag-gray"); // unknown severity -> gray, like the old card
    expect(screen.getByText("You chose not to file this.")).toBeInTheDocument();
  });
});

describe("busy card", () => {
  it("offers Watch and Stop only while the other task runs", async () => {
    const net = setup({ "POST /api/v2/qa/runs/work-1/cancel": () => makeWorkRun({ state: "cancelled", active: false }) });
    seed(makeWorkRun({ state: "running", active: true }));
    show(message("work_busy", "work-1"));
    await userEvent.click(screen.getByRole("button", { name: "Watch" }));
    expect(getState().focus).toBe("work-1");
    await userEvent.click(screen.getByRole("button", { name: "Stop that task" }));
    await waitFor(() => expect(net.count("POST /api/v2/qa/runs/work-1/cancel")).toBe(1));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Watch" })).toBeNull());
  });
});

describe("report cards", () => {
  const qaReport = (over: object = {}) =>
    makeRun({
      state: "succeeded",
      report: {
        counts: { pass: 3, fail: 1, blocked: 2, skipped: 1 },
        bugs: [{ title: "Empty email accepted", severity: "critical", steps: "Submit", expected: "Error", actual: "None", screens: [0, 1, 2, 3] }],
        cases: [
          { title: "Empty email rejected", status: "fail", given: "the form", when: "submitted empty", then: "an error shows", notes: "no error", screens: [1] },
          { title: "Page loads", status: "pass" },
          { title: "Odd", status: "weird" },
        ],
        coverage: { pages: [{ url: "https://example.com/contact", status: "tested", reason: "Validation checked" }, { url: "https://example.com/admin", status: "blocked" }], truncated: true },
        partial: true,
        pages: ["/", "/contact"],
        duration_seconds: 200,
        cost_usd: 0.456,
        ...over,
      },
    });

  it("renders chips, coverage, issues, checks and the footer", () => {
    setup({ "GET /api/v2/qa/runs/run-1/screens/1": () => new Response("x") });
    seed(qaReport());
    show(message("qa_report"));
    const chips = Array.from(document.querySelectorAll(".qa-counts .qa-chip")).map((chip) => `${chip.textContent}|${chip.className}`);
    expect(chips).toEqual([
      "3 passed|qa-chip tag-green",
      "1 failed|qa-chip tag-red",
      "2 couldn't check|qa-chip tag-orange",
      "1 skipped|qa-chip tag-gray",
      "1 issue|qa-chip tag-red",
    ]);
    expect(screen.getByText("Partial coverage: some discovered pages remain untested.")).toBeInTheDocument();
    expect(screen.getByText("Page coverage (2)")).toBeInTheDocument();
    expect(screen.getByText("Tested: https://example.com/contact")).toBeInTheDocument();
    expect(screen.getByText("Untested: https://example.com/admin")).toBeInTheDocument();
    expect(screen.getByText("Not tested before this session ended.")).toBeInTheDocument();
    expect(screen.getByText("The discovery list reached its safety limit. More routes may exist.")).toBeInTheDocument();
    expect(screen.getByText("Issues")).toBeInTheDocument();
    expect(screen.getByText("critical")).toHaveClass("tag-red");
    expect(screen.getByText("All checks (3)")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toHaveClass("tag-red");
    expect(screen.getByText("Passed")).toHaveClass("tag-green");
    expect(screen.getByText("weird")).toHaveClass("tag-gray");
    expect(screen.getByText("Given the form, when submitted empty, then an error shows")).toBeInTheDocument();
    expect(screen.getByText("no error")).toHaveClass("qa-notes");
    expect(document.querySelector("details.qa-cases:last-of-type")).toHaveAttribute("open");
    expect(document.querySelector(".qa-foot")).toHaveTextContent("3 min · 2 pages · $0.46");
    // issue cards show at most 3 thumbnails, checks at most 2
    expect(document.querySelectorAll(".qa-card .qa-thumb")).toHaveLength(3);
  });

  it("collapses a long checks list and singularises the footer", () => {
    const cases = Array.from({ length: 9 }, (_, index) => ({ title: `Case ${index}`, status: "pass" }));
    seed(qaReport({ cases, bugs: [], coverage: undefined, partial: false, pages: ["/"], counts: { pass: 9 }, duration_seconds: null }));
    show(message("qa_report"));
    expect(screen.getByText("All checks (9)").closest("details")).not.toHaveAttribute("open");
    expect(document.querySelector(".qa-foot")).toHaveTextContent("1 page · $0.46");
    expect(screen.queryByText("Issues")).toBeNull();
  });

  it("thumbnails fetch the screenshot, open a lightbox dialog and remove themselves on failure", async () => {
    setup({
      "GET /api/v2/qa/runs/run-1/screens/1": () => new Response("x"),
      "GET /api/v2/qa/runs/run-1/screens/9": () => json({ detail: "gone" }, 404),
    });
    seed(qaReport({ bugs: [], cases: [{ title: "Shot", status: "fail", screens: [1, 9] }], coverage: undefined }));
    show(message("qa_report"));
    const image = await screen.findByAltText("Shot");
    await waitFor(() => expect(document.querySelectorAll("img.qa-thumb")).toHaveLength(1));
    await waitFor(() => expect(image).toHaveAttribute("src", "blob:fake-1"));
    await userEvent.click(image);
    const dialog = document.querySelector("dialog.qa-lightbox") as HTMLDialogElement;
    expect(dialog).toHaveAttribute("open");
    expect(within(dialog).getByAltText("Shot")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(document.querySelector("dialog.qa-lightbox")).toBeNull();
    await userEvent.click(image);
    fireEvent.click(document.querySelector("dialog.qa-lightbox") as HTMLDialogElement);
    expect(document.querySelector("dialog.qa-lightbox")).toBeNull();
  });

  it("is an empty report block until the run has a report", () => {
    seed(makeRun());
    show(message("qa_report"));
    expect(document.querySelector(".qa-report")).toBeEmptyDOMElement();
  });

  describe("work report", () => {
    const work = (report: object) => makeWorkRun({ state: "succeeded", report: { kind: "work", outcome: "succeeded", ...report } });

    it("shows counts, a results table, sections, downloads and the footer", async () => {
      const net = setup({ "GET /api/v2/qa/runs/work-1/files/0": () => new Response("a,b") });
      const clicked: string[] = [];
      const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push(`${this.download}|${this.href}`);
      });
      seed(
        work({
          row_count: 2,
          files: [{ index: 0, name: "leads.csv" }],
          columns: ["company_name", "web-site"],
          rows: [
            { company_name: "Acme", "web-site": "https://acme.com/about" },
            { company_name: "Evil", "web-site": "javascript:alert(1)" },
          ],
          needs_attention: ["Check the login"],
          next_steps: ["Email them"],
          duration_seconds: 30,
          cost_usd: 0.5,
        }),
      );
      show(message("work_report", "work-1"));
      expect(screen.getByText("2 found")).toHaveClass("tag-green");
      expect(screen.queryByText("Finished")).toBeNull();
      expect(screen.getByText("company name")).toBeInTheDocument();
      expect(screen.getByText("web site")).toBeInTheDocument();
      const region = screen.getByRole("region", { name: "Results" });
      expect(region).toHaveAttribute("tabindex", "0");
      const link = within(region).getByRole("link", { name: "acme.com/about" });
      expect(link).toHaveAttribute("href", "https://acme.com/about");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
      expect(link).toHaveAttribute("target", "_blank");
      expect(within(region).getAllByRole("link")).toHaveLength(1);
      expect(within(region).getByText("javascript:alert(1)").tagName).toBe("TD");
      expect(screen.getByText("Needs your attention")).toBeInTheDocument();
      expect(screen.getByText("What I can do next")).toBeInTheDocument();
      expect(document.querySelector(".qa-foot")).toHaveTextContent("1 min · $0.50");
      await userEvent.click(screen.getByRole("button", { name: "Download leads.csv" }));
      await waitFor(() => expect(clicked).toEqual(["leads.csv|blob:fake-1"]));
      expect(net.count("GET /api/v2/qa/runs/work-1/files/0")).toBe(1);
      click.mockRestore();
    });

    it("download failure reports through the host", async () => {
      setup({ "GET /api/v2/qa/runs/work-1/files/0": () => json({}, 404) });
      seed(work({ files: [{ index: 0, name: "x.csv" }] }));
      show(message("work_report", "work-1"));
      await userEvent.click(screen.getByRole("button", { name: "Download x.csv" }));
      await waitFor(() => expect(host.setStatus).toHaveBeenCalledWith("That file isn't available right now.", true));
    });

    it("shows a non-success outcome", () => {
      seed(work({ outcome: "timed_out" }));
      show(message("work_report", "work-1"));
      expect(screen.getByText("Ran out of time")).toHaveClass("tag-orange");
    });
  });

  it("renders untrusted text as text, never as markup", () => {
    const payload = `<img src=x onerror="window.__pwned = 1"><script>window.__pwned = 1</script>`;
    seed(
      qaReport({
        bugs: [{ title: payload, severity: payload, steps: payload, expected: payload, actual: payload }],
        cases: [{ title: payload, status: "pass", notes: payload }],
        coverage: { pages: [{ url: payload, status: "tested" }] },
      }),
    );
    seed(
      makeWorkRun({
        id: "run-2",
        state: "succeeded",
        report: { kind: "work", outcome: "succeeded", columns: [payload], rows: [{ [payload]: payload }], needs_attention: [payload], next_steps: [payload] },
      }),
    );
    show(message("qa_report"));
    show(message("work_report", "run-2"));
    expect(document.querySelectorAll("script")).toHaveLength(0);
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    expect(screen.getAllByText(payload, { exact: false }).length).toBeGreaterThan(5);
  });
});
