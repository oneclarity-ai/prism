import type { QaRun } from "./types";

export const STATE_TEXT: Record<string, string> = {
  planned: "Waiting for you to start",
  starting: "Getting ready",
  running: "Testing",
  waiting_approval: "Waiting for you",
  succeeded: "Finished",
  failed: "Stopped with a problem",
  cancelled: "Stopped",
  timed_out: "Ran out of time",
  error: "Couldn't run",
};
export const STATUS_TEXT: Record<string, string> = { pass: "Passed", fail: "Failed", blocked: "Couldn't check", skipped: "Skipped", pending: "Not run" };
export const STATUS_TONE: Record<string, string> = { pass: "green", fail: "red", blocked: "orange", skipped: "gray", pending: "gray" };
export const SEVERITY_TONE: Record<string, string> = { critical: "red", high: "red", medium: "orange", low: "gray" };

export const isActive = (run: QaRun | null | undefined): boolean => Boolean(run?.active);
export const isWork = (run: QaRun | null | undefined): boolean => run?.kind === "work";

export const stateText = (run: QaRun): string =>
  run.startup_warning ? "Waiting for workspace" : isWork(run) && run.state === "running" ? "Working" : STATE_TEXT[run.state] || run.state;

export function elapsed(run: QaRun | null | undefined): string {
  if (!run?.started_at) return "";
  const end = run.ended_at ? new Date(run.ended_at) : new Date();
  const seconds = Math.max(0, Math.round((end.getTime() - new Date(run.started_at).getTime()) / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${String(seconds % 60).padStart(2, "0")}s` : `${seconds}s`;
}

export const money = (value: unknown): string => `$${Number(value || 0).toFixed(2)}`;

export const stripScheme = (value: string): string => value.replace(/^https?:\/\//, "");

/** What the chat cards depend on. The live panel updates on every change; the chat refresh only when this changes. */
export const cardKey = (run: QaRun): string =>
  [run.state, run.startup_warning || "", (run.approvals ?? []).map((a) => a.status).join(","), run.report ? "r" : "", run.cases?.total || 0].join("|");

/** Only plain http(s) URLs become links in report tables. */
export const isLink = (value: unknown): boolean => /^https?:\/\/[^\s]+$/i.test(String(value));

export const minutesText = (seconds: number | null | undefined): string | null =>
  seconds != null ? `${Math.max(1, Math.round(seconds / 60))} min` : null;
