import type { OrgNode } from "@/lib/prism-organization";
import type { Schema } from "@/types";

/** A Prism as the organization endpoint and the shared Prism list return it. */
export type OrgMember = Schema<"PrismRead">;
export type PrismTool = Schema<"PrismToolRead">;
export type BrainEntry = Schema<"BrainRead">;

export type Loose = string | number | null | undefined;

/** Engine agent from `/api/v2/operations/overview` (the computer service's record). */
export interface Agent {
  id: string;
  key?: string | null;
  name: string;
  description?: string | null;
  role?: string | null;
  status?: string | null;
  model?: string | null;
  runtime?: string | null;
  run_budget_usd?: Loose;
  monthly_budget_usd?: Loose;
  created_at?: string | null;
  tool_count?: number | null;
  ask_first_count?: number | null;
}

export interface Task {
  id: string;
  title: string;
  goal?: string | null;
  agent_id: string;
  target_app_id?: string | null;
  status: string;
  created_at?: string | null;
}

export interface Run {
  id: string;
  task_title?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  kind?: string | null;
  status: string;
  created_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  input_tokens?: Loose;
  output_tokens?: Loose;
  total_tokens?: Loose;
  total_cost_usd?: Loose;
  cost_usd?: Loose;
}

export type PayloadKey =
  | "title"
  | "summary"
  | "question"
  | "site"
  | "reason"
  | "severity"
  | "steps"
  | "expected"
  | "actual"
  | "details";
export type ApprovalPayload = Partial<Record<PayloadKey, string>> & {
  arguments?: Partial<Record<PayloadKey, string>>;
};

/** Pending/decided computer action from the engine overview. */
export interface EngineApproval {
  id: string;
  status: string;
  action?: string | null;
  run_id?: string | null;
  task_title?: string | null;
  created_at?: string | null;
  payload?: ApprovalPayload | null;
}

/** Approval from `/api/v2/work/approvals`, the Prism-side view of an engine approval. */
export interface ManagedApproval {
  id: string;
  engine_approval_id?: string | null;
  prism_id: string;
  prism_name?: string | null;
  run_id: string;
  run_title?: string | null;
  kind: string;
  status: string;
  can_decide_here?: boolean;
  created_at?: string | null;
  payload: Partial<Record<PayloadKey, string>>;
}

export interface Bug {
  id?: string;
  title: string;
  severity: string;
  status: string;
  run_id: string;
  target_name?: string | null;
  task_title?: string | null;
  model?: string | null;
  created_at?: string | null;
  steps?: string | null;
  expected?: string | null;
  actual?: string | null;
  external_url?: string | null;
}

export interface Target {
  id: string;
  name: string;
  base_url: string;
  environment: string;
  notes?: string | null;
  has_test_login?: boolean;
  created_at?: string | null;
}

export interface Secret {
  id: string;
  name: string;
  scope?: string | null;
  created_at?: string | null;
}

export interface UsageCount {
  status?: string;
  severity?: string;
  count?: number;
}
export interface UsageRow {
  agent_name?: string | null;
  model?: string | null;
  runs?: number;
  input_tokens?: Loose;
  output_tokens?: Loose;
  cost_usd?: Loose;
  success_rate?: Loose;
}
export interface UsageDay {
  date: string;
  runs?: number;
  cost_usd?: Loose;
  input_tokens?: Loose;
  output_tokens?: Loose;
}
export interface Analytics {
  totals?: {
    cost_usd?: Loose;
    avg_cost_per_run?: Loose;
    runs?: number;
    succeeded?: number;
    failed?: number;
    success_rate?: Loose;
    input_tokens?: Loose;
    output_tokens?: Loose;
    avg_duration_s?: number | string | null;
    bugs?: number;
    tests_pass?: number;
  };
  by_day?: UsageDay[];
  by_status?: UsageCount[];
  tests_by_status?: UsageCount[];
  bugs_by_severity?: UsageCount[];
  by_agent?: UsageRow[];
  by_model?: UsageRow[];
}

/** `/api/v2/operations/overview`, plus what the controller adds (organization, secrets). */
export interface EngineOverview {
  agents: Agent[];
  positions: unknown[];
  tasks: Task[];
  runs: Run[];
  approvals: EngineApproval[];
  bugs: Bug[];
  targets?: Target[];
  status?: { workers_online?: number; azure_configured?: boolean };
  analytics?: Analytics;
}


export interface WorkspaceData extends Omit<EngineOverview, "targets"> {
  targets: Target[];
  organization: OrgNode[];
  secrets: Secret[];
}
