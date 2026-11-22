import type { PrismLike } from "@/lib/events";
import type { Schema } from "@/types";

export type Thread = Schema<"AgentThreadRead">;
export type Message = Schema<"AgentThreadMessageRead">;
export type Evidence = Schema<"AgentEvidenceRead">;
export type Observation = Schema<"PrismObservationRead">;
export type Preference = Schema<"AgentPreferenceRead">;
export type TeamsSource = Schema<"TeamsChatSourceRead"> & { resolution_rationale?: string | null };

/** The Prism fields the chat reads; the list item itself stays the shared `PrismLike`. */
export interface PrismFields {
  description?: string | null;
  template_key?: string;
  job_role?: string | null;
  department?: string | null;
  logins_policy?: string | null;
  state?: string;
  lifecycle_version?: number;
  color?: string | null;
}
export type ChatPrism = PrismLike & PrismFields;

export interface SourceMetadata {
  chat_type?: string;
  participants?: string[];
  resolution_rationale?: string;
}

export interface JobSource {
  external_id: string;
  label: string | null;
  selection_reason: string;
  source_metadata?: SourceMetadata;
}

export interface RequestedScope {
  qa_draft?: unknown;
  excluded_external_ids?: string[];
  limits?: Record<string, unknown>;
}

export interface JobStep {
  id?: string;
  label: string;
  state: string;
}

export interface Job {
  id: string;
  thread_id: string;
  goal: string;
  state: string;
  version: number;
  scope_mode: string;
  source_label?: string | null;
  sources: JobSource[];
  requested_scope?: RequestedScope;
  steps: JobStep[];
  safe_error_code?: string | null;
  safe_error_detail?: string | null;
  created_at: string;
  started_at?: string | null;
}

export interface Destination {
  label?: string;
  [key: string]: unknown;
}

export interface Approval {
  decision: string;
  manager_identity: string;
  reason?: string | null;
  decided_at: string;
}

export interface Proposal {
  id: string;
  job_id: string;
  state: string;
  body: string;
  reason: string;
  revision: number;
  payload_hash: string;
  sequence: number;
  destination: Destination;
  evidence_ids?: string[];
  depends_on_logical_action_ids?: string[];
  created_at: string;
  approval?: Approval | null;
}

export interface Execution {
  state: string;
  completed_at?: string | null;
  started_at?: string | null;
  created_at: string;
  safe_error_detail?: string | null;
}

export interface PlannedAction {
  proposal: Proposal;
  execution?: Execution | null;
}

export interface ActionPlan {
  id: string;
  job_id: string;
  state: string;
  summary: string;
  actions: PlannedAction[];
}

export interface AttentionItem {
  kind?: string;
  title: string;
  detail: string;
  evidence_ids?: string[];
}

export interface ManagerQuestion {
  question: string;
  evidence_ids?: string[];
}

export interface Review {
  action_plan?: ActionPlan | null;
  proposal?: Proposal | null;
  execution?: Execution | null;
  summary: string;
  attention_items: AttentionItem[];
  manager_questions: ManagerQuestion[];
  limitations?: string[];
  confidence: number;
  requires_reply?: boolean;
  summary_evidence_ids?: string[];
  applied_preferences?: { instruction: string }[];
  provider: string;
  model: string;
  created_at: string;
}

/** One job's slice of the conversation: the job, its review and the evidence it cites. */
export interface Turn {
  job: Job;
  review: Review | null;
  evidence: Map<string, Evidence>;
  error: string | null;
  errorCode: string | null;
}

export interface PendingSubmission {
  content: string;
  label: string;
  createdAt: string;
}

export interface Failure {
  code: string | null;
  message: string;
}

export type ScrollKind = "auto" | "bottom" | "keep" | "none";
export interface ScrollRequest {
  kind: ScrollKind;
  /** After scrolling, centre and focus this message (search jump). */
  focusMessage?: string;
  nonce: number;
}

export type FocusTarget = "composer" | "search" | "searchButton" | "preferenceInput" | "archiveYes";

export interface SourcePicker {
  status: "loading" | "ready" | "error";
  error: string;
  query: string;
  /** The option being saved: shown busy while the server stores the choice. */
  choosing: { key: string; text: string } | null;
}

export type DrawerTab = "preferences" | "profile" | "scope" | "people" | "more";

export type SearchView =
  | { kind: "idle" }
  | { kind: "short" }
  | { kind: "searching" }
  | { kind: "empty"; query: string }
  | { kind: "results"; query: string; items: Message[] }
  | { kind: "error"; failure: Failure };

export interface ObservationPage {
  items: Observation[];
}

export interface IncidentEvent {
  event_type: string;
  created_at: string;
  reason: string;
  mine?: boolean;
}
export interface IncidentHistory {
  other_prisms?: number;
  events: IncidentEvent[];
}

export interface Suggestions {
  steps?: string[];
  suggestions?: string[];
}

export interface NotificationSetting {
  enabled: boolean;
  min_urgency: string;
}

export interface ChatState {
  threads: Thread[];
  activeThread: Thread | null;
  messages: Message[];
  jobs: Job[];
  turns: Map<string, Turn>;
  updates: Observation[];
  currentJob: Job | null;
  sources: TeamsSource[];
  preferences: Preference[];
  preferencesFor: string | null;
  drafts: Map<string, string>;
  loading: boolean;
  prism: ChatPrism | null;
  pendingSubmission: PendingSubmission | null;
  hasEarlier: boolean;
  anchor: string | null;
  composerText: string;
  composerBusy: boolean;
  composerFailure: Failure | null;
  /** False until the first stream render: the static placeholder shows until then. */
  rendered: boolean;
  focus: { target: FocusTarget; nonce: number };
  sourcePicker: SourcePicker;
  search: { open: boolean; query: string; view: SearchView };
  drawer: { open: boolean; tab: DrawerTab; openNonce: number; archiveConfirm: boolean; profileNonce: number };
  scroll: ScrollRequest;
  /** Keys of `<details>` the user opened; survives re-renders and thread switches like the old module Set. */
  openDetails: Set<string>;
}
