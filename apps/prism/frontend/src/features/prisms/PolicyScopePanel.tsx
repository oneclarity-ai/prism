import { initial, matchesSource, sourceDetail } from "./helpers";
import { usePrismsInternal } from "./internal";
import type { TeamsPolicy } from "./types";

const MODES: ReadonlyArray<readonly [TeamsPolicy["mode"], string, string]> = [
  ["all_chats", "All accessible chats", "Monitor every Teams chat you can access. This is the default."],
  ["include_only", "Only selected chats", "Monitor only the chats checked below."],
  ["all_except", "All except selected chats", "Never read the chats checked below."],
];

/**
 * The Teams monitoring scope editor (`#prism-policy-dialog`). The chat's settings drawer renders it inside its
 * "scope" panel and calls `usePrisms().runAction("prism-policy-button")` (or emits `scope-open`) when that panel opens.
 */
export function PolicyScopePanel() {
  const { monitoring: m } = usePrismsInternal();
  const pending = m.pendingPolicy;
  const mode = pending?.mode || "all_chats";
  const selected = new Set(pending?.externalIds || []);
  const sources = m.catalog.filter((source) => matchesSource(source, m.policySearch));

  let list;
  if (m.catalogLoading && !m.catalog.length) {
    list = {
      className: "agent-source-list empty-state",
      content: (
        <>
          <span className="spinner" />
          <span>{` Loading your Teams chats… ${pending?.externalIds?.length ? `${pending.externalIds.length} selected so far.` : ""}`}</span>
        </>
      ),
    };
  } else if (!sources.length) list = { className: "agent-source-list empty-state", content: "No matching Teams chats." };
  else {
    list = {
      className: "agent-source-list",
      content: sources.map((source) => (
        <label className="source-option prism-source-option" key={source.external_id}>
          <span className="avatar">{initial(source.label)}</span>
          <span className="source-copy">
            <strong>{source.label}</strong>
            <span>{sourceDetail(source)}</span>
          </span>
          <input
            type="checkbox"
            aria-label={source.label}
            checked={selected.has(source.external_id)}
            onChange={(event) => m.togglePolicySource(source.external_id, event.currentTarget.checked)}
          />
        </label>
      )),
    };
  }

  return (
    <div id="prism-policy-dialog" className="scope-panel">
      <p className="panel-note">This is a durable boundary for this Prism. It is enforced before Prism reads a chat or stores activity.</p>
      <fieldset id="prism-policy-mode" className="prism-policy-modes">
        {MODES.map(([value, title, note]) => (
          <label className="template-choice" key={value}>
            <input type="radio" name="prism-policy-mode" value={value} checked={mode === value} onChange={() => m.setPolicyMode(value)} />
            <span>
              <strong>{title}</strong>
              <small>{note}</small>
            </span>
          </label>
        ))}
      </fieldset>
      <div id="prism-policy-selection-wrap" hidden={mode === "all_chats"}>
        <label className="sr-only" htmlFor="prism-policy-search">
          Search Teams chats
        </label>
        <div className="search-field">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6" />
            <path d="m20 20-4-4" />
          </svg>
          <input
            id="prism-policy-search"
            type="search"
            autoComplete="off"
            placeholder="Search chats or participants"
            value={m.policySearch}
            onChange={(event) => m.setPolicySearch(event.currentTarget.value)}
          />
        </div>
        <p id="prism-policy-selection-note" className="panel-note">
          {mode === "include_only" ? "Check each chat this Prism may monitor." : "Check each chat this Prism must never read."}
        </p>
        <div id="prism-policy-source-list" className={list.className}>
          {list.content}
        </div>
      </div>
      <p id="prism-policy-error" className="form-error" role="alert" hidden={!m.policyError}>
        {m.policyError}
      </p>
      <div className="dialog-actions">
        <button id="prism-policy-cancel" className="button secondary" type="button" onClick={() => void m.closePolicy()}>
          Cancel
        </button>
        <button id="prism-policy-save" className="button" type="button" disabled={m.policySave !== "idle"} onClick={() => void m.savePolicy()}>
          {m.policySave === "saving" ? (
            <>
              <span className="spinner" /> Saving…
            </>
          ) : m.policySave === "saved" ? (
            "Saved ✓"
          ) : (
            "Save scope"
          )}
        </button>
      </div>
    </div>
  );
}
