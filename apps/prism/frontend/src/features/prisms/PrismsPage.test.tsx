import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emit } from "@/lib/events";
import { STORAGE_KEYS } from "@/lib/storage";
import { PrismCreateButton } from "./PrismCreateButton";
import { PrismSidebarSection } from "./PrismSidebarSection";
import { PrismsPage } from "./PrismsPage";
import { fakeFetch, prismRow, renderPrisms, type Handler } from "./test-utils";

const draft = prismRow({ id: "d1", name: "Draft Prism", state: "draft" as never, description: "Keep me informed. Be brief." });
const org = { chief_of_staff_id: "chief", owner_name: "Me", departments: ["Sales", "Leadership"], members: [prismRow({ id: "chief", name: "Chief of Staff", is_chief_of_staff: true })] };

function question(id: string, key: string, over: Record<string, unknown> = {}) {
  return { id, key, position: 0, prompt: `Hello! what is ${key}?`, help_text: null, required: true, allows_custom: true, question_type: "single_choice", choices: [{ value: "a", label: "Alpha" }, { value: "b", label: "Beta" }], ...over };
}
const session = (over: Record<string, unknown> = {}) => ({
  id: "s1", prism_id: "d1", revision: 3, status: "in_progress", current_question_id: "q1", question_set_version: "1", generation_note: null,
  questions: [question("q1", "mission"), question("q2", "tone", { required: false })], answers: [], ...over,
});

