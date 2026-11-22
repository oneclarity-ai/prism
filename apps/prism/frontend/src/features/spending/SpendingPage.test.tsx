import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockFetch } from "@/features/legacy/testing";
import { renderWithApp } from "@/test/render";
import { AppContext } from "@/lib/app-context";
import { fakeApp } from "@/test/render";
import { CurrencyToggle } from "./CurrencyToggle";
import { costStore, formatMoney, useTodayAiCost } from "./costStore";
import { SpendingPage } from "./SpendingPage";

const item = { calls: 1, estimated_cost_usd: "0.12", unpriced_calls: 0, input_tokens: 100, cached_input_tokens: 0, output_tokens: 20 };
const periods = Object.fromEntries(
  ["today", "week", "month", "total"].map((name) => [name, { prism: item, swarm: { ...item, estimated_cost_usd: "0.08" } }]),
);
const usage = {
  timezone: "Asia/Kolkata",
  range: { from: "2026-11-01", to: "2026-11-21" },
  periods,
  by_feature: {
    prism: [{ ...item, group: "prism_work_plan" }],
    swarm: [{ ...item, estimated_cost_usd: "0.08", group: "qa_tester_test_runs" }],
  },
  by_model: {
    prism: [{ ...item, group: "test-model" }],
    swarm: [{ ...item, estimated_cost_usd: "0.08", group: "test-model" }],
  },
  by_provider: [
    { ...item, group: "openai" },
    { ...item, group: "qa_workspace", estimated_cost_usd: "0.08" },
  ],
};
const RATE = "GET https://open.er-api.com/v6/latest/USD";

let net: ReturnType<typeof mockFetch>;
beforeEach(() => {
  localStorage.clear();
  costStore.reset();
  net = mockFetch({
    [RATE]: { rates: { INR: 83 } },
    "GET /api/v1/usage/llm/sources": usage,
    "GET /api/v1/usage/llm/azure-billed": { configured: false },
  });
});
afterEach(() => vi.unstubAllGlobals());

const cost = (key: string) => document.querySelector(`[data-cost="${key}"]`) as HTMLElement;

describe("SpendingPage", () => {
  it("shows placeholders first, then totals per source and period in rupees", async () => {
    renderWithApp(<SpendingPage />);
    expect(cost("all:today")).toHaveTextContent("—");
    expect(document.getElementById("settings-provider-costs")).toHaveTextContent("Loading provider costs…");
    await waitFor(() => expect(cost("all:today")).toHaveTextContent("₹16.60"));
    // 0.12 + 0.08 = 0.20 USD * 83
    expect(cost("prism:today")).toHaveTextContent("₹9.960");
    expect(cost("swarm:month")).toHaveTextContent("₹6.640");
    expect(document.getElementById("settings-cost-total")).toHaveTextContent("₹16.60");
    expect(document.getElementById("cost-updated")).toHaveTextContent(/^1 USD = ₹83\.00 · Updated /);
    expect(document.getElementById("cost-note")).toHaveTextContent("Estimated from exact token counts and each model's rate, Asia/Kolkata days.");
  });

  it("switches to dollars with the currency toggle and remembers it", async () => {
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(cost("all:today")).toHaveTextContent("₹"));
    await userEvent.click(document.querySelector('[data-currency="USD"]') as HTMLElement);
    expect(document.getElementById("settings-cost-total")).toHaveTextContent("$0.2000");
    expect(cost("prism:week")).toHaveTextContent("$0.1200");
    expect(document.querySelector('[data-currency="USD"]')).toHaveAttribute("aria-pressed", "true");
    expect(document.querySelector('[data-currency="INR"]')).toHaveAttribute("aria-pressed", "false");
    expect(localStorage.getItem("prism-currency")).toBe("USD");
    expect(document.getElementById("cost-updated")).not.toHaveTextContent("1 USD");
    // No second request is needed for a currency change.
    expect(net.callsTo("GET", "/api/v1/usage/llm/sources")).toHaveLength(1);
  });

  it("lists providers by cost with friendly names", async () => {
    renderWithApp(<SpendingPage />);
    const box = document.getElementById("settings-provider-costs") as HTMLElement;
    await waitFor(() => expect(box).toHaveTextContent("OpenAI"));
    expect(box).toHaveTextContent("Agentic swarm (upstream provider unrecorded) · 1 calls");
    expect(box.querySelectorAll(".provider-cost-row")).toHaveLength(2);
    expect(box.querySelectorAll(".provider-cost-row")[0]).toHaveTextContent("OpenAI");
  });

  it("renders the per-source breakdown with labels, share bars and token lines", async () => {
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(document.querySelector("[data-cost-source='prism'] .cost-name")).toHaveTextContent("Task plans"));
    const prism = document.querySelector("[data-cost-source='prism']") as HTMLElement;
    expect(prism.querySelector("[data-cost-tokens]")).toHaveTextContent("1 calls · 100 in (0 cached) · 20 out");
    expect(prism.querySelector(".cost-bar i")).toHaveStyle({ width: "100%" });
    expect(prism.querySelector(".cost-row .cost-meta")).toHaveTextContent("· 100%");
    expect(document.querySelector("[data-cost-source='swarm'] .cost-name")).toHaveTextContent("QA tester: website test runs");
  });

  it("switching the view to By model reloads and shows model names", async () => {
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(cost("all:today")).toHaveTextContent("₹"));
    await userEvent.click(screen.getByRole("button", { name: "By model" }));
    expect(screen.getByRole("button", { name: "By model" })).toHaveAttribute("aria-pressed", "true");
    expect(document.querySelector("[data-cost-source='prism'] .cost-name")).toHaveTextContent("test-model");
    expect(screen.getByRole("button", { name: "By feature" })).toHaveAttribute("aria-pressed", "false");
  });

  it("changing the range requests that period from the server", async () => {
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/usage/llm/sources")).toHaveLength(1));
    await userEvent.click(screen.getByRole("button", { name: "7 days" }));
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/usage/llm/sources")).toHaveLength(2));
    expect(net.callsTo("GET", "/api/v1/usage/llm/sources")[0].url).toContain("period=month");
    expect(net.callsTo("GET", "/api/v1/usage/llm/sources")[1].url).toContain("period=week");
    expect(screen.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows Azure billed lines when configured", async () => {
    net.set("GET /api/v1/usage/llm/azure-billed", { configured: true, sources: { prism: { currency: "USD", cost: 1.5 }, swarm: { error: "no access" } } });
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(document.querySelector("[data-cost-source='prism'] [data-cost-azure]")).toHaveTextContent("Azure billed: ₹124.50 (posts hours late)"));
    expect(document.querySelector("[data-cost-source='swarm'] [data-cost-azure]")).toHaveTextContent("Azure billed: no access");
  });

  it("says when spend could not be loaded", async () => {
    net.set("GET /api/v1/usage/llm/sources", () => ({ __reply: { status: 500, json: { detail: "x" } } }));
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(document.getElementById("cost-note")).toHaveTextContent("Spend could not be loaded."));
  });

  it("empty usage shows the empty states", async () => {
    const empty = { ...usage, by_feature: { prism: [], swarm: [] }, by_model: { prism: [], swarm: [] }, by_provider: [] };
    net.set("GET /api/v1/usage/llm/sources", empty);
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(document.getElementById("settings-provider-costs")).toHaveTextContent("No recorded usage in this period."));
    expect(document.querySelector("[data-cost-source='prism'] [data-cost-rows]")).toHaveClass("empty-state");
  });

  it("never sends the operator token to the exchange-rate host", async () => {
    localStorage.setItem("manager-agent-operator-token", "secret");
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(cost("all:today")).toHaveTextContent("₹"));
    const rateCall = net.calls.find((call) => call.url.startsWith("https://open.er-api.com"));
    expect(rateCall).toBeDefined();
    const fake = vi.mocked(fetch);
    const init = fake.mock.calls.find(([url]) => String(url).startsWith("https://open.er-api.com"))?.[1];
    expect(init?.headers).toBeUndefined();
    const apiInit = fake.mock.calls.find(([url]) => String(url).startsWith("/api/v1/usage/llm/sources"))?.[1];
    expect((apiInit?.headers as Record<string, string>)["X-Manager-Operator-Token"]).toBe("secret");
  });

  it("falls back to dollars while no exchange rate is known", async () => {
    net.set(RATE, () => ({ __reply: { status: 500, json: {} } }));
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(cost("all:today")).toHaveTextContent("$0.2000"));
  });

  it("reuses a cached rate when the lookup fails", async () => {
    localStorage.setItem("prism-usd-inr", JSON.stringify({ rate: 90, at: 1 }));
    costStore.reset({ inrRate: 90 });
    net.set(RATE, () => ({ __reply: { status: 500, json: {} } }));
    renderWithApp(<SpendingPage />);
    await waitFor(() => expect(cost("all:today")).toHaveTextContent("₹18.00"));
  });
});

