import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FormDialogProvider } from "@/components/ui";
import { AppContext } from "@/lib/app-context";
import { on } from "@/lib/events";
import { fakeApp } from "@/test/render";
import { SkillLibrary } from "./SkillLibrary";
import { ArchivedPrismsPane } from "./ArchivedPrismsPane";
import { PrismSkillRows } from "./skills";
import { fakeFetch, prismRow } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

function renderWith(ui: React.ReactElement, app = fakeApp()) {
  const result = render(
    <AppContext.Provider value={app}>
      <FormDialogProvider>{ui}</FormDialogProvider>
    </AppContext.Provider>,
  );
  return { ...result, app };
}

const own = {
  id: "s1", name: "Account research", description: "Research accounts", instructions: "Cite sources", required_tools: ["save_file"], required_connections: ["outlook"],
  revision: 2, archived: false, owner_prism_id: "p1", assignment_revision: 1, enabled: true, approved_revision: 1, approved_definition: { id: "s1", name: "Approved name", description: "Approved desc", instructions: "Old instructions", required_tools: [], required_connections: [], revision: 1, archived: false },
  missing: ["Tool access is off: save_file", "Connection not supported yet: outlook"],
};
const shared = { id: "s2", name: "Shared brief", description: "Briefs", instructions: "Write", required_tools: [], required_connections: [], revision: 1, archived: false, owner_prism_id: null, missing: [] };

