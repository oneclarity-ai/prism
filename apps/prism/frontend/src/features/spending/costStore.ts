import { useEffect, useRef, useSyncExternalStore } from "react";
import { agentApi } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { readStorage, writeStorage } from "@/lib/storage";

export type Currency = "INR" | "USD";
export type CostSourceName = "prism" | "swarm";
export type CostPeriod = "today" | "week" | "month" | "total";
export type CostRange = "today" | "week" | "month";
export type CostView = "feature" | "model";

export const COST_SOURCES: readonly CostSourceName[] = ["prism", "swarm"];

export interface CostRow {
  group: string;
  calls?: number;
  estimated_cost_usd: string | number;
  unpriced_calls?: number;
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
}

export interface CostPeriodTotals {
  estimated_cost_usd: string | number;
  unpriced_calls: number;
}

/** `/api/v1/usage/llm/sources` (an untyped dict in the OpenAPI schema). */
export interface CostData {
  timezone: string;
  range: { from: string; to: string };
  periods: Record<CostPeriod, Record<CostSourceName, CostPeriodTotals>>;
  by_feature: Record<CostSourceName, CostRow[]>;
  by_model: Record<CostSourceName, CostRow[]>;
  by_provider?: CostRow[];
}

export interface AzureBilled {
  configured?: boolean;
  sources?: Record<string, { currency?: string; cost?: number | string; error?: string } | undefined>;
}

export interface CostSnapshot {
  currency: Currency;
  inrRate: number | null;
  range: CostRange;
  view: CostView;
  data: CostData | null;
  billed: AzureBilled | null;
  /** The last (non-background) load failed. */
  failed: boolean;
  /** Time of the last render-worthy change; shown as "Updated ...". */
  stamp: Date | null;
}

const CURRENCY_KEY = "prism-currency";
const RATE_KEY = "prism-usd-inr";
const RATE_URL = "https://open.er-api.com/v6/latest/USD";

function readRate(): number | null {
  try {
    return Number((JSON.parse(readStorage(RATE_KEY) || "{}") as { rate?: unknown }).rate) || null;
  } catch {
    return null;
  }
}

let snapshot: CostSnapshot = {
  currency: readStorage(CURRENCY_KEY) === "USD" ? "USD" : "INR",
  inrRate: readRate(),
  range: "month",
  view: "feature",
  data: null,
  billed: null,
  failed: false,
  stamp: null,
};
const listeners = new Set<() => void>();
let costRequest = 0;

function update(patch: Partial<CostSnapshot>, stamp = false): void {
  snapshot = { ...snapshot, ...patch, ...(stamp ? { stamp: new Date() } : {}) };
  listeners.forEach((listener) => listener());
}

