import type { ReactNode } from "react";
import { useChatController } from "./ChatContext";
import { ActionPlanCard, DraftCard } from "./DraftCard";
import {
  auditEvents,
  CHAT_KINDS,
  confidenceText,
  formatTime,
  humanize,
  metadataOf,
  readLabel,
  SCOPE_LABELS,
} from "./format";
import { AssistantShell, EvidenceList, Failure, Limitations, ListBubble, MsgBubble, TurnDetails } from "./parts";
import type { Job, Review, Turn } from "./types";

/* Choosing a Teams chat: compact chips say which chats Prism read; the details say why and under what limits. */

export function SourcePlan({ job, open = false }: { job: Job; open?: boolean }) {
  const sources = job.sources || [];
  if (!sources.length) {
    return (
      <details className="source-plan" open={open}>
        <summary>Resolving source</summary>
        <p className="panel-note">Prism is resolving an accessible Teams chat from your request.</p>
      </details>
    );
  }
  const scope = job.requested_scope || {};
  const notes: string[] = [];
  if ((scope.excluded_external_ids || []).length) notes.push(`${scope.excluded_external_ids?.length} chat(s) excluded at your request`);
  Object.entries(scope.limits || {}).forEach(([key, value]) => {
    if (["number", "string"].includes(typeof value)) notes.push(`${humanize(key)}: ${String(value)}`);
  });
  return (
    <details className="source-plan" open={open}>
      <summary>
        Why these sources
        <span className="tab-count">{sources.length}</span>
      </summary>
      <ul className="source-plan-list">
        {sources.map((source) => {
          const metadata = metadataOf(source.source_metadata);
          const kind = CHAT_KINDS[String(metadata.chat_type || "").toLowerCase()];
          const participants = (metadata.participants || []).slice(0, 4).join(", ");
          return (
            <li key={source.external_id}>
              <strong>{source.label || "Teams chat"}</strong>
              <span>{[kind, participants].filter(Boolean).join(" · ")}</span>
              <span>
                {source.selection_reason === "destination"
                  ? "Draft destination only · Prism did not read this chat"
                  : metadata.resolution_rationale || humanize(source.selection_reason)}
              </span>
            </li>
          );
        })}
      </ul>
      {notes.length ? <p className="panel-note">{`Limits · ${notes.join(" · ")}`}</p> : null}
      <p className="panel-note">Reading a chat never lets Prism write to it. Every destination is shown separately on its own approval card.</p>
    </details>
  );
}

export function SourceDisclosure({ job }: { job: Job }) {
  const sources = job.sources || [];
  if (!sources.length) return <div className="source-disclosure" />;
  return (
    <div className="source-disclosure">
      <div className="source-chips">
        <span className="source-chips-label">Read from</span>
        {sources
          .filter((source) => source.selection_reason !== "destination")
          .map((source) => (
            <span className="tag blue" key={`read-${source.external_id}`}>
              {source.label || "Teams chat"}
            </span>
          ))}
        {sources
          .filter((source) => source.selection_reason === "destination")
          .map((source) => (
            <span className="tag purple" key={`to-${source.external_id}`}>
              {`Draft to ${source.label || "Teams chat"}`}
            </span>
          ))}
        <span className="tag">{SCOPE_LABELS[job.scope_mode] || humanize(job.scope_mode)}</span>
      </div>
      <SourcePlan job={job} />
    </div>
  );
}

/* A review: summary, what needs attention, a draft reply, and the audit trail. */

function ReviewSection({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <section className="review-section">
      <h3>
        {title}
        <span className="tab-count">{count}</span>
      </h3>
      {children}
    </section>
  );
}

function Finding({
  turn,
  kind,
  title,
  detail,
  evidenceIds,
}: {
  turn: Turn;
  kind: string;
  title: string;
  detail: string;
  evidenceIds: string[] | undefined;
}) {
  return (
    <div className={`finding ${kind}`}>
      <div className="finding-head">
        <strong>{title}</strong>
        {["inference", "conflict"].includes(kind) ? (
          <span className={`tag ${kind === "conflict" ? "orange" : "blue"}`}>
            {kind === "conflict" ? "Conflicting updates" : "Cross-chat inference"}
          </span>
        ) : null}
      </div>
      {detail ? <p>{detail}</p> : null}
      <EvidenceList turn={turn} ids={evidenceIds} />
    </div>
  );
}

