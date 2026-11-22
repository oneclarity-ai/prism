import { agentApi } from "@/lib/api";
import type { BrainEntry } from "./types";

/** The Brain: what every Prism knows. */
export const brainApi = {
  list: () => agentApi<BrainEntry[]>("/api/v2/brain"),
  decide: (entry: Pick<BrainEntry, "id">, action: "approve" | "reject") =>
    agentApi<BrainEntry>(`/api/v2/brain/${entry.id}/${action}`, { method: "POST" }),
  remove: (entry: Pick<BrainEntry, "id">) => agentApi<null>(`/api/v2/brain/${entry.id}`, { method: "DELETE" }),
};

export const brainProposedCount = (entries: readonly Pick<BrainEntry, "status">[]): number =>
  entries.filter((entry) => entry.status === "proposed").length;

export const sourceLabel = (entry: Pick<BrainEntry, "source">): string =>
  entry.source === "chat" ? "Learned from a chat" : entry.source === "prism" ? "Prism work note" : "Added by you";
