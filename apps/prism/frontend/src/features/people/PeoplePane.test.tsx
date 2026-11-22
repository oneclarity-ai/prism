import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { installDialogPolyfill } from "@/test/dialog";
import { renderWithApp } from "@/test/render";
import { mockFetch } from "../workspace/test-fetch";
import { PeoplePane } from "./PeoplePane";
import { PrismPeopleScope } from "./PrismPeopleScope";
import { resetPeople, type Person } from "./people-store";

beforeAll(installDialogPolyfill);
beforeEach(() => resetPeople());

const base = { in_chats: true, in_team: false, is_managed: false, is_me: false, last_chat_at: null, notes: null, overrides: [] as string[], responsibilities: null, direct_report_count: 0, manager_id: null, manager_name: null, department: null };
const boss: Person = { ...base, id: "boss", name: "Bela Boss", email: "bela@x.test", title: "VP", relationship: "Your manager", in_chats: false };
const me: Person = { ...base, id: "me", name: "Yash Mandi", email: "yash@x.test", title: "Manager", department: "Eng", relationship: "You", is_me: true, manager_id: "boss", manager_name: "Bela Boss", direct_report_count: 1 };
const asha: Person = { ...base, id: "asha", name: "Asha <b>Rao</b>", email: "asha@x.test", title: "Engineer", relationship: "Reports to you", manager_id: "me", manager_name: "Yash Mandi" };

function directory(extra: Person[] = []) {
  let state = { me, people: [boss, asha, ...extra] };
  const calls = mockFetch([
    ["GET", /^\/api\/v1\/people$/, () => ({ ...state, synced_at: "2026-01-01T10:00:00Z" })],
    ["PATCH", /^\/api\/v1\/people\/asha$/, (_u, init) => {
      const edit = JSON.parse(String(init.body)) as Partial<Person>;
      state = { ...state, people: state.people.map((p) => (p.id === "asha" ? { ...p, ...edit, overrides: ["title"] } : p)) };
      return state;
    }],
  ]);
  return calls;
}

describe("PeoplePane", () => {
  it("shows me, grouped people with text-only names, and filters by search", async () => {
    directory();
    renderWithApp(<PeoplePane />);
    expect(await screen.findByText("Reports to you")).toHaveClass("people-group-title");
    expect(document.getElementById("people-me")).toHaveTextContent("Reports to Bela Boss · 1 direct report");
    const row = screen.getByText("Asha <b>Rao</b>").closest(".person-row") as HTMLElement;
    expect(row).toHaveTextContent("Reports to Yash Mandi");
    expect(document.querySelector("#people-list b")).toBeNull();
    expect(screen.getByText("Org link")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search people"), "zzz");
    expect(document.getElementById("people-list")).toHaveTextContent("Nobody matches that search.");
  });

  it("nests the org chart view under managers", async () => {
    directory();
    renderWithApp(<PeoplePane />);
    await screen.findByText("Reports to you");
    await userEvent.click(document.querySelector("[data-people-view='tree']")!);
    expect(document.querySelector(".org-tree .org-tree .org-tree .person-row")).toHaveTextContent("Asha");
  });

  it("edits a person through the dialog and marks the row edited", async () => {
    const calls = directory();
    const { app } = renderWithApp(<PeoplePane />);
    await userEvent.click((await screen.findByText("Asha <b>Rao</b>")).closest("button")!);
    const dialog = document.getElementById("person-edit-dialog") as HTMLDialogElement;
    expect(dialog).toHaveAttribute("open");
    expect(within(dialog).getByRole("heading")).toHaveTextContent("Asha <b>Rao</b>");
    const title = document.getElementById("person-edit-title") as HTMLInputElement;
    await userEvent.clear(title);
    await userEvent.type(title, "Tech Lead");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ title: "Tech Lead" }));
    expect(app.setStatus).toHaveBeenCalledWith("Saved. Prism will use this from now on.");
    await waitFor(() => expect(dialog).not.toHaveAttribute("open"));
    expect(screen.getByText("Edited")).toBeInTheDocument();
  });

  it("opens the 'about me' editor with the self wording", async () => {
    directory();
    renderWithApp(<PeoplePane />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit about me" }));
    expect(document.getElementById("person-edit-name")).toHaveTextContent("About you, Yash");
    expect(document.getElementById("person-edit-responsibilities-label")).toHaveTextContent("What you do");
  });
});

describe("PrismPeopleScope", () => {
  it("saves the scope and the picked people", async () => {
    const calls = mockFetch([
      ["GET", /^\/api\/v1\/people$/, () => ({ me, people: [boss, asha], synced_at: null })],
      ["GET", /^\/api\/v2\/prisms\/p1\/people$/, () => ({ scope: "selected", employee_ids: [] })],
      ["PUT", /^\/api\/v2\/prisms\/p1\/people$/, () => ({})],
    ]);
    renderWithApp(<PrismPeopleScope prismId="p1" prismName="Sales" />);
    expect(await screen.findByText(/Choose who Sales knows about/)).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(await screen.findByRole("switch", { name: /Bela Boss/ }));
    });
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ scope: "selected", employee_ids: ["boss"] }));
  });
});
