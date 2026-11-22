import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { on } from "@/lib/events";
import { fakeFetch, prismRow, renderPrisms } from "./test-utils";
import { PrismSidebarSection } from "./PrismSidebarSection";

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Teams updates poller", () => {
  it("posts presence, publishes summaries, repeats every 15s and stops on unmount", async () => {
    const { calls } = fakeFetch([
      ["GET", /api\/v2\/prisms\?/, () => [prismRow()]],
      ["GET", /updates\/summary/, () => [{ prism_id: "p1", unread: 2, urgent_unread: 0 }]],
      ["POST", /notifications\/presence/, () => ({})],
    ]);
    const seen: Array<Map<string, unknown>> = [];
    const off = on("updates", ({ summaries }) => seen.push(summaries));
    const view = renderPrisms(<PrismSidebarSection />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    const count = (path: string) => calls.filter((call) => call.path.includes(path)).length;
    expect(count("notifications/presence")).toBe(1);
    expect(calls.find((call) => call.path.includes("presence"))?.body).toEqual({ client_id: expect.any(String) });
    expect(seen).toHaveLength(1);
    expect(seen[0].get("p1")).toMatchObject({ unread: 2 });
    expect(await screen.findByRole("button", { name: "Sales Prism, 2 unread updates" })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(count("notifications/presence")).toBe(2);

    view.unmount();
    off();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(count("notifications/presence")).toBe(2);
  });

  it("does not poll while v22 mode is off", async () => {
    const { calls } = fakeFetch([]);
    renderPrisms(<div />, { modes: { v21: false, v22: false, v24: false, singleExecutive: false } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(40000);
    });
    expect(calls).toHaveLength(0);
  });

  it("survives a failing poll and retries", async () => {
    let fail = true;
    const { calls } = fakeFetch([
      ["GET", /api\/v2\/prisms\?/, () => []],
      ["POST", /presence/, () => {
        if (fail) throw { status: 500, detail: "down" };
        return {};
      }],
      ["GET", /updates\/summary/, () => []],
    ]);
    renderPrisms(<div />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    fail = false;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(calls.filter((call) => call.path.includes("updates/summary")).length).toBeGreaterThan(0);
  });
});
