import type { ActionPlan, Execution, Job, Proposal, Review, SourceMetadata, Thread, Turn } from "./types";

export const ACTIVE_JOB_STATES = ["queued", "researching", "planning"];

export const PROGRESS_LABELS: Record<string, string> = {
  queued: "Resolving the Teams source…",
  researching: "Reading the Teams conversation…",
  planning: "Working out what needs your attention…",
  waiting_for_approval: "Waiting for your approval",
  executing: "Sending your approved message…",
  completed: "Done",
  failed: "Prism could not finish this review",
  cancelled: "Review cancelled",
};

export const SUGGESTIONS = [
  "What needs my attention?",
  "Summarize decisions and open questions",
  "Draft a reply to the latest message",
  "What did I commit to?",
];

export const TONES = ["gray", "blue", "green", "orange", "purple", "yellow", "red"];

export const PAGE_SIZE = 60;
export const STAMP_GAP_MS = 20 * 60 * 1000;

export const SIGNAL_LABELS: Record<string, string> = {
  production_incident: "Possible production incident",
  missed_deadline: "Deadline at risk",
  blocker: "Blocked work",
  unanswered_message: "Unanswered message",
  customer_discussion: "Customer discussion",
};
export const URGENCY_TONES: Record<string, string> = { critical: "red", high: "orange", medium: "yellow", low: "blue" };
export const FEEDBACK_LABELS: Record<string, string> = {
  helpful: "Helpful",
  not_helpful: "Not helpful",
  wrong_urgency: "Wrong urgency",
  wrong_evidence: "Wrong evidence",
  duplicate: "Duplicate",
  no_longer_relevant: "No longer relevant",
};
export const FEEDBACK_REASONS = ["wrong_urgency", "wrong_evidence", "duplicate", "no_longer_relevant"];
export const INCIDENT_LABELS: Record<string, string> = {
  opened: "Opened",
  linked: "Linked",
  updated: "Updated",
  resolved: "Resolved",
  reopened: "Reopened",
  split: "Split",
};

export const SCOPE_LABELS: Record<string, string> = {
  auto: "Auto-selected",
  chat: "You limited this to one chat",
  person: "You limited this to one person",
  "explicit-set": "Sources you chose",
};
export const CHAT_KINDS: Record<string, string> = {
  oneonone: "1:1 chat",
  group: "Group chat",
  private: "1:1 chat",
  meeting: "Meeting chat",
};
export const SOURCE_KINDS: Record<string, string> = { oneonone: "1:1", group: "Group", meeting: "Meeting" };

export interface Recovery {
  title: string;
  detail: string;
  /** Button label; the click is "reconnect Microsoft" (the only action any recovery offers). */
  action: string | null;
}

// Stable domain codes map to one clear next step; none of these claim a message was sent.
export const RECOVERY: Record<string, Recovery> = {
  microsoft_reconnect_required: {
    title: "Reconnect Microsoft to continue",
    detail: "Prism could not use your Microsoft session. Nothing was sent.",
    action: "Reconnect Microsoft",
  },
  microsoft_permission_required: {
    title: "Microsoft permission is missing",
    detail:
      "Your account cannot read or write this Teams chat with Prism's current consent. Nothing was sent. Ask an admin to grant Teams chat access, then reconnect.",
    action: "Reconnect Microsoft",
  },
  microsoft_throttled: {
    title: "Microsoft is asking Prism to slow down",
    detail: "Nothing was sent. Wait a minute, then retry.",
    action: null,
  },
  no_source_evidence: {
    title: "Nothing to read in this chat yet",
    detail:
      "Prism found no messages in the reading window, so it has nothing to ground a review on. Nothing was sent. Ask Prism to draft a message from your instruction, or ask again once the chat has messages.",
    action: null,
  },
  reconciliation_required: {
    title: "Delivery needs your confirmation",
    detail:
      "Prism could not prove whether Microsoft accepted this message, so it will not retry on its own. Check Teams before drafting again.",
    action: null,
  },
};

export const reconnectMicrosoft = (): void => window.location.assign("/api/v1/microsoft/auth/start");

export function formatTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
}

export function humanize(value: unknown): string {
  return String(value || "").replaceAll("_", " ");
}

export function toneFor(text: unknown): string {
  let hash = 0;
  for (const character of String(text || "")) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return TONES[hash % TONES.length];
}

export function initialOf(text: unknown): string {
  return String(text || "?").trim().charAt(0).toUpperCase() || "?";
}

export const capitalize = (value: string): string => `${value[0].toUpperCase()}${value.slice(1)}`;

const clockText = (date: Date) => date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