export function formatMoney(value: unknown, currency: Currency, inrRate: number | null): string {
  const usd = Number(value) || 0;
  if (currency === "INR" && inrRate) {
    const amount = usd * inrRate;
    const digits = amount >= 100 ? 2 : amount >= 1 ? 3 : 4;
    return `₹${amount.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
  }
  return `$${usd.toFixed(usd >= 1 ? 2 : usd >= 0.01 ? 4 : 6)}`;
}

async function loadRate(): Promise<void> {
  try {
    // A plain fetch on purpose: this is a third-party host, so no operator token header may go along.
    const response = await fetch(RATE_URL, { signal: AbortSignal.timeout(4000) });
    const rate = Number(((await response.json()) as { rates?: { INR?: unknown } }).rates?.INR);
    if (rate > 0) {
      update({ inrRate: rate });
      writeStorage(RATE_KEY, JSON.stringify({ rate, at: Date.now() }));
    }
  } catch {
    /* keep the last known rate */
  }
}

async function loadCost(): Promise<void> {
  const request = ++costRequest;
  const selectedRange = snapshot.range;
  await loadRate();
  if (request !== costRequest) return;
  const data = await agentApi<CostData>(`/api/v1/usage/llm/sources?period=${selectedRange}`);
  if (request !== costRequest) return;
  update({ data, billed: null, failed: false }, true);
  agentApi<AzureBilled>(`/api/v1/usage/llm/azure-billed?from=${data.range.from}&to=${data.range.to}`)
    .then((billed) => update({ billed }, true))
    .catch(() => {});
}

let scheduled = false;

export const costStore = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  getSnapshot: (): CostSnapshot => snapshot,
  /** Load now; a failure shows "Spend could not be loaded." */
  load(): Promise<void> {
    return loadCost().catch(() => update({ failed: true }));
  },
  /** Several triggers in the same tick (tab change + mode change + refresh) share one load. */
  scheduleLoad(): void {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => {
      scheduled = false;
      void costStore.load();
    });
  },
  /** Hourly background refresh: errors stay silent. */
  loadQuietly(): Promise<void> {
    return loadCost().catch(() => {});
  },
  setRange(range: CostRange): void {
    update({ range });
    void costStore.loadQuietly();
  },
  setView(view: CostView): void {
    update({ view });
    void costStore.loadQuietly();
  },
  setCurrency(currency: Currency): void {
    writeStorage(CURRENCY_KEY, currency);
    update({ currency }, true);
  },
  /** Test helper: forget loaded data and cancel in-flight loads. */
  reset(initial: Partial<CostSnapshot> = {}): void {
    costRequest += 1;
    snapshot = {
      currency: "INR",
      inrRate: null,
      range: "month",
      view: "feature",
      data: null,
      billed: null,
      failed: false,
      stamp: null,
      ...initial,
    };
    listeners.forEach((listener) => listener());
  },
};

export const useCostSnapshot = (): CostSnapshot => useSyncExternalStore(costStore.subscribe, costStore.getSnapshot);

let syncUsers = 0;
let syncTimer: ReturnType<typeof setInterval> | undefined;

/**
 * Keeps the cost data fresh like today-prisms.js: load at start, when the Spending page opens, when the
 * Prism workspace turns on, on "Reload all data", and hourly. Safe to call from several components.
 */
export function useCostSync(): void {
  const app = useApp();
  const firstRefresh = useRef(true);

  useEffect(() => {
    syncUsers += 1;
    costStore.scheduleLoad();
    if (syncUsers === 1) syncTimer = setInterval(() => void costStore.loadQuietly(), 60 * 60 * 1000);
    return () => {
      syncUsers -= 1;
      if (syncUsers === 0) clearInterval(syncTimer);
    };
  }, []);
  useEffect(() => {
    if (app.activeTab === "spending") costStore.scheduleLoad();
  }, [app.activeTab]);
  useEffect(() => {
    if (app.modes.v22 === true) costStore.scheduleLoad();
  }, [app.modes.v22]);
  useEffect(() => {
    if (firstRefresh.current) firstRefresh.current = false;
    else costStore.scheduleLoad();
  }, [app.refreshKey]);
}

export function sumRows(rows: readonly CostRow[], field: keyof CostRow): number {
  return rows.reduce((total, row) => total + Number(row[field] || 0), 0);
}

/** Total estimated USD across both sources for one period. */
export function periodTotal(data: CostData, period: CostPeriod): number {
  return COST_SOURCES.reduce((total, source) => total + Number(data.periods[period][source].estimated_cost_usd), 0);
}

export interface TodayAiCost {
  text: string;
  /** Tooltip; `undefined` until the first load. */
  title: string | undefined;
}

/**
 * Text for the topbar `#ai-cost-today` element (old today-prisms.js `renderCost`). Also keeps the cost data
 * loading, so the shell only has to render `<span id="ai-cost-today" aria-live="polite" title={title}>{text}</span>`.
 */
export function useTodayAiCost(): TodayAiCost {
  useCostSync();
  const { data, currency, inrRate } = useCostSnapshot();
  if (!data) return { text: "Today's AI cost: —", title: undefined };
  const unpriced = COST_SOURCES.reduce((total, source) => total + data.periods.today[source].unpriced_calls, 0);
  return {
    text: `Today's AI cost: ${formatMoney(periodTotal(data, "today"), currency, inrRate)}${unpriced ? " + unpriced usage" : ""}`,
    title: `${data.timezone} day. Prism plus agent swarm, estimated from provider tokens.`,
  };
}
