import type { Schema } from "@/types";

export type Prism = Schema<"PrismRead">;
export type OnboardingSession = Schema<"PrismOnboardingSessionRead">;
export type OnboardingQuestion = Schema<"PrismOnboardingQuestionRead">;
export type OnboardingAnswer = Schema<"PrismOnboardingAnswerRead">;
export type TeamsPolicy = Schema<"PrismTeamsSourcePolicyRead">;
export type TriggerPolicy = Schema<"PrismTriggerPolicyRead">;

export type OnboardingState = null | "loading" | "missing" | "error" | OnboardingSession;

/** The agreement document is a free-form dict on the wire; these are the keys the chat reads. */
export interface AgreementContent {
  mission?: string;
  attention_signals?: string[] | string;
  regular_brief?: string;
  teams_scope?: string;
  tone?: string;
  allowed_proposals?: string[] | string;
  restrictions?: string[] | string;
  safety_rule?: string;
  current_limitations?: string;
  work?: unknown;
  answers?: Array<{ key: string; answer?: string | null }>;
}
export interface Agreement {
  agreement: AgreementContent;
  status: "draft" | "confirmed" | "superseded";
  revision: number;
}
export type AgreementState = null | "loading" | "error" | Agreement;

export interface ConversationMessage {
  id?: string;
  role: string;
  content: string;
  created_at?: string | null;
}
export interface Conversation {
  messages: ConversationMessage[];
  preferences?: Array<{ instruction: string }>;
}
export type ConversationState = null | "loading" | "error" | Conversation;

export interface TeamsSource {
  external_id: string;
  label: string;
  chat_type?: string | null;
  participants?: string[];
}

export interface ActivityEvent {
  event_kind: string;
  body_text?: string | null;
  sender_display_name: string;
  source_label?: string | null;
}
export interface ActivityPage {
  items?: ActivityEvent[];
}
export interface Observation {
  state: string;
  urgency: string;
  summary: string;
  suggested_next_step: string;
}
export interface ObservationsPage {
  items?: Observation[];
}
export interface RunItem {
  state: string;
  completed_at?: string | null;
  safe_error?: string | null;
}
export interface RunsPage {
  items?: RunItem[];
}
export interface ManualRun extends RunItem {
  result?: { status?: string; scanned_chats?: number; created_events?: number } | null;
}

export type Loadable<T> = null | "loading" | "error" | T;

export interface OrganizationData {
  chief_of_staff_id: string | null;
  owner_name: string;
  departments: string[];
  members: Prism[];
}