// Centered time between messages: the clock for today, then day and clock the further back it is.
export function stampLabel(value: string): string {
  const date = new Date(value);
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(date).setHours(0, 0, 0, 0)) / 86400000);
  if (days <= 0) return clockText(date);
  if (days === 1) return `Yesterday, ${clockText(date)}`;
  if (days < 7) return `${date.toLocaleDateString([], { weekday: "long" })}, ${clockText(date)}`;
  const day = date.toLocaleDateString([], {
    day: "numeric",
    month: "short",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
  return `${day}, ${clockText(date)}`;
}

export function snippetFor(content: string, query: string): string {
  const text = String(content).replace(/\s+/g, " ");
  const at = text.toLowerCase().indexOf(query.toLowerCase());
  const start = Math.max(0, at - 50);
  return `${start ? "…" : ""}${text.slice(start, start + 160)}${text.length > start + 160 ? "…" : ""}`;
}

// A long job description becomes a one-line blurb: the first sentence, cut at a word boundary.
export function briefDescription(text: unknown, limit = 140): string {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (!clean) return "Ask me about your team’s work and I’ll look into it.";
  const first = clean.match(/^.*?[.!?](?=\s|$)/)?.[0] || clean;
  if (first.length <= limit) return first;
  return `${first.slice(0, limit).replace(/\s+\S*$/, "")}…`;
}

export function confidenceText(confidence: number): string {
  return confidence >= 0.75 ? "High confidence" : confidence >= 0.5 ? "Medium confidence" : "Low confidence";
}

export function readLabel(turn: Turn): string {
  const read = (turn.job.sources || [])
    .filter((source) => source.selection_reason !== "destination")
    .map((source) => source.label || "Teams chat");
  const count = turn.evidence.size;
  const who = read.length > 2 ? `${read.slice(0, 2).join(", ")} +${read.length - 2}` : read.join(", ");
  if (count && who) return `Read ${count} message${count === 1 ? "" : "s"} · ${who}`;
  if (who) return who;
  return "Details";
}

export const scopeKey = (job: Job | null | undefined): string =>
  `${job?.scope_mode || ""}:${(job?.sources || []).map((source) => source.external_id).sort().join(",")}`;

export const metadataOf = (value: unknown): SourceMetadata =>
  value && typeof value === "object" ? (value as SourceMetadata) : {};

export function threadParticipants(thread: Thread | null): string[] {
  const participants = metadataOf(thread?.source_metadata).participants;
  return Array.isArray(participants) ? participants : [];
}

export interface DraftState {
  key: string;
  label: string;
  tone: string;
}

export function draftState(proposal: Proposal, execution: Execution | null | undefined): DraftState {
  if (execution?.state === "succeeded" || proposal.state === "executed") return { key: "sent", label: "Sent", tone: "green" };
  if (execution?.state === "uncertain") return { key: "uncertain", label: "Needs confirmation", tone: "orange" };
  if (execution?.state === "failed" || proposal.state === "failed") return { key: "failed", label: "Failed", tone: "red" };
  if (execution?.state === "running" || proposal.state === "executing") return { key: "sending", label: "Sending", tone: "blue" };
  if (proposal.state === "approved") return { key: "approved", label: "Approved", tone: "blue" };
  if (proposal.state === "rejected") return { key: "rejected", label: "Rejected", tone: "gray" };
  if (proposal.state === "expired") return { key: "expired", label: "Expired", tone: "gray" };
  return { key: "pending", label: "Awaiting approval", tone: "orange" };
}

export function draftStatusText(proposal: Proposal, execution: Execution | null | undefined): string {
  if (execution?.state === "running") return "Sending through your connected Microsoft account…";
  if (execution?.state === "succeeded") {
    return `Delivered from your Microsoft Teams account${execution.completed_at ? ` · ${formatTime(execution.completed_at)}` : ""}.`;
  }
  if (execution?.state === "failed") return execution.safe_error_detail || "Delivery failed.";
  if (execution?.state === "uncertain") {
    return execution.safe_error_detail || "Delivery confirmation required; Prism will not retry automatically.";
  }
  const byState: Record<string, string> = {
    pending: "Nothing is sent until you approve.",
    approved: "Approved. Ready to send.",
    rejected: "Rejected. Nothing was sent.",
    expired: "This draft expired. Nothing was sent.",
    draft: "Draft.",
    executing: "Sending…",
    executed: "Delivered from your Microsoft Teams account.",
    failed: "Delivery failed.",
  };
  return byState[proposal.state] || `Status: ${humanize(proposal.state)}.`;
}

/** Every review, edit, approval, and delivery is stored; the audit trail makes that visible. */
export function auditEvents(turn: Turn & { review: Review }): [string, string | null | undefined][] {
  const { job, review } = turn;
  const events: [string, string | null | undefined][] = [["Review requested", job.created_at]];
  if (turn.evidence.size) {
    events.push([`Read ${turn.evidence.size} Teams message${turn.evidence.size === 1 ? "" : "s"}`, job.started_at || job.created_at]);
  }
  events.push([`Review prepared · ${review.provider} ${review.model}`, review.created_at]);
  const plan: ActionPlan | null | undefined = review.action_plan;
  const records = plan?.actions || (review.proposal ? [{ proposal: review.proposal, execution: review.execution }] : []);
  records.forEach(({ proposal, execution }) => {
    const destination = proposal.destination.label || "Teams";
    events.push([proposal.revision > 1 ? `Edited by you · revision ${proposal.revision}` : "Draft created", proposal.created_at]);
    if (proposal.approval) {
      const approval = proposal.approval;
      const decision = `${humanize(approval.decision).replace(/^./, (letter) => letter.toUpperCase())} by ${approval.manager_identity}`;
      events.push([approval.reason ? `${decision} · ${approval.reason}` : decision, approval.decided_at]);
    }
    if (execution) {
      const labels: Record<string, string> = {
        succeeded: "Delivered to Teams",
        failed: "Delivery failed",
        uncertain: "Delivery unconfirmed",
        running: "Sending started",
      };
      const label = labels[execution.state] || "Delivery queued";
      events.push([`${label} · ${destination}`, execution.completed_at || execution.started_at || execution.created_at]);
    }
  });
  return events;
}
