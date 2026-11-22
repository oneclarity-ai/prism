import { useEffect, useRef } from "react";

/**
 * Cross-feature notifications that replace the old `document` CustomEvents (`prism:*`).
 * Shared *state* lives in contexts; the bus is only for one-shot commands and refresh nudges.
 */
export interface BusEvents {
  /** A feature changed the Prism list (create, archive, rename...): reload it. */
  "prisms-changed": void;
  /** A single Prism was edited in place. */
  "prism-updated": { prism: PrismLike };
  /** Open the Prism chat for this Prism (switches to the chat tab). */
  "open-agent": { prism: PrismLike };
  /** URL layer resolved /prisms/<key>: select that Prism (add it to the list, include archived) and open its chat. */
  "open-prism-route": { prism: PrismLike };
  /** Open a Prism's chat by id (sidebar/updates/command palette). */
  "open-prism": { id: string };
  /** Open a Prism chat and jump to a search hit. */
  "search-result": { prismId: string; message?: { id: string; created_at?: string | null } | null };
  /** Open the legacy single-assistant (v2.1) workspace. */
  "open-legacy-agent": void;
  /** Start a fresh chat in the current Prism. */
  "new-chat": void;
  /** An agent/Prism chat changed state: refresh the foundation counters. */
  "agent-changed": void;
  /** Refresh the Teams updates badge/list. */
  "updates-refresh": void;
  /** The updates summaries map changed (id -> summary). */
  updates: { summaries: Map<string, unknown> };
  /** Navigate the operations workspace. */
  "workspace-navigate": { page: string; id?: string; section?: string; runId?: string };
  /** Computer panel: focus a run, or show the panel. */
  "focus-computer-run": { runId: string };
  "show-computer": void;
  "computer-opened": void;
  /** Prism settings drawer helpers owned by the Prism chat. */
  "scope-open": void;
  "people-open": { prismId: string; prismName: string };
  "edit-organization": { prism: PrismLike };
  "archive-confirmed": { id: string };
  "skills-changed": void;
  "no-prism-selected": void;
  /** Start the create-Prism flow (command palette, empty states). */
  "create-prism": void;
  /** Open the global search palette (Ctrl/Cmd+K). */
  "open-search": void;
  "open-agent-message": { prism?: PrismLike; message?: unknown } & Record<string, unknown>;
}

/** Minimal shape every feature may rely on; feature code narrows with the generated API types. */
export interface PrismLike {
  id: string;
  name: string;
  code?: string | null;
  [key: string]: unknown;
}

type Handler<K extends keyof BusEvents> = (detail: BusEvents[K]) => void;
const handlers = new Map<keyof BusEvents, Set<Handler<keyof BusEvents>>>();

export function emit<K extends keyof BusEvents>(name: K, ...detail: BusEvents[K] extends void ? [] : [BusEvents[K]]): void {
  handlers.get(name)?.forEach((handler) => (handler as (value: unknown) => void)(detail[0]));
}

export function on<K extends keyof BusEvents>(name: K, handler: Handler<K>): () => void {
  const set = handlers.get(name) ?? new Set();
  set.add(handler as Handler<keyof BusEvents>);
  handlers.set(name, set);
  return () => set.delete(handler as Handler<keyof BusEvents>);
}

/** Subscribe for the component's lifetime; always calls the latest handler. */
export function useBusEvent<K extends keyof BusEvents>(name: K, handler: Handler<K>): void {
  const latest = useRef(handler);
  latest.current = handler;
  useEffect(() => on(name, (detail) => latest.current(detail)), [name]);
}