describe("PrismSkillRows", () => {
  it("renders stats, cards, requirements and reports the enabled count", async () => {
    fakeFetch([["GET", /prisms\/p1\/skills$/, () => ({ skills: [own, shared], tool_labels: { save_file: "Save file" } })]]);
    const onCount = vi.fn();
    renderWith(<PrismSkillRows prism={prismRow()} onCount={onCount} />);
    expect(screen.getByText("Loading skills…")).toBeInTheDocument();
    await screen.findByText("Approved name");
    expect(onCount).toHaveBeenCalledWith(1);
    const stats = document.querySelectorAll(".skill-stat strong");
    expect([...stats].map((node) => node.textContent)).toEqual(["1", "1", "1"]);
    expect(screen.getByText("Needs access")).toBeInTheDocument();
    expect(screen.getByText("Enable Save file in Tools")).toBeInTheDocument();
    expect(screen.getByText("Outlook integration is not available yet")).toBeInTheDocument();
    expect(screen.getByText("Using revision 1. Library revision 2 is available.")).toBeInTheDocument();
    expect(screen.getByText("Private to this Prism · From onboarding")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disable Approved name" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Workspace library · 1 available")).toBeInTheDocument();
  });

  it("toggles a skill with the revisions it saw", async () => {
    let data = { skills: [shared] };
    const { calls } = fakeFetch([
      ["GET", /prisms\/p1\/skills$/, () => data],
      ["PUT", /prisms\/p1\/skills\/s2$/, () => {
        data = { skills: [{ ...shared, assignment_revision: 1, enabled: true, approved_revision: 1, approved_definition: shared } as never] };
        return {};
      }],
    ]);
    const changed = vi.fn();
    const off = on("skills-changed", changed);
    renderWith(<PrismSkillRows prism={prismRow()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Enable Shared brief" }));
    await screen.findByRole("button", { name: "Disable Shared brief" });
    off();
    expect(calls.find((call) => call.method === "PUT")?.body).toEqual({ enabled: true, expected_skill_revision: 1 });
    expect(changed).toHaveBeenCalled();
  });

  it("edits a private skill in a dialog and reloads", async () => {
    let name = "Account research";
    const { calls } = fakeFetch([
      ["GET", /prisms\/p1\/skills$/, () => ({ skills: [{ ...own, name, enabled: false, missing: [] }] })],
      ["PUT", /skills\/s1\/definition$/, (body) => {
        name = (body as { name: string }).name;
        return {};
      }],
    ]);
    renderWith(<PrismSkillRows prism={prismRow()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit skill" }));
    const dialog = document.querySelector("dialog.workspace-dialog") as HTMLElement;
    const field = within(dialog).getByLabelText("Skill name");
    await userEvent.clear(field);
    await userEvent.type(field, "Renamed workflow");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByText("Renamed workflow");
    expect(calls.find((call) => call.method === "PUT")?.body).toMatchObject({
      name: "Renamed workflow", required_tools: ["save_file"], required_connections: ["outlook"], expected_revision: 2, expected_assignment_revision: 1, archived: false,
    });
  });

  it("creates skills from onboarding for an active Prism with none", async () => {
    const { calls } = fakeFetch([
      ["GET", /prisms\/p1\/skills$/, () => ({ skills: [] })],
      ["POST", /from-onboarding$/, () => ({ skills_created: 3 })],
    ]);
    const { app } = renderWith(<PrismSkillRows prism={prismRow()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Create 3 skills from onboarding" }));
    await waitFor(() => expect(app.setStatus).toHaveBeenCalledWith("3 skills created from onboarding. Edit them here in Skills."));
    expect(calls.filter((call) => call.path.endsWith("/skills") && call.method === "GET").length).toBeGreaterThan(1);
  });

  it("is read-only for archived Prisms and offers retry on failure", async () => {
    fakeFetch([["GET", /skills$/, () => ({ skills: [shared] })]]);
    renderWith(<PrismSkillRows prism={prismRow({ state: "archived" as never })} />);
    expect(await screen.findByRole("button", { name: "Enable Shared brief" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add shared skill" })).toBeDisabled();
    vi.unstubAllGlobals();
    fakeFetch([["GET", /skills$/, () => { throw { status: 500, detail: "nope" }; }]]);
    renderWith(<PrismSkillRows prism={prismRow()} />);
    expect(await screen.findByText("nope")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("renders skill text safely", async () => {
    const evil = '<img src=x onerror="window.__xss=1">';
    fakeFetch([["GET", /skills$/, () => ({ skills: [{ ...shared, name: evil, description: evil, instructions: evil, assignment_revision: 1, enabled: false }] })]]);
    renderWith(<PrismSkillRows prism={prismRow()} />);
    await screen.findByRole("heading", { name: evil });
    expect(document.querySelector(".prism-skill-card img")).toBeNull();
  });
});

describe("SkillLibrary", () => {
  it("lists, adds and archives shared skills", async () => {
    let skills = [shared];
    const { calls } = fakeFetch([
      ["GET", /skills\/library$/, () => skills],
      ["POST", /skills\/library$/, (body) => {
        skills = [...skills, { ...shared, id: "s3", name: (body as { name: string }).name }];
        return {};
      }],
      ["PUT", /skills\/library\/s2$/, () => {
        skills = [{ ...shared, archived: true }, ...skills.slice(1)];
        return {};
      }],
    ]);
    const { app } = renderWith(<SkillLibrary />);
    await screen.findByText("Shared brief");
    expect(screen.getByText("Skill")).toHaveClass("workspace-chip");
    await userEvent.click(screen.getByRole("button", { name: "Add skill" }));
    const dialog = document.querySelector("dialog.workspace-dialog") as HTMLElement;
    await userEvent.type(within(dialog).getByLabelText("Skill name"), "Written brief");
    await userEvent.type(within(dialog).getByLabelText("What this skill does"), "d");
    await userEvent.type(within(dialog).getByLabelText("Reusable instructions"), "i");
    await userEvent.type(within(dialog).getByLabelText(/Required tool identifiers/), "Teams_Read, teams_read");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByText("Written brief");
    expect(calls.find((call) => call.method === "POST")?.body).toMatchObject({ name: "Written brief", required_tools: ["teams_read"], required_connections: [] });

    await userEvent.click(screen.getAllByRole("button", { name: "Archive" })[0]);
    expect(app.askDialog).toHaveBeenCalledWith({ title: "Archive this shared skill?", message: expect.any(String), confirmLabel: "Archive" });
    await screen.findByText("Archived skill");
    expect(calls.find((call) => call.method === "PUT")?.body).toMatchObject({ archived: true, expected_revision: 1, name: "Shared brief" });
    expect(screen.getByRole("button", { name: "Restore" })).toBeInTheDocument();
  });

  it("shows the empty and error states", async () => {
    fakeFetch([["GET", /skills\/library$/, () => []]]);
    const first = renderWith(<SkillLibrary />);
    expect(await screen.findByText("No shared skills yet")).toBeInTheDocument();
    first.unmount();
    vi.unstubAllGlobals();
    fakeFetch([["GET", /skills\/library$/, () => { throw { status: 500, detail: "bad" }; }]]);
    renderWith(<SkillLibrary />);
    expect(await screen.findByText("Skills could not load")).toBeInTheDocument();
  });
});

describe("ArchivedPrismsPane", () => {
  it("lists archived Prisms only and deletes after confirmation", async () => {
    let rows = [prismRow({ id: "a", name: "Old", state: "archived" as never }), prismRow()];
    const { calls } = fakeFetch([
      ["GET", /api\/v2\/prisms\?include_archived=true/, () => rows],
      ["DELETE", /prisms\/a$/, () => { rows = [prismRow()]; return null; }],
    ]);
    const { app } = renderWith(<ArchivedPrismsPane />);
    await screen.findByText("Old");
    expect(screen.queryByText("Sales Prism")).toBeNull();
    const seen = vi.fn();
    const off = on("prisms-changed", seen);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await screen.findByText("No archived Prisms.");
    off();
    expect(app.askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Delete Old?", danger: true }));
    expect(seen).toHaveBeenCalled();
    expect(app.setStatus).toHaveBeenCalledWith("Old deleted.");
    expect(calls.some((call) => call.method === "DELETE")).toBe(true);
    await act(async () => {});
  });
});