function setup(extra: Array<[string, RegExp, Handler]> = [], rows = [draft], source?: () => unknown) {
  return fakeFetch([
    ...extra,
    ["GET", /api\/v2\/prisms\?/, () => (source ? source() : rows)],
    ["GET", /updates\/summary/, () => []],
    ["POST", /presence/, () => ({})],
    ["GET", /qa\/status/, () => ({ computers: false })],
    ["GET", /prisms\/organization/, () => org],
  ]);
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("create flow", () => {
  it("creates a Prism from the dialog and selects it", async () => {
    let rows: Array<typeof draft> = [];
    const created = prismRow({ id: "n1", name: "Executive Updates", state: "draft" as never, color: "green" });
    const { calls } = setup([["GET", /prisms\/organization/, () => ({ ...org, chief_of_staff_id: null, members: [] })], ["POST", /api\/v2\/prisms$/, () => { rows = [created]; return created; }], ["GET", /prisms\/n1\/onboarding$/, () => { throw { status: 404, detail: "none" }; }], ["POST", /onboarding\/start/, () => session({ prism_id: "n1" })]], [], () => rows);
    const { app } = renderPrisms(<><PrismCreateButton /><PrismSidebarSection /><PrismsPage /></>);
    await screen.findByText("No Prisms yet.");
    await userEvent.click(screen.getByRole("button", { name: "Create Prism" }));
    const dialog = document.getElementById("prism-editor-dialog") as HTMLDialogElement;
    expect(dialog).toHaveAttribute("open");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Create prism" })).toBeEnabled());
    // The first Prism of a workspace becomes the Chief of Staff.
    expect(within(dialog).getByLabelText("Role")).toHaveValue("Chief of Staff");
    await userEvent.clear(within(dialog).getByLabelText("Name"));
    await userEvent.type(within(dialog).getByLabelText("Name"), "Executive Updates");
    await userEvent.clear(within(dialog).getByLabelText("What is this Prism responsible for?"));
    await userEvent.type(within(dialog).getByLabelText("What is this Prism responsible for?"), "Keep me informed.");
    await userEvent.click(within(dialog).getByLabelText("Green"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Create prism" }));
    await waitFor(() => expect(app.setStatus).toHaveBeenCalledWith("Executive Updates is ready. Let’s set it up."));
    const post = calls.find((call) => call.method === "POST" && call.path === "/api/v2/prisms");
    expect(post?.body).toMatchObject({ name: "Executive Updates", description: "Keep me informed.", color: "green", job_role: "Chief of Staff", department: "Leadership", reports_to_prism_id: null, template_key: "blank" });
    expect(dialog).not.toHaveAttribute("open");
    expect(app.setActiveTab).toHaveBeenCalledWith("prisms");
    expect(localStorage.getItem(STORAGE_KEYS.selectedPrism)).toBe("n1");
    expect(document.querySelector(".prism-nav-item .nav-logo")).toHaveAttribute("data-color", "green");
    await waitFor(() => expect(document.getElementById("prism-conversation-title")).toHaveTextContent("Executive Updates"));
  });

  it("shows an error from the server and keeps the dialog open", async () => {
    setup([["POST", /api\/v2\/prisms$/, () => { throw { status: 422, detail: "Name taken" }; }]], []);
    renderPrisms(<><PrismCreateButton /><PrismsPage /></>);
    await userEvent.click(screen.getByRole("button", { name: "Create Prism" }));
    const dialog = document.getElementById("prism-editor-dialog") as HTMLDialogElement;
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Create prism" })).toBeEnabled());
    await userEvent.type(within(dialog).getByLabelText("Name"), "X");
    await userEvent.type(within(dialog).getByLabelText("Role"), "Analyst");
    await userEvent.type(within(dialog).getByLabelText("What is this Prism responsible for?"), "Y");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create prism" }));
    expect(await within(dialog).findByText("Name taken")).toBeVisible();
    expect(dialog).toHaveAttribute("open");
  });
});

describe("archive", () => {
  it("asks first, archives and clears the selection", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "d1");
    let rows = [draft];
    const { calls } = setup([["POST", /archive$/, () => { rows = []; return {}; }]], undefined, () => rows);
    const { app } = renderPrisms(<><PrismSidebarSection /><PrismsPage /></>);
    await waitFor(() => expect(document.getElementById("prism-conversation-title")).toHaveTextContent("Draft Prism"));
    expect(document.getElementById("prism-archive-label")).toHaveTextContent("Archive");
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    await userEvent.click(document.getElementById("prism-archive-button") as HTMLElement);
    await waitFor(() => expect(app.askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Archive Draft Prism?", confirmLabel: "Archive Prism", danger: true })));
    await waitFor(() => expect(app.setStatus).toHaveBeenCalledWith("Draft Prism archived."));
    expect(calls.find((call) => call.path.endsWith("/archive"))?.body).toEqual({ expected_lifecycle_version: 1 });
    expect(localStorage.getItem(STORAGE_KEYS.selectedPrism)).toBeNull();
  });

  it("does nothing when the dialog is declined", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "d1");
    const { calls } = setup();
    const { app } = renderPrisms(<PrismsPage />, { askDialog: vi.fn(async () => null) });
    await waitFor(() => expect(document.getElementById("prism-conversation-title")).toHaveTextContent("Draft Prism"));
    await userEvent.click(document.getElementById("prism-archive-button") as HTMLElement);
    await waitFor(() => expect(app.askDialog).toHaveBeenCalled());
    expect(calls.some((call) => call.path.endsWith("/archive"))).toBe(false);
  });

  it("archive-confirmed archives without asking again; archived Prisms offer permanent delete", async () => {
    const { calls } = setup([["POST", /archive$/, () => ({})]]);
    const { app } = renderPrisms(<PrismSidebarSection />);
    await screen.findByRole("button", { name: /Draft Prism/ });
    act(() => emit("archive-confirmed", { id: "d1" }));
    await waitFor(() => expect(app.setStatus).toHaveBeenCalledWith("Draft Prism archived."));
    expect(app.askDialog).not.toHaveBeenCalled();
    expect(calls.filter((call) => call.path.endsWith("/archive"))).toHaveLength(1);
  });

  it("deletes an archived Prism after confirmation", async () => {
    const old = prismRow({ id: "a1", name: "Old Prism", state: "archived" as never });
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "a1");
    const { calls } = setup([["DELETE", /prisms\/a1$/, () => null]], [old]);
    const { app } = renderPrisms(<PrismsPage />);
    await waitFor(() => expect(document.getElementById("prism-archive-label")).toHaveTextContent("Delete permanently"));
    expect(document.getElementById("prism-edit-label")).toHaveTextContent("View details");
    await userEvent.click(document.getElementById("prism-archive-button") as HTMLElement);
    await waitFor(() => expect(app.askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Delete Old Prism?", confirmLabel: "Delete Prism" })));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE")).toBe(true));
  });
});

