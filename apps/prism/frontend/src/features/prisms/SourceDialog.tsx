import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { errorMessage } from "@/lib/api";
import { initial, matchesSource, policyAllowsSource, sourceDetail } from "./helpers";
import type { MonitoringApi } from "./monitoring";
import type { TeamsSource } from "./types";

export interface SourceDialogHandle {
  open: () => void;
}

interface Props {
  ref?: Ref<SourceDialogHandle>;
  monitoring: MonitoringApi;
  selected: TeamsSource[];
  onSelect: (sources: TeamsSource[]) => void;
}

const MAX_SOURCES = 5;

/** `#prism-source-dialog`: pick up to five Teams chats for the next request. */
export function SourceDialog({ ref, monitoring, selected, onSelect }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<TeamsSource[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [listState, setListState] = useState<{ kind: "loading" } | { kind: "failed"; message: string } | { kind: "ready" }>({ kind: "ready" });
  const { catalog, sourcePolicy } = monitoring;

  useImperativeHandle(ref, () => ({
    open() {
      setSearch("");
      setPending([...selected]);
      setError("");
      dialogRef.current?.showModal();
      searchRef.current?.focus();
      if (monitoring.live.current.catalog.length) {
        setListState({ kind: "ready" });
        return;
      }
      setListState({ kind: "loading" });
      monitoring.loadCatalog().then(
        () => setListState({ kind: "ready" }),
        (failure: unknown) => setListState({ kind: "failed", message: errorMessage(failure) }),
      );
    },
  }));

  const close = () => dialogRef.current?.close();
  const sources = catalog.filter((source) => policyAllowsSource(sourcePolicy, source) && matchesSource(source, search));
  const chosen = new Set(pending.map((source) => source.external_id));

  const toggle = (source: TeamsSource, checked: boolean) => {
    const current = new Map(pending.map((item) => [item.external_id, item]));
    if (checked) {
      if (current.size >= MAX_SOURCES) {
        setError("Select up to five Teams chats for one request.");
        return;
      }
      current.set(source.external_id, source);
    } else current.delete(source.external_id);
    setPending([...current.values()]);
    setError("");
  };

  let list;
  if (listState.kind === "loading") list = { className: "agent-source-list empty-state", content: "Loading Teams chats…" };
  else if (listState.kind === "failed") list = { className: "agent-source-list empty-state", content: listState.message };
  else if (!sources.length) list = { className: "agent-source-list empty-state", content: "No Teams chats are allowed by this Prism’s monitoring scope." };
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
          <input type="checkbox" aria-label={source.label} checked={chosen.has(source.external_id)} onChange={(event) => toggle(source, event.currentTarget.checked)} />
        </label>
      )),
    };
  }

  return (
    <dialog id="prism-source-dialog" className="picker" ref={dialogRef} onClose={() => setPending([])}>
      <div className="agent-source-dialog-form">
        <div>
          <h2>Select Teams chats</h2>
          <p className="panel-note">Prism will read only the chats selected here for your next request. Select up to five chats.</p>
        </div>
        <label className="sr-only" htmlFor="prism-source-search">
          Search Teams chats
        </label>
        <div className="search-field">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6" />
            <path d="m20 20-4-4" />
          </svg>
          <input
            id="prism-source-search"
            ref={searchRef}
            type="search"
            autoComplete="off"
            placeholder="Search chats or participants"
            value={search}
            onChange={(event) => setSearch(event.currentTarget.value)}
          />
        </div>
        <div id="prism-source-list" className={list.className}>
          {list.content}
        </div>
        <p id="prism-source-error" className="form-error" role="alert" hidden={!error}>
          {error}
        </p>
        <div className="dialog-actions">
          <button
            id="prism-source-clear"
            className="button ghost push"
            type="button"
            onClick={() => {
              onSelect([]);
              close();
            }}
          >
            Use auto-select
          </button>
          <button id="prism-source-cancel" className="button secondary" type="button" onClick={close}>
            Cancel
          </button>
          <button
            id="prism-source-done"
            className="button"
            type="button"
            onClick={() => {
              onSelect([...pending]);
              close();
            }}
          >
            {pending.length ? `Use ${pending.length} ${pending.length === 1 ? "chat" : "chats"}` : "Done"}
          </button>
        </div>
      </div>
    </dialog>
  );
}
