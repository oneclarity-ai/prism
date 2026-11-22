import type { ReactNode } from "react";
import { useChatController, useChatState } from "./ChatContext";
import { reconnectMicrosoft, RECOVERY, formatTime } from "./format";
import type { Evidence as EvidenceItem, Failure as FailureData, Turn } from "./types";

/** Stable domain codes map to one clear next step; unknown codes show the plain message. */
export function Failure({ code, message }: FailureData) {
  const recovery = code ? RECOVERY[code] : undefined;
  if (!recovery) return <p className="inline-error">{message}</p>;
  return (
    <div className="callout recovery" role="alert">
      <span className="callout-icon">!</span>
      <div className="callout-body">
        <strong>{recovery.title}</strong>
        <p>{recovery.detail}</p>
        {recovery.action ? (
          <button type="button" className="mini-button" onClick={reconnectMicrosoft}>
            {recovery.action}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export interface ShellProps {
  extraClass?: string;
  job?: string;
  progress?: string;
  observation?: string;
  children: ReactNode;
}

export function AssistantShell({ extraClass = "", job, progress, observation, children }: ShellProps) {
  return (
    <article
      className={`turn assistant ${extraClass}`.trim()}
      data-job={job}
      data-progress={progress}
      data-observation={observation}
    >
      <span className="avatar prism">P</span>
      <div className="turn-body">{children}</div>
    </article>
  );
}

/** One chat bubble. Replies read like messages from a colleague; the machinery lives in details. */
export function MsgBubble({ children, className = "say" }: { children: ReactNode; className?: string }) {
  return <div className={className}>{children}</div>;
}

/** "• Title → detail" lines, the way a person would summarise a list in chat. */
export function ListBubble({ intro, rows }: { intro: string; rows: [string, string][] }) {
  return (
    <div className="say say-list">
      {intro ? <p>{intro}</p> : null}
      {rows.map(([title, detail], index) => (
        <p className="say-line" key={index}>
          <strong>{title}</strong>
          {detail ? ` → ${detail}` : null}
        </p>
      ))}
    </div>
  );
}

export function TypingBubble({ label }: { label: string }) {
  return (
    <div className="say say-typing" role="status">
      <span className="typing-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** Sources, confidence, evidence, and the audit trail stay one click away instead of in the message. */
export function TurnDetails({ label, detailKey, children }: { label: string; detailKey: string; children: ReactNode }) {
  const controller = useChatController();
  const open = useChatState().openDetails.has(detailKey);
  return (
    <details className="turn-details" open={open} onToggle={(event) => controller.setDetailOpen(detailKey, event.currentTarget.open)}>
      <summary>{label}</summary>
      <div className="turn-details-body">{children}</div>
    </details>
  );
}

export function EvidenceList({ turn, ids, label = "Evidence" }: { turn: Turn; ids: string[] | undefined; label?: string }) {
  const cited = (ids || []).map((id) => turn.evidence.get(id)).filter((item): item is EvidenceItem => Boolean(item));
  if (!cited.length) return null;
  const groups = new Map<string, { label: string; items: EvidenceItem[] }>();
  cited.forEach((item) => {
    const key = item.source_external_id || "unknown";
    const group = groups.get(key) ?? { label: item.source_label || "Teams chat", items: [] };
    group.items.push(item);
    groups.set(key, group);
  });
  return (
    <details className="evidence">
      <summary>
        {label}
        <span className="tab-count">{cited.length}</span>
      </summary>
      {[...groups.entries()].map(([key, group]) => (
        <EvidenceGroup key={key} group={group} showHeading={groups.size > 1} />
      ))}
    </details>
  );
}

function EvidenceGroup({ group, showHeading }: { group: { label: string; items: EvidenceItem[] }; showHeading: boolean }) {
  return (
    <>
      {showHeading ? <h4 className="evidence-source">{group.label}</h4> : null}
      {group.items.map((item) => (
        <blockquote key={item.id}>
          <div className="quote-head">
            <strong>{item.sender_display_name}</strong>
            <time>{formatTime(item.sent_at)}</time>
          </div>
          <p>{item.excerpt}</p>
        </blockquote>
      ))}
    </>
  );
}

export function Limitations({ items }: { items: string[] }) {
  return (
    <details className="limitations">
      <summary>What Prism could not verify</summary>
      <ul>
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </details>
  );
}