describe("onboarding chat", () => {
  it("answers a question and moves on", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "d1");
    let current = session();
    const { calls } = setup([
      ["GET", /prisms\/d1\/onboarding$/, () => current],
      ["POST", /questions\/q1\/answer/, () => {
        current = session({ revision: 4, current_question_id: "q2", answers: [{ question_id: "q1", selected_values: ["b"], custom_text: null, skipped: false }] });
        return current;
      }],
    ]);
    renderPrisms(<PrismsPage />);
    const stream = document.getElementById("prism-onboarding-stream") as HTMLElement;
    await waitFor(() => expect(stream).toHaveTextContent("Hi, I’m Draft Prism. You set me up to: keep me informed."));
    expect(stream).toHaveTextContent("What is mission?");
    expect(document.getElementById("prism-onboarding-form")).not.toHaveAttribute("hidden");
    expect(document.getElementById("prism-onboarding-skip")).toHaveAttribute("hidden");
    expect(document.getElementById("prism-onboarding-back")).toHaveAttribute("hidden");
    await userEvent.click(screen.getByLabelText("Beta"));
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(stream).toHaveTextContent("Beta"), { timeout: 3000 });
    expect(calls.find((call) => call.path.endsWith("/answer"))?.body).toEqual({ expected_revision: 3, selected_values: ["b"], custom_text: "", skipped: false });
    await waitFor(() => expect(stream).toHaveTextContent("Got it, thanks. Hello! what is tone?"), { timeout: 3000 });
    await waitFor(() => expect(document.getElementById("prism-onboarding-skip")).not.toHaveAttribute("hidden"), { timeout: 3000 });
    expect(document.getElementById("prism-onboarding-back")).not.toHaveAttribute("hidden");
  });

  it("shows the answer error and keeps the question", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "d1");
    setup([
      ["GET", /prisms\/d1\/onboarding$/, () => session()],
      ["POST", /answer/, () => { throw { status: 409, detail: "Stale revision" }; }],
    ]);
    renderPrisms(<PrismsPage />);
    await screen.findByLabelText("Alpha");
    await userEvent.click(screen.getByLabelText("Alpha"));
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Stale revision", {}, { timeout: 3000 })).toBeVisible();
    expect(screen.getByLabelText("Alpha")).toBeInTheDocument();
  });

  it("starts onboarding by itself for a brand-new draft Prism", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "d1");
    const { calls } = setup([
      ["GET", /prisms\/d1\/onboarding$/, () => { throw { status: 404, detail: "none" }; }],
      ["POST", /onboarding\/start/, () => session()],
    ]);
    const { app } = renderPrisms(<PrismsPage />);
    await screen.findByLabelText("Alpha");
    expect(calls.some((call) => call.path.endsWith("/onboarding/start"))).toBe(true);
    expect(app.setStatus).toHaveBeenCalledWith("Onboarding started. Your answers are saved after every step.");
  });

  it("offers a manual start for non-draft Prisms without a record", async () => {
    const review = prismRow({ id: "r1", name: "Review Prism", state: "onboarding" as never });
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "r1");
    setup([["GET", /prisms\/r1\/onboarding$/, () => { throw { status: 404, detail: "none" }; }]], [review]);
    renderPrisms(<PrismsPage />);
    expect(await screen.findByRole("button", { name: "Let’s get started" })).toBeInTheDocument();
    expect(document.getElementById("prism-conversation-state")).toHaveTextContent("Onboarding");
  });

  it("renders the working agreement and confirms it", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "d1");
    const done = session({ status: "completed", current_question_id: null, answers: [{ question_id: "q1", selected_values: ["a"], custom_text: null, skipped: false }, { question_id: "q2", selected_values: [], custom_text: "Warm", skipped: false }] });
    const agreement = { status: "draft", revision: 2, agreement: { mission: "Watch incidents", attention_signals: ["incidents", "blockers"], teams_scope: "All accessible Teams chats", tone: "Friendly.", safety_rule: "Nothing is sent without approval", allowed_proposals: ["drafts"], restrictions: ["No sends"] } };
    const { calls } = setup([
      ["GET", /prisms\/d1\/onboarding$/, () => done],
      ["GET", /prisms\/d1\/agreement$/, () => agreement],
      ["POST", /agreement\/confirm/, () => ({ agreement: { ...agreement, status: "confirmed" }, prism: { ...draft, state: "active" }, skills_created: 3 })],
      ["GET", /prisms\/d1\/conversation$/, () => ({ messages: [], preferences: [] })],
      ["GET", /teams-policy$/, () => ({ mode: "all_chats", revision: 1, rules: [], last_discovery_at: null, last_discovery_error: null })],
      ["GET", /teams-activity$/, () => ({ items: [] })],
      ["GET", /observations$/, () => ({ items: [] })],
      ["GET", /trigger-policy$/, () => ({ mode: "manual", revision: 1, enabled: true, local_scheduler_enabled: false })],
      ["GET", /prisms\/d1\/runs$/, () => ({ items: [] })],
    ]);
    const { app } = renderPrisms(<PrismsPage />);
    const stream = document.getElementById("prism-onboarding-stream") as HTMLElement;
    await waitFor(() => expect(stream.querySelector(".working-agreement")).toHaveTextContent("My job: Watch incidents."));
    expect(stream.querySelector(".working-agreement")).toHaveTextContent("I’ll bring incidents and blockers to your attention.");
    expect(stream.querySelector(".working-agreement")).toHaveTextContent("Happy with this?");
    expect(document.getElementById("prism-onboarding-form")).toHaveAttribute("hidden");
    await userEvent.click(screen.getByRole("button", { name: "Confirm and activate" }));
    await waitFor(() => expect(app.setStatus).toHaveBeenCalledWith("3 skills created from onboarding. Edit them in this Prism’s settings → Skills.", false));
    expect(calls.find((call) => call.path.endsWith("/agreement/confirm"))?.body).toEqual({ expected_agreement_revision: 2, expected_lifecycle_version: 1 });
    await waitFor(() => expect(document.getElementById("prism-conversation-state")).toHaveTextContent("active"));
  });

  it("renders Prism names, descriptions and model text as text only", async () => {
    const evil = '<img src=x onerror="window.__xss=1">';
    const prism = prismRow({ id: "x1", name: evil, state: "draft" as never, description: evil });
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "x1");
    setup([["GET", /prisms\/x1\/onboarding$/, () => session({ prism_id: "x1", questions: [question("q1", "mission", { prompt: evil, choices: [{ value: "a", label: evil }] })] })]], [prism]);
    renderPrisms(<PrismsPage />);
    await waitFor(() => expect(document.getElementById("prism-onboarding-stream")).toHaveTextContent(evil));
    expect(document.getElementById("prism-conversation-title")).toHaveTextContent(evil);
    expect(document.querySelector("#prism-workspace img")).toBeNull();
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });
});

describe("selection", () => {
  it("shows the empty state until a Prism is chosen", async () => {
    setup([], [draft, prismRow()]);
    renderPrisms(<><PrismSidebarSection /><PrismsPage /></>);
    await screen.findByRole("button", { name: /Sales Prism/ });
    expect(document.getElementById("prism-workspace-empty")).not.toHaveAttribute("hidden");
    expect(document.getElementById("prism-onboarding-workspace")).toHaveAttribute("hidden");
  });
});
