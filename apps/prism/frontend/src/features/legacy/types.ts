import type { Schema } from "@/types";

export type Employee = Schema<"EmployeeRead">;
export type Project = Schema<"ProjectRead">;
export type Task = Schema<"TaskRead">;
export type DailyUpdate = Schema<"DailyUpdateRead">;
export type Blocker = Schema<"BlockerRead">;
export type Commitment = Schema<"CommitmentRead">;
export type Escalation = Schema<"EscalationRead">;
export type RuleFinding = Schema<"RuleFinding">;
export type Journey = Schema<"JourneyRead">;
export type KnowledgeEntry = Schema<"ManagementContextRead">;
export type AttentionEntry = Schema<"AttentionItem">;
export type Brief = Schema<"DailyBrief">;
export type AgentFoundation = Schema<"AgentFoundationRead">;
export type MemoryFact = Schema<"MemoryFactRead">;

/** `/api/v1/memory/episodes` and the episodes in a memory search are untyped objects in the schema. */
export interface MemoryEpisode {
  id?: string;
  title: string;
  summary: string;
  started_at: string;
}

export type LegacyAction =
  | "daily-reminder"
  | "resolve-blocker"
  | "blocker-follow-up"
  | "mark-missed"
  | "revise-commitment"
  | "acknowledge-escalation"
  | "resolve-escalation";

export interface LegacyDataset {
  employees: Employee[];
  projects: Project[];
  tasks: Task[];
  updates: DailyUpdate[];
  blockers: Blocker[];
  commitments: Commitment[];
  escalations: Escalation[];
  findings: RuleFinding[];
  journeys: Journey[];
  knowledge: KnowledgeEntry[];
  memoryFacts: MemoryFact[];
  memoryEpisodes: MemoryEpisode[];
  attention: AttentionEntry[];
  brief: Brief | null;
  totals: { employees: number; updates: number; blockers: number; commitments: number; escalations: number } | null;
}

export const EMPTY_DATASET: LegacyDataset = {
  employees: [],
  projects: [],
  tasks: [],
  updates: [],
  blockers: [],
  commitments: [],
  escalations: [],
  findings: [],
  journeys: [],
  knowledge: [],
  memoryFacts: [],
  memoryEpisodes: [],
  attention: [],
  brief: null,
  totals: null,
};
