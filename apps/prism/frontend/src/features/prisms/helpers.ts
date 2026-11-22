import type { Prism, OnboardingQuestion, OnboardingAnswer, TeamsPolicy, TeamsSource, TriggerPolicy } from "./types";

export const formatTime = (value: string | null | undefined): string =>
  value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";

export function stateLabel(prism: Pick<Prism, "state">): string {
  const value = String(prism.state || "unknown").toLowerCase();
  if (value === "draft") return "Draft";
  if (value === "onboarding") return "Onboarding";
  if (value === "awaiting_confirmation") return "Review needed";
  return value.replaceAll("_", " ");
}

export const clock = (value: string): string => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const dayDiff = (value: string): number =>
  Math.round((new Date().setHours(0, 0, 0, 0) - new Date(value).setHours(0, 0, 0, 0)) / 86400000);

export function dayLabel(value: string): string {
  const date = new Date(value);
  const days = dayDiff(value);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return date.toLocaleDateString([], {
    month: "long",
    day: "numeric",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}

/** Sidebar time: the clock today, "Yesterday", the weekday this week, then the date. */
export function sidebarTime(value: string): string {
  const date = new Date(value);
  const days = dayDiff(value);
  if (days <= 0) return clock(value);
  if (days === 1) return "Yesterday";
  if (days < 7) return date.toLocaleDateString([], { weekday: "short" });
  return date.toLocaleDateString([], {
    day: "numeric",
    month: "short",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}

export const initial = (name: unknown): string => (String(name || "").trim()[0] || "P").toUpperCase();
export const isArchived = (prism: { state?: unknown }): boolean => String(prism.state).toLowerCase() === "archived";
/** An active Prism is worked in the full Assistant Prism chat; the rest use the onboarding chat. */
export const isWorking = (prism: { state?: unknown } | null | undefined): boolean => String(prism?.state).toLowerCase() === "active";

export function teamsScopeCopy(policy: null | "loading" | "error" | TeamsPolicy): string {
  if (!policy || policy === "loading") return "Loading the durable Teams monitoring boundary…";
  if (policy === "error") return "Teams monitoring scope could not be loaded.";
  const count = policy.rules?.length || 0;
  if (policy.mode === "include_only") {
    return count
      ? `Only ${count} selected Teams ${count === 1 ? "chat is" : "chats are"} eligible to be read.`
      : "No Teams chats are eligible until you select one.";
  }
  if (policy.mode === "all_except") {
    return count
      ? `All accessible Teams chats except ${count} excluded ${count === 1 ? "chat" : "chats"} are eligible.`
      : "All accessible Teams chats are eligible; no exclusions are set.";
  }
  return "All accessible Teams chats are eligible by default.";
}

export function sourceDetail(source: TeamsSource): string {
  const kinds: Record<string, string> = { private: "1:1 chat", oneonone: "1:1 chat", group: "Group chat", meeting: "Meeting chat" };
  const kind = kinds[String(source.chat_type || "").toLowerCase()] || "Teams chat";
  return [kind, ...(source.participants || [])].filter(Boolean).join(" · ");
}

export function policyAllowsSource(policy: unknown, source: TeamsSource): boolean {
  if (!policy || typeof policy !== "object") return true;
  const typed = policy as TeamsPolicy;
  const ids = new Set((typed.rules || []).map((rule) => rule.external_id));
  if (typed.mode === "include_only") return ids.has(source.external_id);
  if (typed.mode === "all_except") return !ids.has(source.external_id);
  return true;
}

export const matchesSource = (source: TeamsSource, query: string): boolean => {
  const needle = query.trim().toLowerCase();
  return !needle || `${source.label} ${(source.participants || []).join(" ")}`.toLowerCase().includes(needle);
};

export const choiceLabel = (question: OnboardingQuestion, value: string): string =>
  question.choices.find((choice) => choice.value === value)?.label || value;

export const ACKNOWLEDGEMENTS = [
  "Got it, thanks.",
  "Great, that helps.",
  "Perfect, thank you.",
  "Good to know.",
  "Makes sense.",
  "Thanks, that’s useful.",
  "Sounds good.",
];

/** The model sometimes opens with its own greeting; the intro bubble already said hello. */
export const withoutGreeting = (text: unknown): string =>
  String(text || "")
    .replace(/^\s*(hi|hello|hey)( there)?[!,.]?\s*/i, "")
    .replace(/^./, (letter) => letter.toUpperCase());

export function answerText(question: OnboardingQuestion, answer: OnboardingAnswer): string {
  return answer.skipped ? "Skip for now" : answer.custom_text || answer.selected_values.map((value) => choiceLabel(question, value)).join(", ");
}

export function introText(prism: Pick<Prism, "name" | "description"> | undefined): string {
  const name = prism?.name || "Prism";
  const about = String(prism?.description || "")
    .replace(/\s+/g, " ")
    .trim()
    .split(/(?<=[.!?])\s/)[0]
    .replace(/[.!?]+$/, "")
    .slice(0, 140);
  return `Hi, I’m ${/prism$/i.test(name) ? name : `${name} Prism`}.${about ? ` You set me up to: ${about.charAt(0).toLowerCase()}${about.slice(1)}.` : ""} I’ll ask a few quick things so I can work the way you like. Pick an option or just tell me in your own words, and feel free to skip anything optional.`;
}

export function sentence(value: unknown): string {
  const text = String(value || "").trim();
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

export function joinList(items: unknown): string {
  const list = (Array.isArray(items) ? items : [items]).filter(Boolean).map((item) => String(item).trim().replace(/[.]$/, ""));
  if (list.length <= 1) return list[0] || "";
  return `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`;
}

export const lowerFirst = (text: string): string => text.charAt(0).toLowerCase() + text.slice(1);

export const ALWAYS_ASKS = [
  "Signing in to a site",
  "Sending, posting or publishing anything",
  "Submitting a form with your details",
  "Buying, paying, ordering or deleting",
];

export function listItems(value: unknown): string[] {
  return (Array.isArray(value) ? value : [value]).filter(Boolean).map(String);
}

const TRIGGER_MODES: Record<string, string> = {
  manual: "Manual only",
  scheduled: "Daily schedule",
  continuous: "Continuous checks",
  event_driven: "Coalesced event checks",
};

export function monitoringSchedule(trigger: TriggerPolicy): string {
  const mode = TRIGGER_MODES[trigger.mode] || trigger.mode;
  let schedule = `Monitoring mode: ${mode}.`;
  if (trigger.mode === "scheduled" && trigger.next_scheduled_for) schedule += ` Next run ${formatTime(trigger.next_scheduled_for)}.`;
  if (trigger.mode !== "manual" && !trigger.local_scheduler_enabled) schedule += " Local scheduler is off; run it manually until enabled.";
  return schedule;
}

/** Only fields the sidebar shows or the org chart needs: a poll that changes none of them re-renders nothing. */
export const prismListKey = (rows: Prism[]): string =>
  rows
    .map(
      (row) =>
        `${row.id}|${row.last_message_at}|${row.last_message_preview}|${row.state}|${row.name}|${row.job_role}|${row.department}|${row.reports_to_prism_id}|${row.is_chief_of_staff}`,
    )
    .join("\n");

export const splitNames = (value: unknown): string[] => [
  ...new Set(
    String(value || "")
      .split(",")
      .map((name) => name.trim().toLowerCase())
      .filter(Boolean),
  ),
];