function Audit({ turn }: { turn: Turn & { review: Review } }) {
  const events = auditEvents(turn);
  return (
    <details className="audit">
      <summary>
        Audit trail
        <span className="tab-count">{events.length}</span>
      </summary>
      <ol className="audit-list">
        {events.map(([label, time], index) => (
          <li key={index}>
            <span>{label}</span>
            <time>{formatTime(time)}</time>
          </li>
        ))}
      </ol>
    </details>
  );
}

/** Recovery actions shared by the review turn and the progress turn. */
export function JobActions({ job, interrupted = true }: { job: Job; interrupted?: boolean }) {
  const controller = useChatController();
  const recoverable = interrupted && job.state === "executing";
  const retryable = ["failed", "cancelled"].includes(job.state);
  if (!recoverable && !retryable) return null;
  return (
    <div className="item-actions">
      {recoverable ? (
        <button type="button" className="mini-button" onClick={() => void controller.recoverJob(job)}>
          Check interrupted delivery
        </button>
      ) : null}
      {retryable ? (
        <button type="button" className="mini-button" onClick={() => void controller.retryJob(job, false)}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function ReviewTurn({ turn }: { turn: Turn & { review: Review } }) {
  const controller = useChatController();
  const { review, job } = turn;
  const single = (job.sources || []).length <= 1;
  const canFollowUp =
    !review.action_plan && !review.proposal && !review.requires_reply && single && (review.attention_items.length || review.manager_questions.length);
  return (
    <AssistantShell job={job.id}>
      {/* When you asked for a message, the draft is the answer. The analysis behind it stays in details. */}
      {review.action_plan ? (
        <ActionPlanCard turn={turn} />
      ) : review.proposal ? (
        <>
          <MsgBubble>
            <p className="review-summary">{`Here’s a draft for ${review.proposal.destination?.label || "them"}. Have a look before it goes out.`}</p>
          </MsgBubble>
          <DraftCard turn={turn} proposal={review.proposal} execution={review.execution} />
        </>
      ) : (
        <>
          <MsgBubble>
            <p className="review-summary">{review.summary}</p>
          </MsgBubble>
          {review.attention_items.length ? (
            <ListBubble
              intro={review.attention_items.length > 1 ? "What needs you:" : ""}
              rows={review.attention_items.map((item) => [item.title, item.detail])}
            />
          ) : null}
          {review.manager_questions.length === 1 ? (
            <MsgBubble>
              <p>{review.manager_questions[0].question}</p>
            </MsgBubble>
          ) : review.manager_questions.length > 1 ? (
            <ListBubble intro="A few things I need from you:" rows={review.manager_questions.map((item) => [item.question, ""])} />
          ) : null}
        </>
      )}

      <div className="turn-quiet">
        <TurnDetails label={readLabel(turn)} detailKey={`review:${job.id}`}>
          <p className="turn-meta">{confidenceText(review.confidence)}</p>
          <SourceDisclosure job={job} />
          {review.action_plan || review.proposal ? <p>{review.summary}</p> : null}
          <EvidenceList turn={turn} ids={review.summary_evidence_ids} label="Messages behind this" />
          {review.attention_items.length ? (
            <ReviewSection title="Needs your attention" count={review.attention_items.length}>
              {review.attention_items.map((item, index) => (
                <Finding key={index} turn={turn} kind={item.kind || "direct"} title={item.title} detail={item.detail} evidenceIds={item.evidence_ids} />
              ))}
            </ReviewSection>
          ) : null}
          {review.manager_questions.length ? (
            <ReviewSection title="Questions for you" count={review.manager_questions.length}>
              {review.manager_questions.map((item, index) => (
                <Finding key={index} turn={turn} kind="question" title={item.question} detail="" evidenceIds={item.evidence_ids} />
              ))}
            </ReviewSection>
          ) : null}
          {review.limitations?.length ? <Limitations items={review.limitations} /> : null}
          <Audit turn={turn} />
        </TurnDetails>
        {canFollowUp ? (
          <button type="button" className="link-button" onClick={() => void controller.draftFollowUp(job)}>
            Draft a follow-up
          </button>
        ) : null}
      </div>
      {turn.error ? <Failure code={turn.errorCode} message={turn.error} /> : null}
      <JobActions job={job} />
    </AssistantShell>
  );
}
