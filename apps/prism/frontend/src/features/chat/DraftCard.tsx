import { useLayoutEffect, useRef, useState } from "react";
import { useChatController, useChatState } from "./ChatContext";
import type { ApprovalPhase } from "./jobs";
import { draftState, draftStatusText } from "./format";
import { EvidenceList, MsgBubble } from "./parts";
import type { Execution, Proposal, Turn } from "./types";

export function autoGrow(textarea: HTMLTextAreaElement, max = Infinity): void {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight + 2, max)}px`;
}

/** Runs an async action once at a time (a double click must not send twice) and exposes its phase. */
function useGuardedAction() {
  const [phase, setPhase] = useState<ApprovalPhase | null>(null);
  const busy = useRef(false);
  const run = async (action: (onPhase: (phase: ApprovalPhase) => void) => Promise<void>) => {
    if (busy.current) return;
    busy.current = true;
    try {
      await action(setPhase);
    } finally {
      busy.current = false;
      setPhase(null);
    }
  };
  return { phase, run };
}

interface DraftCardProps {
  turn: Turn;
  proposal: Proposal;
  execution: Execution | null | undefined;
}

export function DraftCard({ turn, proposal, execution }: DraftCardProps) {
  const controller = useChatController();
  const { drafts, openDetails } = useChatState();
  const { review, job } = turn;
  const [text, setText] = useState(() => drafts.get(proposal.id) ?? proposal.body);
  const [seenBody, setSeenBody] = useState(proposal.body);
  if (seenBody !== proposal.body) {
    setSeenBody(proposal.body);
    setText(drafts.get(proposal.id) ?? proposal.body);
  }
  const textarea = useRef<HTMLTextAreaElement>(null);
  const { phase, run } = useGuardedAction();
  useLayoutEffect(() => {
    if (textarea.current) autoGrow(textarea.current);
  }, [text]);

  const state = draftState(proposal, execution);
  const label = proposal.destination.label || "the selected Teams chat";
  const pending = proposal.state === "pending";
  const dirty = pending && text.trim() !== proposal.body.trim();
  const empty = !text.trim();
  // No stored Teams messages back this draft; say so instead of implying evidence.
  const fromTests = Boolean(job.requested_scope?.qa_draft);
  const detailKey = `draft:${proposal.id}`;

  const onInput = (value: string) => {
    setText(value);
    controller.setDraft(proposal.id, value.trim() !== proposal.body.trim() ? value : null);
  };

  const canResend = !fromTests && (["rejected", "expired", "failed"].includes(proposal.state) || execution?.state === "failed");

  return (
    <section className={`draft-card ${state.key}`}>
      <div className="draft-head">
        <span className="draft-avatar">{label.trim().charAt(0).toUpperCase()}</span>
        <span className="draft-dest">
          {"To "}
          <strong>{label}</strong>
        </span>
        <span className={`draft-state ${state.tone}`}>{state.label}</span>
      </div>
      <textarea
        ref={textarea}
        className="draft-body autogrow"
        rows={2}
        aria-label="Reply that will be sent to Teams"
        value={pending ? text : (drafts.get(proposal.id) ?? proposal.body)}
        readOnly={!pending}
        onChange={(event) => onInput(event.target.value)}
      />
      {fromTests ? (
        <p className="draft-basis">Written from my test results, not from Teams messages. Edit it as you like, then approve to send.</p>
      ) : !proposal.evidence_ids?.length ? (
        <p className="draft-basis">Based on your instruction. There were no Teams messages to go on, so check it before sending.</p>
      ) : null}
      <p className={`draft-status ${state.tone}`}>
        {dirty ? "You edited this draft. Save the edit, then approve it." : draftStatusText(proposal, execution)}
      </p>
      <details
        className="draft-more"
        open={openDetails.has(detailKey)}
        onToggle={(event) => controller.setDetailOpen(detailKey, event.currentTarget.open)}
      >
        <summary>Why this reply</summary>
        <div className="draft-more-body">
          <p>{proposal.reason}</p>
          <EvidenceList turn={turn} ids={proposal.evidence_ids} label="Messages behind this reply" />
          {review?.applied_preferences?.length ? (
            <div className="pref-used">
              <span className="pref-label">Shaped by your preferences</span>
              {review.applied_preferences.map((item, index) => (
                <span className="pref-chip" title={item.instruction} key={index}>
                  {item.instruction}
                </span>
              ))}
              <button type="button" className="link-button" onClick={() => controller.setPreferencesOpen(true)}>
                Manage
              </button>
            </div>
          ) : null}
        </div>
      </details>
      {pending ? (
        <div className="draft-actions">
          <button type="button" className="button ghost" onClick={() => void controller.rejectDraft(proposal)}>
            Reject
          </button>
          {fromTests ? null : (
            <button type="button" className="button ghost" onClick={() => controller.requestActionRedraft(proposal)}>
              Redraft
            </button>
          )}
          <span className="spacer" />
          <button
            type="button"
            className="button secondary"
            hidden={!dirty}
            disabled={empty}
            onClick={() => void controller.reviseProposal(turn, proposal, text)}
          >
            Save edit
          </button>
          <button
            type="button"
            className="button approve"
            disabled={phase !== null || dirty || empty}
            onClick={() => void run((onPhase) => controller.approveAndSend(proposal, onPhase))}
          >
            {phase === "approving" ? "Approving…" : phase === "sending" ? "Sending…" : "Approve and send"}
          </button>
        </div>
      ) : proposal.state === "approved" && !execution ? (
        <div className="draft-actions">
          <span className="spacer" />
          <button
            type="button"
            className="button"
            disabled={phase !== null}
            onClick={() => void run((onPhase) => controller.sendApprovedProposal(proposal, onPhase))}
          >
            {phase === "sending" ? "Sending…" : "Send approved message"}
          </button>
        </div>
      ) : canResend ? (
        <div className="draft-actions">
          <span className="spacer" />
          <button type="button" className="button secondary" onClick={() => void controller.retryJob(job, true)}>
            Regenerate
          </button>
        </div>
      ) : null}
    </section>
  );
}

export function ActionPlanCard({ turn }: { turn: Turn }) {
  const controller = useChatController();
  const { drafts } = useChatState();
  const { phase, run } = useGuardedAction();
  const plan = turn.review?.action_plan;
  if (!plan) return null;
  const pending = plan.actions.filter(({ proposal }) => proposal.state === "pending");
  return (
    <section className={`action-plan plan-${plan.state}`}>
      <MsgBubble>
        <p>
          {pending.length
            ? `${plan.summary}. ${pending.length === 1 ? "One message is" : `${pending.length} messages are`} ready for you to check.`
            : `${plan.summary}.`}
        </p>
      </MsgBubble>
      {pending.length > 1 ? (
        <div className="action-plan-bulk">
          <span className="panel-note">Sends exactly the messages below, as written.</span>
          <button
            type="button"
            className="button secondary"
            disabled={phase !== null || pending.some(({ proposal }) => drafts.has(proposal.id))}
            onClick={() =>
              void run(async (onPhase) => {
                onPhase("approving");
                await controller.approveActionPlan(turn);
              })
            }
          >
            {phase !== null ? "Approving exact drafts…" : `Approve all ${pending.length} visible drafts`}
          </button>
        </div>
      ) : null}
      {plan.actions.map(({ proposal, execution }) => (
        <div className="planned-action" key={proposal.id}>
          {proposal.depends_on_logical_action_ids?.length ? (
            <div className="planned-action-order">Goes after the previous message</div>
          ) : null}
          <DraftCard turn={turn} proposal={proposal} execution={execution} />
        </div>
      ))}
    </section>
  );
}
