import { act, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { emit } from "@/lib/events";
import { PrismCreateButton } from "./PrismCreateButton";
import { PrismSidebarSection } from "./PrismSidebarSection";
import { fakeFetch, prismRow, renderPrisms } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

const base = [
  ["GET", /updates\/summary/, () => []],
  ["POST", /presence/, () => ({})],
] as const;

describe("PrismSidebarSection", () => {
  it("renders names, previews, times and unread badges", async () => {
    const rows = [
      prismRow({ last_message_at: new Date().toISOString(), last_message_preview: "On it", last_message_role: "manager" }),
      prismRow({ id: "p2", name: "Quiet Prism" }),
    ];
    fakeFetch([["GET", /api\/v2\/prisms\?/, () => rows], ...base]);
    renderPrisms(<PrismSidebarSection />);
    const sales = await screen.findByRole("button", { name: /Sales Prism/ });
    expect(sales).toHaveAttribute("title", rows[0].description);
    expect(within(sales).getByText("You: On it")).toHaveClass("prism-nav-preview");
    expect(sales.querySelector("time.prism-nav-time")).toBeInTheDocument();
    expect(sales.querySelector(".nav-logo")).toHaveAttribute("data-color");
    expect(within(screen.getByRole("button", { name: /Quiet Prism/ })).getByText("No messages yet")).toBeInTheDocument();

    act(() => emit("updates", { summaries: new Map([["p1", { prism_id: "p1", unread: 3, urgent_unread: 1 }], ["p2", { prism_id: "p2", unread: 1, urgent_unread: 0 }]]) }));
    const urgent = await screen.findByRole("button", { name: "Sales Prism, 3 unread updates, 1 urgent" });
    expect(within(urgent).getByText("3")).toHaveClass("nav-count", "urgent");
    const calm = screen.getByRole("button", { name: "Quiet Prism, 1 unread update" });
    expect(within(calm).getByText("1")).toHaveClass("nav-count", "approval");
  });

  it("is hidden until the v22 mode is on", () => {
    fakeFetch([...base]);
    renderPrisms(<PrismSidebarSection />, { modes: { v21: false, v22: false, v24: false, singleExecutive: false } });
    expect(document.getElementById("prism-directory-list")).toHaveAttribute("hidden");
    expect(document.getElementById("prism-archived-button")).toHaveAttribute("data-v22-only");
  });

  it("renders Prism names and descriptions as text, never HTML", async () => {
    const evil = '<img src=x onerror="window.__xss=1"><b>bold</b>';
    fakeFetch([["GET", /api\/v2\/prisms\?/, () => [prismRow({ name: evil, description: evil, last_message_preview: evil })]], ...base]);
    renderPrisms(<PrismSidebarSection />);
    const list = await screen.findByRole("button", { name: /onerror/ });
    expect(list.querySelector("img")).toBeNull();
    expect(list.querySelector("b")).toBeNull();
    expect(screen.getAllByText(evil).length).toBeGreaterThan(0);
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it("has a create button hidden outside v22", () => {
    fakeFetch([...base]);
    renderPrisms(<PrismCreateButton />, { modes: { v21: false, v22: null, v24: false, singleExecutive: false } });
    expect(document.getElementById("prism-create-button")).toHaveAttribute("hidden");
  });
});
