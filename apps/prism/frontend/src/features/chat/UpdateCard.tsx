import { useRef, useState } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { useChatController } from "./ChatContext";
import {
  capitalize,
  confidenceText,
  FEEDBACK_LABELS,
  FEEDBACK_REASONS,
  formatTime,
  INCIDENT_LABELS,
  SIGNAL_LABELS,
  URGENCY_TONES,
} from "./format";
import { AssistantShell, Limitations, MsgBubble, TurnDetails } from "./parts";
import type { IncidentHistory, Observation } from "./types";

// Feedback is saved for this Prism only. It never changes behavior until you confirm it in Status & tuning.
function Feedback({ item }: { item: Observation }) {
  const { setStatus } = useApp();
  const [kinds, setKinds] = useState<string[]>(item.feedback_kinds || []);
  const [reasonsOpen, setReasonsOpen] = useState(() => FEEDBACK_REASONS.some((kind) => kinds.includes(kind)));
  const reasonsId = `feedback-reasons-${item.id}`;

  const save = async (kind: string) => {
    try {
      const result = await agentApi<{ feedback_kinds: string[] }>(`/api/v2/prisms/${item.prism_id}/observations/${item.id}/feedback`, {
        method: "POST",
        ...jsonBody({ kind }),
      });
      setKinds(result.feedback_kinds);
      setStatus("Thanks. Noted for this Prism only.");
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };
  const choice = (kind: string) => (
    <button
      key={kind}
      type="button"
      className={`mini-button feedback${kinds.includes(kind) ? " selected" : ""}`}
      data-kind={kind}
      aria-pressed={kinds.includes(kind)}
      onClick={() => void save(kind)}
    >
      {FEEDBACK_LABELS[kind]}
    </button>
  );
  return (
    <div className="update-feedback">
      <div className="feedback-main">
        <span className="turn-meta">Was this useful?</span>
        {choice("helpful")}
        {choice("not_helpful")}
        <button
          type="button"
          className="mini-button ghost feedback-more"
          aria-controls={reasonsId}
          aria-expanded={reasonsOpen}
          onClick={() => setReasonsOpen(!reasonsOpen)}
        >
          What was off?
        </button>
      </div>
      <div className="feedback-reasons" id={reasonsId} role="group" aria-label="What was wrong" hidden={!reasonsOpen}>
        {FEEDBACK_REASONS.map(choice)}
      </div>
    </div>
  );
}

function Incident({ item }: { item: Observation }) {
  const { setStatus } = useApp();
  const [view, setView] = useState<IncidentHistory | "error" | null>(null);
  const loaded = useRef(false);
  const path = `/api/v2/prisms/${item.prism_id}/observations/${item.id}/incident`;

  const load = async () => {
    try {
      setView(await agentApi<IncidentHistory>(path));
    } catch {
      setView("error");
    }
  };
  const split = async () => {
    try {
      await agentApi(`${path}/split`, { method: "POST" });
      loaded.current = false;
      await load();
      setStatus("Split into its own incident. Nothing was deleted.");
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };

  return (
    <details
      className="incident-history"
      onToggle={(event) => {
        if (event.currentTarget.open && !loaded.current) {
          loaded.current = true;
          void load();
        }
      }}
    >
      <summary>Why this is grouped</summary>
      <div className="incident-body">
        {view === "error" ? (
          <p className="turn-meta">Incident history is unavailable right now.</p>
        ) : view ? (
          <>
            {view.other_prisms ? (
              <p className="turn-meta">{`The same event was also seen by ${view.other_prisms} other Prism${view.other_prisms === 1 ? "" : "s"}. You were alerted once.`}</p>
            ) : null}
            <ul>
              {view.events.map((event, index) => (
                <li key={index}>{`${INCIDENT_LABELS[event.event_type]} · ${formatTime(event.created_at)} · ${event.reason}`}</li>
              ))}
            </ul>
            {view.events.some((event) => event.mine && ["linked", "updated", "reopened"].includes(event.event_type)) ? (
              <button type="button" className="mini-button" onClick={() => void split()}>
                This is a different incident
              </button>
            ) : null}
          </>
        ) : null}
      </div>
    </details>
  );
}

/** A proactive update, rendered as a first-class turn in this Prism's conversation. */
export function UpdateCard({ item }: { item: Observation }) {
  const controller = useChatController();
  const [expanded, setExpanded] = useState(false);
  const urgency = capitalize(item.urgency);
  const signal = SIGNAL_LABELS[item.signal_type];
  const summaryText =
    item.state === "open"
      ? `${item.summary}.`
      : `${item.summary}. ${item.state === "resolved" ? "This looks resolved now." : "There is a newer update on this."}`;
  return (
    <AssistantShell extraClass={`proactive-update ${item.state}`} observation={item.id}>
      <MsgBubble>
        <p className="review-summary">
          {["critical", "high"].includes(item.urgency) && item.state === "open" ? (
            <span className={`urgency-dot ${URGENCY_TONES[item.urgency]}`} title={`${urgency} urgency`} />
          ) : null}
          {summaryText}
        </p>
      </MsgBubble>
      {item.verified_facts.length ? (
        <div className={`say say-quote${expanded ? " expanded" : ""}`} title="Show the full message" onClick={() => setExpanded(!expanded)}>
          {item.verified_facts.map((fact, index) => (
            <p key={index}>{fact}</p>
          ))}
        </div>
      ) : null}
      {item.state === "open" && item.suggested_next_step ? (
        <MsgBubble>
          <p>{item.suggested_next_step}</p>
        </MsgBubble>
      ) : null}
      <div className="turn-quiet">
        <TurnDetails label={[item.source_label, signal].filter(Boolean).join(" · ") || "Details"} detailKey={`update:${item.id}`}>
          <p className="turn-meta">{`${signal || "Update"} · ${urgency} urgency · ${confidenceText(item.confidence)}`}</p>
          <p className="update-why">{`Why it matters: ${item.why_it_matters}`}</p>
          {item.inference ? <p className="update-inference">{`Inference, not a verified fact: ${item.inference}`}</p> : null}
          {item.unknowns.length ? <Limitations items={item.unknowns} /> : null}
          <Incident item={item} />
          <Feedback item={item} />
        </TurnDetails>
        {item.state === "open" ? (
          <button type="button" className="link-button" onClick={() => void controller.draftFromUpdate(item)}>
            Prepare a Teams draft
          </button>
        ) : null}
      </div>
    </AssistantShell>
  );
}