describe("topbar hook", () => {
  function Topbar() {
    const { text, title } = useTodayAiCost();
    return (
      <span id="ai-cost-today" title={title}>
        {text}
      </span>
    );
  }

  it("shows the dash first, then today's combined cost with the timezone tooltip", async () => {
    renderWithApp(<Topbar />);
    expect(screen.getByText("Today's AI cost: —")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Today's AI cost: ₹16.600")).toBeInTheDocument());
    expect(document.getElementById("ai-cost-today")).toHaveAttribute("title", "Asia/Kolkata day. Prism plus agent swarm, estimated from provider tokens.");
  });

  it("flags unpriced usage and follows the currency", async () => {
    net.set("GET /api/v1/usage/llm/sources", {
      ...usage,
      periods: { ...periods, today: { prism: { ...item, unpriced_calls: 2 }, swarm: { ...item, estimated_cost_usd: "0.08" } } },
    });
    renderWithApp(
      <>
        <Topbar />
        <CurrencyToggle />
      </>,
    );
    await waitFor(() => expect(screen.getByText(/₹16\.600 \+ unpriced usage/)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "$ USD" }));
    expect(screen.getByText("Today's AI cost: $0.2000 + unpriced usage")).toBeInTheDocument();
  });

  it("loads once for the topbar and the page together and reloads on refresh", async () => {
    const app = fakeApp({ refreshKey: 0 });
    const tree = (key: number) => (
      <AppContext.Provider value={{ ...app, refreshKey: key }}>
        <Topbar />
        <SpendingPage />
      </AppContext.Provider>
    );
    const view = render(tree(0));
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/usage/llm/sources")).toHaveLength(1));
    await act(async () => {
      view.rerender(tree(1));
    });
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/usage/llm/sources")).toHaveLength(2));
  });
});

describe("formatMoney", () => {
  it("uses the old digit rules", () => {
    expect(formatMoney(2.5, "USD", null)).toBe("$2.50");
    expect(formatMoney(0.2, "USD", null)).toBe("$0.2000");
    expect(formatMoney("0.001", "USD", null)).toBe("$0.001000");
    expect(formatMoney(1, "INR", 83)).toBe("₹83.000");
    expect(formatMoney(2, "INR", 83)).toBe("₹166.00");
    expect(formatMoney(0.01, "INR", 83)).toBe("₹0.8300");
    expect(formatMoney(undefined, "INR", null)).toBe("$0.000000");
  });
});
