import { useSyncExternalStore } from "react";
import { agentApi, errorMessage } from "@/lib/api";
import { setNavCount } from "@/lib/nav-counts";
import type { PrismLike } from "@/lib/events";

/** The Work and Approvals tabs share the Prism list and the approvals badge, so their data lives here. */

export interface WorkRun {
  id: string;
  title?: string | null;
  state?: string | null;
  kind?: string | null;
  active?: boolean;
  prism_id: string;
  prism_name?: string | null;
  created_at?: string | null;
  cost_usd?: number | string | null;
  activity?: string | null;
  error?: string | null;
  report?: { summary?: string | null } | null;
}

export interface WorkApproval {
  id: string;
  kind: string;
  prism_id: string;
  prism_name?: string | null;
  run_id: string;
  run_title?: string | null;
  can_decide_here?: boolean;
  payload: Partial<Record<"title" | "summary" | "question" | "site" | "severity" | "steps" | "expected" | "actual" | "details" | "reason", string>>;
}

export type ListView<T> = { kind: "initial" } | { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; items: T[] };

export interface StatusLine {
  text: string;
  error: boolean;
}

export interface UnifiedWorkState {
  prisms: Map<string, PrismLike>;
  prismListLoaded: boolean;
  prismFilter: string;
  runs: ListView<WorkRun>;
  runtime: { text: string; tone: "" | "error" | "success" };
  workStatus: StatusLine;
  approvals: ListView<WorkApproval>;
  approvalStatus: StatusLine;
  loaded: boolean;
}

const initial = (): UnifiedWorkState => ({
  prisms: new Map(),
  prismListLoaded: false,
  prismFilter: "",
  runs: { kind: "initial" },
  runtime: { text: "Checking the computer service…", tone: "" },
  workStatus: { text: "", error: false },
  approvals: { kind: "initial" },
  approvalStatus: { text: "", error: false },
  loaded: false,
});

let state = initial();
const listeners = new Set<() => void>();

function patch(next: Partial<UnifiedWorkState>): void {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const getUnifiedWork = (): UnifiedWorkState => state;
export const useUnifiedWork = (): UnifiedWorkState => useSyncExternalStore(subscribe, getUnifiedWork);
export function resetUnifiedWork(): void {
  state = initial();
  setNavCount("work-approvals", 0);
  listeners.forEach((listener) => listener());
}

async function ensurePrisms(): Promise<void> {
  if (state.prismListLoaded) return;
  const prisms = await agentApi<PrismLike[]>("/api/v2/prisms?include_archived=false");
  patch({ prisms: new Map(prisms.map((prism) => [prism.id, prism])), prismListLoaded: true });
}

async function loadRuntimeStatus(): Promise<void> {
  try {
    const result = await agentApi<{ message: string; available: boolean }>("/api/v2/work/status");
    patch({ runtime: { text: result.message, tone: result.available ? "success" : "error" } });
  } catch (error) {
    patch({ runtime: { text: errorMessage(error), tone: "error" } });
  }
}

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;

export async function loadRuns(): Promise<void> {
  patch({ runs: { kind: "loading" } });
  try {
    await ensurePrisms();
    const query = new URLSearchParams({ limit: "100" });
    if (state.prismFilter) query.set("prism_id", state.prismFilter);
    const [runs] = await Promise.all([agentApi<WorkRun[]>(`/api/v2/work/runs?${query}`), loadRuntimeStatus()]);
    patch({
      runs: { kind: "ready", items: runs },
      workStatus: { text: `${plural(runs.length, "recent task")}. Costs are reported by the computer service.`, error: false },
    });
  } catch (error) {
    patch({ runs: { kind: "error", message: errorMessage(error) }, workStatus: { text: "Work could not be loaded.", error: true } });
  }
}

export async function loadApprovals(): Promise<void> {
  patch({ approvals: { kind: "loading" } });
  try {
    await ensurePrisms();
    const approvals = await agentApi<WorkApproval[]>("/api/v2/work/approvals?limit=100");
    setNavCount("work-approvals", approvals.length);
    patch({
      approvals: { kind: "ready", items: approvals },
      approvalStatus: { text: `${plural(approvals.length, "decision")} waiting.`, error: false },
    });
  } catch (error) {
    patch({ approvals: { kind: "error", message: errorMessage(error) }, approvalStatus: { text: "Approvals could not be loaded.", error: true } });
  }
}

export function setWorkStatus(text: string, error = false): void {
  patch({ workStatus: { text, error } });
}
export function setApprovalStatus(text: string, error = false): void {
  patch({ approvalStatus: { text, error } });
}

export function setPrismFilter(prismFilter: string): void {
  patch({ prismFilter });
  void loadRuns();
}

/** The Prism list changed (old `prism:list`): keep the filter valid and preload approvals once. */
export function syncPrismList(list: readonly PrismLike[]): void {
  const prisms = new Map(list.map((prism) => [prism.id, prism]));
  patch({ prisms, prismListLoaded: true, prismFilter: prisms.has(state.prismFilter) ? state.prismFilter : "" });
  if (!state.loaded) {
    patch({ loaded: true });
    void loadApprovals();
  }
}
