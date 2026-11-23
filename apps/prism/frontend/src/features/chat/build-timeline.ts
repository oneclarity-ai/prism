import { scopeKey, STAMP_GAP_MS } from "./format";
import type { ChatState, Message, Observation, PendingSubmission, Turn } from "./types";

export type TimelineItem =
  | { type: "history-banner"; key: string }
  | { type: "load-earlier"; key: string }
  | { type: "stamp"; key: string; value: string }
  | { type: "update"; key: string; item: Observation }
  | { type: "separator"; key: string; text: string }
  | { type: "user"; key: string; message: Message }
  | { type: "progress"; key: string; turn: Turn }
  | { type: "assistant"; key: string; message: Message; turn: Turn | undefined }
  | { type: "pending"; key: string; pending: PendingSubmission };

export type TimelineView = { kind: "loading" } | { kind: "welcome" } | { kind: "items"; items: TimelineItem[] };

// A separator appears when Prism starts working from a different source set.
function topicSeparator(state: ChatState, message: Message, previous: Message | null): string | null {
  const job = state.turns.get(message.job_id ?? "")?.job;
  const previousJob = previous ? state.turns.get(previous.job_id ?? "")?.job : undefined;
  const newTopic = Boolean(previous && job?.sources?.length && previousJob?.sources?.length && scopeKey(job) !== scopeKey(previousJob));
  if (!newTopic || !job) return null;
  return `New topic · ${sourceSummary(job.sources.map((source) => source.label || "Teams chat"))}`;
}

/** Chats that share a label (e.g. several chats with the same person) collapse to "Name (3 chats)". */
export function sourceSummary(labels: string[]): string {
  const counts = new Map<string, number>();
  labels.forEach((label) => counts.set(label, (counts.get(label) ?? 0) + 1));
  return [...counts].map(([label, count]) => (count > 1 ? `${label} (${count} chats)` : label)).join(", ");
}

/** The old `renderStream` decision tree as a pure function of the chat state. */
export function buildTimeline(state: ChatState): TimelineView {
  if (state.loading && !state.pendingSubmission) return { kind: "loading" };
  const { messages } = state;
  if ((!state.activeThread || (!messages.length && !state.jobs.length)) && !state.pendingSubmission && !state.updates.length) {
    return { kind: "welcome" };
  }
  const items: TimelineItem[] = [];
  const answered = new Set(messages.filter((message) => message.role !== "manager" && message.job_id).map((message) => message.job_id));
  if (state.anchor) items.push({ type: "history-banner", key: "history-banner" });
  if (state.hasEarlier) items.push({ type: "load-earlier", key: "load-earlier" });
  let previous: Message | null = null;
  // A centered time appears at the start, after a pause of 20 minutes, or when the day changes.
  let lastAt: Date | null = null;
  const stamp = (value: string | null | undefined) => {
    if (!value) return;
    const at = new Date(value);
    if (lastAt === null || Math.abs(at.getTime() - lastAt.getTime()) >= STAMP_GAP_MS || at.toDateString() !== lastAt.toDateString()) {
      items.push({ type: "stamp", key: `stamp-${items.length}`, value });
    }
    lastAt = at;
  };
  // Oldest first, so each update sits between the messages around the time it was found.
  const updates = [...state.updates].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const flushUpdates = (before?: string) => {
    while (updates.length && (!before || new Date(updates[0].created_at) <= new Date(before))) {
      const item = updates.shift() as Observation;
      stamp(item.created_at);
      items.push({ type: "update", key: `update-${item.id}`, item });
    }
  };
  messages.forEach((message) => {
    flushUpdates(message.created_at);
    stamp(message.created_at);
    if (message.role === "manager") {
      const separator = topicSeparator(state, message, previous);
      if (separator) items.push({ type: "separator", key: `separator-${message.id}`, text: separator });
      previous = message;
      items.push({ type: "user", key: message.id, message });
      const turn = state.turns.get(message.job_id ?? "");
      if (turn && !answered.has(message.job_id)) items.push({ type: "progress", key: `progress-${turn.job.id}`, turn });
    } else {
      items.push({ type: "assistant", key: message.id, message, turn: state.turns.get(message.job_id ?? "") });
    }
  });
  flushUpdates();
  if (state.pendingSubmission) {
    stamp(state.pendingSubmission.createdAt);
    items.push({ type: "pending", key: "pending-submission", pending: state.pendingSubmission });
  }
  return { kind: "items", items };
}
