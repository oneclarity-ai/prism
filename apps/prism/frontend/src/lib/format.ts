export type DateInput = string | number | Date | null | undefined;

export const words = (value: unknown): string => String(value || "unknown").replaceAll("_", " ");

export const money = (value: unknown): string => `$${Number(value || 0).toFixed(2)}`;

export const count = (value: unknown): string =>
  new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));

export function time(value: DateInput): string {
  const d = new Date(value as string | number | Date);
  return value && !Number.isNaN(d.valueOf()) ? d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—";
}

export function age(value: DateInput): string {
  if (!value) return "—";
  const days = Math.floor((Date.now() - new Date(value).getTime()) / 86400000);
  if (!Number.isFinite(days)) return "—";
  return days < 1 ? "Today" : days === 1 ? "1 day ago" : `${days} days ago`;
}

export interface DurationSource {
  avg_duration_s?: number | string | null;
  started_at?: DateInput;
  ended_at?: DateInput;
}

export function duration(item: DurationSource): string {
  let seconds: unknown = item.avg_duration_s;
  if (seconds === undefined) {
    seconds = item.started_at
      ? (new Date(item.ended_at || Date.now()).getTime() - new Date(item.started_at).getTime()) / 1000
      : 0;
  }
  const whole = Math.max(0, Math.round(Number(seconds) || 0));
  return whole >= 60 ? `${Math.floor(whole / 60)}m ${whole % 60}s` : `${whole}s`;
}

// One plain sentence or two from a Markdown job description, for cards and lists.
export function plainSummary(text: unknown, limit = 170): string {
  const plain = String(text || "")
    .replace(/^#{1,6}\s*(Mission|Overview|Summary)\s*$/gim, "")
    .replace(/^#{1,6}\s+.*$/gm, " ")
    .replace(/^\s*[-*•]\s+/gm, "")
    .replace(/[*_`]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return plain.length > limit ? `${plain.slice(0, limit).replace(/\s+\S*$/, "")}…` : plain;
}

export type StatusTone = "gray" | "blue" | "orange" | "green" | "purple" | "red";
export type StatusMeta = readonly [title: string, glyph: string, tone: StatusTone];

export const STATUS_META: Readonly<Record<string, StatusMeta>> = {
  todo: ["To do", "circle-dashed", "gray"],
  in_progress: ["In progress", "circle-play", "blue"],
  blocked: ["Blocked", "ban", "orange"],
  done: ["Done", "circle-check", "green"],
  queued: ["Queued", "clock", "gray"],
  running: ["Running", "loader-circle", "blue"],
  waiting_children: ["Sub-agents working", "network", "purple"],
  waiting_approval: ["Needs approval", "shield-check", "orange"],
  succeeded: ["Succeeded", "circle-check", "green"],
  failed: ["Failed", "circle-x", "red"],
  cancelled: ["Cancelled", "ban", "gray"],
  timed_out: ["Timed out", "timer", "red"],
  pending: ["Pending", "clock", "orange"],
  approved: ["Approved", "circle-check", "green"],
  rejected: ["Rejected", "circle-x", "red"],
  active: ["Active", "circle-check", "green"],
};

/** Own-property lookup (the old object lookup also matched prototype keys such as "constructor"). */
export function statusMeta(value: unknown): StatusMeta {
  const known = typeof value === "string" && Object.hasOwn(STATUS_META, value) ? STATUS_META[value] : undefined;
  return known ?? [words(value), "circle-dashed", "gray"];
}
