import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockFetch } from "@/features/legacy/testing";
import { emit, on } from "@/lib/events";
import { getThemeChoice } from "@/lib/prefs";
import { renderWithApp } from "@/test/render";
import { CommandPalette } from "./CommandPalette";
import { highlightParts, score, type SearchRow } from "./logic";

const prisms = [
  { id: "p1", name: "Sales Scout", job_role: "Researcher", department: "Sales", description: "Finds accounts" },
  { id: "p2", name: "Old Timer", archived: true },
];

let net: ReturnType<typeof mockFetch>;
beforeEach(() => {
  localStorage.clear();
  net = mockFetch({ "GET /api/v2/prisms/search": [] });
});
afterEach(() => vi.unstubAllGlobals());

const dialog = () => document.getElementById("search-dialog") as HTMLDialogElement;
const input = () => document.getElementById("search-input") as HTMLInputElement;
const labels = () => [...document.querySelectorAll(".search-item .search-label")].map((node) => node.textContent);

function setup(app = {}) {
  const view = renderWithApp(<CommandPalette />, { prisms: { list: prisms }, app });
  return view;
}

function openPalette() {
  act(() => emit("open-search"));
}

describe("opening", () => {
  it("opens on the open-search bus event with the input focused and the default rows", () => {
    setup({ modes: { v21: false, v22: true, v24: false, singleExecutive: false } });
    expect(dialog()).not.toHaveAttribute("open");
    openPalette();
    expect(dialog()).toHaveAttribute("open");
    expect(input()).toHaveFocus();
    expect(labels()).toEqual(["Sales Scout", "Chats", "Spending", "Create Prism", "Open Settings", "Theme: Light", "Theme: Dark"]);
    expect([...document.querySelectorAll(".search-group")].map((node) => node.textContent)).toEqual(["Prisms", "Go to", "Actions"]);
  });

  it("toggles with Ctrl+K and Cmd+K", () => {
    setup();
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    expect(dialog()).toHaveAttribute("open");
    fireEvent.keyDown(document, { key: "K", metaKey: true });
    expect(dialog()).not.toHaveAttribute("open");
  });

  it("resets the query every time it opens", async () => {
    setup();
    openPalette();
    await userEvent.type(input(), "dark");
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    openPalette();
    expect(input()).toHaveValue("");
  });

  it("closes on a backdrop click and on Escape", () => {
    setup();
    openPalette();
    fireEvent.click(dialog());
    expect(dialog()).not.toHaveAttribute("open");
    openPalette();
    act(() => {
      dialog().close();
    });
    expect(dialog()).not.toHaveAttribute("open");
  });

  it("hides workspace-only rows until the modes are on", () => {
    setup({ modes: { v21: false, v22: false, v24: false, singleExecutive: false } });
    openPalette();
    expect(labels()).not.toContain("Spending");
    expect(labels()).not.toContain("Create Prism");
  });

  it("fetches the Prism list when the shared one is empty", async () => {
    net.set("GET /api/v2/prisms", [{ id: "x", name: "Fetched Prism" }]);
    renderWithApp(<CommandPalette />);
    openPalette();
    await waitFor(() => expect(labels()).toContain("Fetched Prism"));
    expect(net.callsTo("GET", "/api/v2/prisms")[0].url).toContain("include_archived=false");
  });
});

describe("filtering and listbox", () => {
  it("filters across pages, Prisms, settings and actions and highlights the match", async () => {
    setup();
    openPalette();
    await userEvent.type(input(), "dark");
    expect(labels()).toEqual(["Theme: Dark"]);
    expect(document.querySelector(".search-label mark")).toHaveTextContent("Dark");
    expect(screen.getByRole("status")).toHaveTextContent("1 results");
  });

  it("finds settings rows with their section and archived Prisms are never listed", async () => {
    setup();
    openPalette();
    await userEvent.type(input(), "contrast");
    expect(labels()).toEqual(["High contrast"]);
    expect(document.querySelector(".search-sub")).toHaveTextContent("Settings › Preferences");
    await userEvent.clear(input());
    await userEvent.type(input(), "old timer");
    expect(labels()).toEqual([]);
    expect(screen.getByRole("status")).toHaveTextContent("No results");
    await userEvent.clear(input());
    await userEvent.type(input(), "~");
    expect(screen.getByText("No results for “~”.")).toBeInTheDocument();
  });

  it("searches Prism role, department and description keywords", async () => {
    setup();
    openPalette();
    await userEvent.type(input(), "accounts");
    expect(labels()).toEqual(["Sales Scout"]);
  });

  it("has combobox/listbox/option semantics with a moving aria-activedescendant", async () => {
    setup();
    openPalette();
    expect(input()).toHaveAttribute("role", "combobox");
    expect(screen.getByRole("listbox", { name: "Results" })).toBeInTheDocument();
    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    expect(input()).toHaveAttribute("aria-activedescendant", "search-option-0");
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    expect(input()).toHaveAttribute("aria-activedescendant", "search-option-1");
    expect(screen.getAllByRole("group").map((group) => group.getAttribute("aria-label"))).toEqual(["Prisms", "Pages", "Actions"]);
  });

  it("wraps with the arrow keys and jumps with Ctrl+Home/End", async () => {
    setup();
    openPalette();
    const count = screen.getAllByRole("option").length;
    await userEvent.keyboard("{ArrowUp}");
    expect(screen.getAllByRole("option")[count - 1]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{Control>}{End}{/Control}");
    expect(screen.getAllByRole("option")[count - 1]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{Control>}{Home}{/Control}");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
  });

  it("follows the pointer", async () => {
    setup();
    openPalette();
    fireEvent.pointerMove(screen.getAllByRole("option")[2]);
    expect(screen.getAllByRole("option")[2]).toHaveAttribute("aria-selected", "true");
  });
});

describe("activating rows", () => {
  it("Enter runs the selected action and closes", async () => {
    setup();
    openPalette();
    await userEvent.type(input(), "theme: dark{Enter}");
    expect(dialog()).not.toHaveAttribute("open");
    await waitFor(() => expect(getThemeChoice()).toBe("dark"));
  });

  it("display size rows use setUiSize", async () => {
    setup();
    openPalette();
    await userEvent.type(input(), "display size large");
    await userEvent.click(screen.getAllByRole("option").find((option) => option.textContent?.includes("Display size: Large")) as HTMLElement);
    await waitFor(() => expect(localStorage.getItem("prism-pref-ui-size")).toBe("large"));
  });

  it("a Prism row selects the chat sidebar and opens that Prism", async () => {
    const opened = vi.fn();
    const off = on("open-prism", opened);
    const view = setup();
    openPalette();
    await userEvent.type(input(), "scout");
    await userEvent.click(screen.getAllByRole("option")[0]);
    await waitFor(() => expect(opened).toHaveBeenCalledWith({ id: "p1" }));
    expect(view.app.setSidebarSection).toHaveBeenCalledWith("chat");
    off();
  });

  it("page and settings rows navigate through the shell", async () => {
    const view = setup();
    openPalette();
    await userEvent.type(input(), "spending");
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(view.app.setActiveTab).toHaveBeenCalledWith("spending"));
    openPalette();
    await userEvent.type(input(), "time zone{Enter}");
    await waitFor(() => expect(view.app.settings.open).toHaveBeenCalledWith("preferences"));
  });

  it("workspace pages emit workspace-navigate and switch the sidebar", async () => {
    const navigate = vi.fn();
    const off = on("workspace-navigate", navigate);
    const view = setup();
    openPalette();
    await userEvent.type(input(), "run analytics{Enter}");
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ page: "usage" }));
    expect(view.app.setSidebarSection).toHaveBeenCalledWith("workspace");
    off();
  });

  it("Refresh data calls the shell refresh", async () => {
    const view = setup();
    openPalette();
    await userEvent.type(input(), "refresh data{Enter}");
    await waitFor(() => expect(view.app.refresh).toHaveBeenCalled());
  });
});

