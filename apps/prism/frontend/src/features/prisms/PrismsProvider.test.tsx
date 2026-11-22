import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emit } from "@/lib/events";
import { STORAGE_KEYS } from "@/lib/storage";
import { PrismSidebarSection } from "./PrismSidebarSection";
import { usePrisms } from "./PrismsContext";
import { fakeFetch, prismRow, renderPrisms } from "./test-utils";

const sales = prismRow();
const draft = prismRow({ id: "p2", code: "pDef34", name: "Draft Prism", state: "draft" as never });
const archived = prismRow({ id: "p3", name: "Old Prism", state: "archived" as never });

function Probe() {
  const { prisms, selectedId, loading } = usePrisms();
  return <output data-testid="probe">{`${prisms.length}|${selectedId ?? "none"}|${loading ? "loading" : "idle"}`}</output>;
}

const listRoutes = (rows = [sales, draft]) =>
  fakeFetch([
    ["GET", /^\/api\/v2\/prisms\?include_archived=false/, () => rows],
    ["GET", /^\/api\/v2\/prisms\?include_archived=true/, () => [...rows, archived]],
    ["GET", /updates\/summary/, () => []],
    ["POST", /notifications\/presence/, () => ({})],
  ]);

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("PrismsProvider", () => {
  it("loads the list, selects on click and persists the selection", async () => {
    listRoutes();
    const { app } = renderPrisms(<><Probe /><PrismSidebarSection /></>);
    const draftItem = await screen.findByRole("button", { name: /Draft Prism/ });
    expect(draftItem).toHaveAttribute("aria-current", "false");
    expect(screen.getByTestId("probe")).toHaveTextContent("2|none|idle");

    await userEvent.click(draftItem);
    expect(localStorage.getItem(STORAGE_KEYS.selectedPrism)).toBe("p2");
    expect(screen.getByRole("button", { name: /Draft Prism/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /Draft Prism/ })).toHaveClass("selected");
    expect(app.setActiveTab).toHaveBeenCalledWith("prisms");
    expect(app.routes.prism).toHaveBeenCalledWith(expect.objectContaining({ id: "p2" }));
    expect(app.closeSidebarIfNarrow).toHaveBeenCalled();
  });

  it("opens an active Prism in the chat and tells it", async () => {
    listRoutes();
    const seen: string[] = [];
    const off = (await import("@/lib/events")).on("open-agent", ({ prism }) => seen.push(prism.id));
    const { app } = renderPrisms(<PrismSidebarSection />);
    await userEvent.click(await screen.findByRole("button", { name: /Sales Prism/ }));
    off();
    expect(app.setActiveTab).toHaveBeenCalledWith("agent");
    expect(seen).toContain("p1");
  });

  it("restores the stored selection once the list is in", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "p1");
    listRoutes();
    renderPrisms(<><Probe /><PrismSidebarSection /></>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("2|p1|idle"));
  });

  it("forgets a stored selection that is no longer listed", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "gone");
    listRoutes();
    const events: string[] = [];
    const off = (await import("@/lib/events")).on("no-prism-selected", () => events.push("none"));
    renderPrisms(<><Probe /><PrismSidebarSection /></>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("2|none|idle"));
    off();
    expect(localStorage.getItem(STORAGE_KEYS.selectedPrism)).toBeNull();
    expect(events).toEqual(["none"]);
  });

  it("does not auto-select a stored Prism when a deep link was requested", async () => {
    localStorage.setItem(STORAGE_KEYS.selectedPrism, "p1");
    listRoutes();
    const routes = { prism: vi.fn(), workspace: vi.fn(), requestedPrism: "pDef34", requestedLegacy: false };
    renderPrisms(<><Probe /><PrismSidebarSection /></>, { routes });
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("2|none|idle"));
  });

  it("auto-selects the only Prism", async () => {
    listRoutes([sales]);
    renderPrisms(<Probe />);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("1|p1|idle"));
    expect(localStorage.getItem(STORAGE_KEYS.selectedPrism)).toBe("p1");
  });

  it("includes archived Prisms from the toggle and labels them", async () => {
    const { calls } = listRoutes();
    renderPrisms(<PrismSidebarSection />);
    await screen.findByRole("button", { name: /Draft Prism/ });
    const toggle = screen.getByRole("button", { name: "Show archived Prisms" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(toggle);
    await screen.findByRole("button", { name: /Old Prism/ });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(toggle).toHaveAttribute("data-tooltip", "Hide archived");
    expect(calls.some((call) => call.path.endsWith("include_archived=true"))).toBe(true);
    expect(screen.getByText("archived")).toHaveClass("nav-count");
    expect(screen.getByText("Draft")).toHaveClass("nav-count");
  });

  it("reloads on prisms-changed and shows the empty text", async () => {
    let rows: typeof sales[] = [];
    fakeFetch([
      ["GET", /api\/v2\/prisms\?/, () => rows],
      ["GET", /updates\/summary/, () => []],
      ["POST", /presence/, () => ({})],
    ]);
    renderPrisms(<PrismSidebarSection />);
    await screen.findByText("No Prisms yet.");
    rows = [sales];
    act(() => emit("prisms-changed"));
    await screen.findByRole("button", { name: /Sales Prism/ });
  });

  it("adds, selects and opens the Prism the URL layer resolved", async () => {
    listRoutes([sales]);
    const { app } = renderPrisms(<><Probe /><PrismSidebarSection /></>);
    await screen.findByRole("button", { name: /Sales Prism/ });
    act(() => emit("open-prism-route", { prism: draft }));
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("2|p2|idle"));
    expect(app.setActiveTab).toHaveBeenLastCalledWith("prisms");
    expect(app.routes.prism).toHaveBeenCalledWith(expect.objectContaining({ id: "p2" }));
  });

  it("opens a Prism by id and reports a search hit that is gone", async () => {
    listRoutes();
    const { app } = renderPrisms(<><Probe /><PrismSidebarSection /></>);
    await screen.findByRole("button", { name: /Draft Prism/ });
    act(() => emit("open-prism", { id: "p2" }));
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("2|p2|idle"));
    await act(async () => emit("search-result", { prismId: "missing" }));
    await waitFor(() => expect(app.setStatus).toHaveBeenCalledWith("This Prism is no longer available.", true));
  });

  it("merges prism-updated into the list", async () => {
    listRoutes();
    renderPrisms(<PrismSidebarSection />);
    await screen.findByRole("button", { name: /Sales Prism/ });
    act(() => emit("prism-updated", { prism: { id: "p1", name: "Renamed" } }));
    expect(await screen.findByRole("button", { name: /Renamed/ })).toBeInTheDocument();
  });
});
