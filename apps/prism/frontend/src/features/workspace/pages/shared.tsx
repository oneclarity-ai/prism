import type { ReactNode } from "react";
import { SelectField, Tabs, type SelectOption } from "@/components/ui";
import type { WorkspaceNavigate } from "../workspace-nav";
import type { Agent, ManagedApproval, Analytics, OrgMember, Run, Target, Task, WorkspaceData } from "../types";

export type Filters = Record<string, string>;

/** What the controller hands every workspace page (the old `ctx`). */
export interface PageContext {
  data: WorkspaceData;
  prisms: OrgMember[];
  analytics: Analytics | null;
  filters: Filters;
  managedApprovals: ManagedApproval[];
  /** True while an approval decision is in flight: the page's buttons are disabled. */
  busy: boolean;
  navigate: WorkspaceNavigate;
  openRun: (runId: string) => void;
  openPrism: (prismId: string, runId?: string | null) => void;
  openAgent: (agent: Agent) => void;
  editTask: (item?: Task | null, defaults?: { agent_id?: string }) => void;
  editTarget: (item?: Target | null) => void;
  editSecret: () => void;
  remove: (section: "targets" | "secrets" | "positions", item: { id: string; title?: string; name?: string }) => void;
  decide: (item: ManagedApproval, decision: "approve" | "reject") => void;
  createPrism: () => void;
  /** Sets a filter; `remote` reloads the page data (analytics), otherwise the page just redraws. */
  filter: (key: string, value: string, remote?: boolean) => void;
}

export interface WorkspacePageProps {
  ctx: PageContext;
}

export const TASK_STATES: readonly SelectOption[] = [
  ["all", "All"],
  ["todo", "To do"],
  ["in_progress", "In progress"],
  ["blocked", "Blocked"],
  ["done", "Done"],
  ["failed", "Failed"],
];
export const RUN_STATES: readonly SelectOption[] = [
  ["all", "All"],
  ["queued", "Queued"],
  ["running", "Running"],
  ["waiting_children", "Prisms working"],
  ["waiting_approval", "Needs approval"],
  ["succeeded", "Succeeded"],
  ["failed", "Failed"],
  ["cancelled", "Cancelled"],
  ["timed_out", "Timed out"],
];
export const PERIODS: readonly SelectOption[] = [
  ["7", "Last 7 days"],
  ["30", "Last 30 days"],
  ["90", "Last 90 days"],
  ["365", "Last year"],
  ["0", "All available"],
];

export const current = (ctx: PageContext, key: string, fallback = ""): string => ctx.filters[key] ?? fallback;

export function Toolbar({ children }: { children?: ReactNode }) {
  return <div className="workspace-toolbar">{children}</div>;
}

export function DateFilter({ ctx, fallback = "30", analytics = false }: WorkspacePageProps & { fallback?: string; analytics?: boolean }) {
  return (
    <SelectField
      label="Date range"
      options={analytics ? PERIODS.filter(([key]) => key !== "0") : PERIODS}
      value={current(ctx, "days", fallback)}
      onChange={(value) => ctx.filter("days", value, analytics)}
    />
  );
}

export function inPeriod<T extends { created_at?: string | null }>(items: readonly T[], days: string | number): T[] {
  if (Number(days) === 0) return [...items];
  const since = Date.now() - Number(days) * 86400000;
  return items.filter((item) => new Date(item.created_at ?? NaN).getTime() >= since);
}

export const choices = (items: ReadonlyArray<{ id: string; name: string }>, title: string): SelectOption[] => [
  ["", title],
  ...items.map((item): SelectOption => [item.id, item.name]),
];

export const agentName = (ctx: PageContext, id: string | null | undefined): string =>
  ctx.data.agents?.find((item) => item.id === id)?.name || "Unassigned";
export const targetName = (ctx: PageContext, id: string | null | undefined): string =>
  ctx.data.targets?.find((item) => item.id === id)?.name || "—";

/** Status filter pills with the per-status counts. */
export function StatusTabs({
  ctx,
  items,
  states,
  filterKey = "status",
}: WorkspacePageProps & { items: ReadonlyArray<{ status: string }>; states: readonly SelectOption[]; filterKey?: string }) {
  return (
    <Tabs
      showIcons
      options={states.map(([value, title]) => [value, title, value === "all" ? items.length : items.filter((item) => item.status === value).length] as const)}
      value={current(ctx, filterKey, "all")}
      onChange={(value) => ctx.filter(filterKey, value)}
    />
  );
}

export function dayLabel(value: string | null | undefined): string {
  const d = new Date(value ?? NaN);
  if (Number.isNaN(d.valueOf())) return "Unknown date";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const day = new Date(d);
  day.setHours(0, 0, 0, 0);
  const gap = Math.round((today.getTime() - day.getTime()) / 86400000);
  return gap === 0 ? "Today" : gap === 1 ? "Yesterday" : d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "short", year: "numeric" });
}

export function groupByDay<T extends { created_at?: string | null }>(items: readonly T[]): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  [...items]
    .sort((a, b) => new Date(b.created_at ?? NaN).getTime() - new Date(a.created_at ?? NaN).getTime())
    .forEach((item) => {
      const key = dayLabel(item.created_at);
      groups.set(key, [...(groups.get(key) ?? []), item]);
    });
  return groups;
}

export function PeriodCaption({ items, noun }: { items: readonly unknown[]; noun: string }) {
  return items.length >= 200 ? <p className="panel-note">{`Showing the latest 200 ${noun}; filters apply to these records.`}</p> : null;
}

export const runCost = (run: Run): unknown => run.total_cost_usd ?? run.cost_usd;