describe("conversation search", () => {
  it("debounces, queries the server and lists matching messages under Chats", async () => {
    net.set("GET /api/v2/prisms/search", [
      { kind: "prism", prism_id: "p1", prism_name: "Sales Scout", snippet: "", message_id: null, role: null, created_at: null },
      { kind: "message", prism_id: "p1", prism_name: "Sales Scout", snippet: "the <b>release</b> plan", message_id: "m1", role: "manager", created_at: "2026-01-02T10:00:00Z" },
    ]);
    const found = vi.fn();
    const off = on("search-result", found);
    setup();
    openPalette();
    await userEvent.type(input(), "release");
    expect(screen.getByText("Searching conversations…")).toBeInTheDocument();
    expect(net.callsTo("GET", "/api/v2/prisms/search")).toHaveLength(0);
    await waitFor(() => expect(document.querySelector(".search-snippet")).toBeInTheDocument(), { timeout: 2000 });
    expect(net.callsTo("GET", "/api/v2/prisms/search")).toHaveLength(1);
    expect(net.callsTo("GET", "/api/v2/prisms/search")[0].url).toContain("q=release");
    // Untrusted snippet text stays text.
    expect(document.querySelector(".search-snippet")?.textContent).toBe("the <b>release</b> plan");
    expect(document.querySelector(".search-snippet b")).toBeNull();
    expect(document.querySelector(".search-sub")?.textContent).toMatch(/^You · /);
    await userEvent.click(document.querySelector(".search-snippet")!.closest(".search-item") as HTMLElement);
    await waitFor(() => expect(found).toHaveBeenCalledWith({ prismId: "p1", message: { id: "m1", created_at: "2026-01-02T10:00:00Z" } }));
    off();
  });

  it("says when nothing matched and when the search failed", async () => {
    setup();
    openPalette();
    await userEvent.type(input(), "zzqq");
    await waitFor(() => expect(screen.getByText("No conversation matches.")).toBeInTheDocument(), { timeout: 2000 });
    net.set("GET /api/v2/prisms/search", () => ({ __reply: { status: 500, json: { detail: "no" } } }));
    await userEvent.clear(input());
    await userEvent.type(input(), "yyxx");
    await waitFor(() => expect(screen.getByText("Conversations could not be searched.")).toBeInTheDocument(), { timeout: 2000 });
  });

  it("does not search for a single character", async () => {
    setup();
    openPalette();
    await userEvent.type(input(), "z");
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(net.callsTo("GET", "/api/v2/prisms/search")).toHaveLength(0);
  });
});

describe("matching helpers", () => {
  const row = (label: string, sub = "", keywords = ""): SearchRow => ({ kind: "page", label, sub, keywords, run: () => {} });
  it("ranks prefix over word-start over substring over keyword and rejects misses", () => {
    expect(score(row("Spending"), ["spe"])).toBe(4);
    expect(score(row("Run analytics"), ["ana"])).toBe(3);
    expect(score(row("Spending"), ["end"])).toBe(2);
    expect(score(row("Spending", "", "cost"), ["cost"])).toBe(1);
    expect(score(row("Spending"), ["zzz"])).toBe(-1);
    expect(score(row("Spending cost"), ["spe", "cost"])).toBe(7);
  });
  it("splits around the earliest hit", () => {
    expect(highlightParts("Theme: Dark", ["dark"])).toEqual(["Theme: ", "Dark", ""]);
    expect(highlightParts("Nothing", ["zz"])).toEqual(["Nothing", null, ""]);
  });
});
