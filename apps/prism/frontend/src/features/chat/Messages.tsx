import { renderQaMessage } from "@/features/computers";
import { useChatController } from "./ChatContext";
import { ACTIVE_JOB_STATES, formatTime, humanize, PROGRESS_LABELS, RECOVERY } from "./format";
import { AssistantShell, Failure, MsgBubble, TurnDetails, TypingBubble } from "./parts";
import { JobActions, ReviewTurn, SourcePlan } from "./ReviewCard";
import type { Message, PendingSubmission, Review, Turn } from "./types";

interface UserMessageData {
  id: string;
  content: string;
  created_at: string;
}

export function UserMessage({ message }: { message: UserMessageData }) {
  const controller = useChatController();
  return (
    <article
      className="turn user"
      data-message={message.id}
      tabIndex={-1}
      ref={(node) => {
        if (node) controller.refs.messages.set(message.id, node);
        else controller.refs.messages.delete(message.id);
      }}
    >
      <div className="bubble" title={formatTime(message.created_at)}>
        <p>{message.content}</p>
      </div>
    </article>
  );
}

export function PendingTurn({ pending }: { pending: PendingSubmission }) {
  return (
    <>
      <UserMessage message={{ id: "pending-submission", content: pending.content, created_at: pending.createdAt }} />
      <AssistantShell extraClass="working pending-submission">
        <TypingBubble label={pending.label} />
      </AssistantShell>
    </>
  );
}

const hasReview = (turn: Turn | undefined): turn is Turn & { review: Review } => Boolean(turn?.review);

export function AssistantMessage({ message, turn }: { message: Message; turn: Turn | undefined }) {
  if (hasReview(turn) && message.message_metadata?.kind === "conversation_review") return <ReviewTurn turn={turn} />;
  const qa = renderQaMessage(message);
  if (qa) {
    return (
      <AssistantShell>
        {qa.lead ? (
          <MsgBubble>
            <p className="review-summary">{qa.lead}</p>
          </MsgBubble>
        ) : null}
        {qa.card}
      </AssistantShell>
    );
  }
  return (
    <AssistantShell>
      <MsgBubble>
        <p className="review-summary">{message.content}</p>
      </MsgBubble>
    </AssistantShell>
  );
}

/* A review that is still running, or did not finish. */
export function ProgressTurn({ turn }: { turn: Turn }) {
  const controller = useChatController();
  const { job } = turn;
  const active = ACTIVE_JOB_STATES.includes(job.state) || job.state === "executing";
  const failure = job.safe_error_detail
    ? { code: job.safe_error_code ?? null, message: job.safe_error_detail }
    : turn.error
      ? { code: turn.errorCode, message: turn.error }
      : null;
  return (
    <AssistantShell extraClass="working" progress={job.id}>
      {active && !failure ? (
        <TypingBubble label={PROGRESS_LABELS[job.state] || humanize(job.state)} />
      ) : !failure ? (
        <MsgBubble>
          <p>{job.state === "cancelled" ? "Stopped before I finished this one." : "I didn't get to finish this one."}</p>
        </MsgBubble>
      ) : failure.code && RECOVERY[failure.code] ? (
        <Failure {...failure} />
      ) : (
        <MsgBubble>
          <p>{`I couldn't finish this one. ${failure.message}`}</p>
        </MsgBubble>
      )}
      <JobActions job={job} />
      {/* What it is reading and the step list stay available, out of the conversation. */}
      <div className="turn-quiet">
        <TurnDetails label={active ? "Working on it" : "Details"} detailKey={`progress:${job.id}`}>
          <SourcePlan job={job} open />
          {job.steps.length ? (
            <ul className="step-list">
              {job.steps.map((step, index) => (
                <li className={`step ${step.state}`} key={step.id ?? index}>
                  {step.label}
                </li>
              ))}
            </ul>
          ) : null}
          {ACTIVE_JOB_STATES.includes(job.state) ? (
            <div className="item-actions">
              <button type="button" className="mini-button" onClick={() => void controller.cancelJob(job)}>
                Cancel
              </button>
              <button type="button" className="mini-button" onClick={() => void controller.recoverJob(job)}>
                Resume
              </button>
            </div>
          ) : null}
        </TurnDetails>
      </div>
    </AssistantShell>
  );
}
