import type { ReactNode } from "react";
import { ApprovalCard, BusyCard } from "./ApprovalCard";
import { PlanCard } from "./PlanCard";
import { ReportCard } from "./ReportCard";
import type { ChatMessageLike } from "./types";

/** The extra card for a QA/work message, or null to let the chat show it as a normal message. */
export function renderQaMessage(message: ChatMessageLike): { lead: string; card: ReactNode } | null {
  switch (message.message_metadata?.kind) {
    case "qa_plan":
    case "work_plan":
      return { lead: message.content, card: <PlanCard message={message} /> };
    case "qa_approval":
    case "work_approval":
      return { lead: message.content, card: <ApprovalCard message={message} /> };
    case "qa_report":
    case "work_report":
      return { lead: message.content, card: <ReportCard message={message} /> };
    case "work_busy":
      return { lead: message.content, card: <BusyCard message={message} /> };
    default:
      return null;
  }
}
