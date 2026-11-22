/** Shapes of the `/api/v2/qa/*` and `/api/v2/prisms/{id}/computer` answers (untyped dicts in the OpenAPI schema). */

export interface QaCases {
  total?: number;
  pass?: number;
  fail?: number;
  blocked?: number;
  skipped?: number;
}

export interface QaApprovalView {
  question?: string;
  site?: string;
  reason?: string;
  summary?: string;
  details?: string;
  frame?: unknown;
  budget_usd?: number;
  max_turns?: number;
}

export interface QaApproval {
  id: string;
  kind: string;
  view?: QaApprovalView;
  title?: string;
  severity?: string;
  steps?: string;
  expected?: string;
  actual?: string;
  status: string;
}

export interface QaPlan {
  title?: string;
  /** Work plans: ordered steps. */
  steps?: string[];
  sites?: string[];
  any_public_site?: boolean;
  uses?: string[];
  asks_first?: string[];
  max_minutes?: number;
  /** QA plans. */
  pages?: string[];
  features?: string[];
  acceptance_criteria?: string[];
  allow_bug_filing?: boolean;
  may_file_bugs?: boolean;
  environment?: string | null;
  host?: string | null;
  discovery_mode?: string;
  max_turns?: number;
  budget_usd?: number | null;
}

export interface ChecklistStep {
  title: string;
  status: string;
}

export interface QaCaseResult {
  title: string;
  status: string;
  given?: string;
  when?: string;
  then?: string;
  notes?: string;
  screens?: number[];
}

export interface QaBug {
  title: string;
  severity: string;
  steps?: string;
  expected?: string;
  actual?: string;
  screens?: number[];
}

export interface QaCoveragePage {
  url: string;
  status: string;
  reason?: string;
}

export interface QaReport {
  kind?: string;
  counts?: QaCases;
  bugs?: QaBug[];
  cases?: QaCaseResult[];
  coverage?: { pages?: QaCoveragePage[]; truncated?: boolean };
  partial?: boolean;
  pages?: unknown[];
  duration_seconds?: number | null;
  cost_usd?: number;
}

export interface WorkFile {
  index: number;
  name: string;
}

export interface WorkReport {
  kind: "work";
  outcome?: string;
  row_count?: number;
  files?: WorkFile[];
  columns?: string[];
  rows?: Array<Record<string, unknown>>;
  needs_attention?: string[];
  next_steps?: string[];
  duration_seconds?: number | null;
  cost_usd?: number;
}

export interface QaRun {
  id: string;
  prism_id: string;
  state: string;
  active: boolean;
  kind?: string;
  site?: string | null;
  environment?: string | null;
  plan?: QaPlan;
  checklist?: ChecklistStep[];
  frame?: number | null;
  screen?: number | null;
  current_url?: string | null;
  activity?: string | null;
  startup_warning?: string | null;
  activity_log?: Array<{ text: string }>;
  cases?: QaCases;
  turn?: number;
  max_turns?: number | null;
  cost_usd?: number;
  budget_usd?: number | null;
  started_at?: string | null;
  ended_at?: string | null;
  error?: string | null;
  approvals: QaApproval[];
  report?: QaReport | WorkReport | null;
}

export interface ComputerInfo {
  state?: string;
  reason?: string | null;
  run_id?: string | null;
}

export interface SavedLogin {
  id: string;
  site: string;
  username: string;
  remember: boolean;
}

export interface QaStatus {
  available: boolean;
  computers?: boolean;
  reason?: string | null;
}

/** Edits sent to `/qa/runs/{id}/start` (QA plan or work plan). */
export interface PlanEdits {
  pages?: string[];
  acceptance_criteria?: string[];
  max_turns?: number | undefined;
  budget_usd?: number | undefined;
  allow_bug_filing?: boolean;
  steps?: string[];
  sites?: string[];
  any_public_site?: boolean;
}

export interface ApprovalDecision {
  decision: string;
  answer?: string;
  login?: { username: string; password: string; remember: boolean };
}

export const isWorkReport = (report: QaReport | WorkReport): report is WorkReport => report.kind === "work";

export type ChatScroll = "auto" | "keep" | "bottom";

export interface ComputersHost {
  /** Reload the open conversation's messages. */
  refreshMessages: () => Promise<void>;
  /** Ask the chat to re-render its message stream (old `renderStream`); `scroll` is the old `{ scroll }` option. */
  rerenderChat: (options?: { scroll?: ChatScroll }) => void;
  setStatus: (message: string | null, isError?: boolean) => void;
}

export interface ChatMessageLike {
  content: string;
  job_id?: string | null;
  message_metadata?: Record<string, unknown> | null;
  [key: string]: unknown;
}
