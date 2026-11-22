import { useChatController, useChatState } from "./ChatContext";
import { humanize, initialOf, SOURCE_KINDS, toneFor } from "./format";
import type { TeamsSource } from "./types";

function Avatar({ text }: { text: string }) {
  return <span className={`avatar ${toneFor(text)}`}>{initialOf(text)}</span>;
}

function Spinner() {
  return <span className="spinner" />;
}

interface OptionProps {
  id: string;
  label: string;
  detail: string;
  onChoose: () => void;
}

function SourceOption({ id, label, detail, onChoose }: OptionProps) {
  const { sourcePicker } = useChatState();
  const choosing = sourcePicker.choosing?.key === id ? sourcePicker.choosing : null;
  return (
    <button type="button" className={`source-option${choosing ? " choosing" : ""}`} onClick={onChoose}>
      <Avatar text={label} />
      <span className="source-copy">
        <strong>{label}</strong>
        <span>{choosing ? choosing.text : detail}</span>
      </span>
      {choosing ? <Spinner /> : null}
    </button>
  );
}

function sourceDetail(source: TeamsSource): string {
  return (
    source.resolution_rationale ||
    `${SOURCE_KINDS[String(source.chat_type).toLowerCase()] || humanize(source.chat_type)} · ${source.participants.join(", ") || "Participants unavailable"}`
  );
}

/** Choosing a Teams chat to constrain requests to. */
export function SourceDialog() {
  const controller = useChatController();
  const { sourcePicker, sources } = useChatState();
  const needle = sourcePicker.query.trim().toLowerCase();
  const matches = sources.filter((source) => `${source.label} ${source.participants.join(" ")}`.toLowerCase().includes(needle));
  const ready = sourcePicker.status === "ready";
  // "All chats" is listed first unless the user is searching.
  const showAuto = ready && !needle;
  const empty = !ready || (!matches.length && !showAuto);

  return (
    <dialog
      id="agent-source-dialog"
      className="picker"
      ref={(node) => {
        controller.refs.sourceDialog = node;
      }}
    >
      <form method="dialog" className="agent-source-dialog-form">
        <div>
          <h2 id="agent-source-dialog-title">Choose a Teams source constraint</h2>
          <p id="agent-source-dialog-note" className="panel-note">
            All chats lets Prism choose for every request. Choose one chat only to apply a hard constraint.
          </p>
        </div>
        <label className="sr-only" htmlFor="agent-source-search">
          Search chats
        </label>
        <input
          id="agent-source-search"
          ref={(node) => {
            controller.refs.sourceSearch = node;
          }}
          type="search"
          autoComplete="off"
          placeholder="Search chats or participants"
          value={sourcePicker.query}
          onChange={(event) => controller.setSourceQuery(event.target.value)}
        />
        <div
          id="agent-source-list"
          className={`agent-source-list${empty ? " empty-state" : ""}${sourcePicker.choosing ? " is-busy" : ""}`}
          aria-busy={sourcePicker.choosing ? true : undefined}
        >
          {sourcePicker.status === "loading" ? (
            <>
              <Spinner /> Loading your Teams chats…
            </>
          ) : sourcePicker.status === "error" ? (
            sourcePicker.error
          ) : !matches.length && !showAuto ? (
            "No matching Teams chats."
          ) : (
            <>
              {showAuto ? (
                <SourceOption id="all" label="All chats" detail="Prism picks the relevant Teams chats from each request" onChoose={() => void controller.clearSourceConstraint()} />
              ) : null}
              {matches.map((source) => (
                <SourceOption key={source.external_id} id={source.external_id} label={source.label} detail={sourceDetail(source)} onChoose={() => void controller.selectSource(source)} />
              ))}
            </>
          )}
        </div>
        <div className="dialog-actions">
          <button className="button secondary" type="submit" value="cancel">
            Cancel
          </button>
        </div>
      </form>
    </dialog>
  );
}
