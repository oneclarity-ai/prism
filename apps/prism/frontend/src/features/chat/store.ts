import type { AppApi } from "@/lib/app-context";
import { ApiError, errorMessage } from "@/lib/api";
import type { ChatState, FocusTarget, Job, ScrollKind, Turn } from "./types";

/** DOM nodes the controller needs for focus and scrolling (callback refs register them). */
export interface ChatRefs {
  composer: HTMLTextAreaElement | null;
  scroller: HTMLDivElement | null;
  sourceDialog: HTMLDialogElement | null;
  sourceSearch: HTMLInputElement | null;
  searchInput: HTMLInputElement | null;
  searchButton: HTMLButtonElement | null;
  preferenceInput: HTMLTextAreaElement | null;
  archiveYes: HTMLButtonElement | null;
  messages: Map<string, HTMLElement>;
}

export const newTurn = (job: Job): Turn => ({ job, review: null, evidence: new Map(), error: null, errorCode: null });

export const codeOf = (error: unknown): string | null => (error instanceof ApiError ? error.code : null);

export function initialState(): ChatState {
  return {
    threads: [],
    activeThread: null,
    messages: [],
    jobs: [],
    turns: new Map(),
    updates: [],
    currentJob: null,
    sources: [],
    preferences: [],
    preferencesFor: null,
    drafts: new Map(),
    loading: false,
    prism: null,
    pendingSubmission: null,
    hasEarlier: false,
    anchor: null,
    composerText: "",
    composerBusy: false,
    composerFailure: null,
    rendered: false,
    focus: { target: "composer", nonce: 0 },
    sourcePicker: { status: "loading", error: "", query: "", choosing: null },
    search: { open: false, query: "", view: { kind: "idle" } },
    drawer: { open: false, tab: "preferences", openNonce: 0, archiveConfirm: false, profileNonce: 0 },
    scroll: { kind: "none", nonce: 0 },
    openDetails: new Set(),
  };
}

/**
 * The old module-level `agentState`, as an external store: the controller mutates it through `set`,
 * React reads it with useSyncExternalStore. Async flows read `this.state` after every await, exactly
 * like the old code read `agentState`, so there are no stale closures.
 */
export abstract class ChatStore {
  state: ChatState = initialState();
  readonly refs: ChatRefs = {
    composer: null,
    scroller: null,
    sourceDialog: null,
    sourceSearch: null,
    searchInput: null,
    searchButton: null,
    preferenceInput: null,
    archiveYes: null,
    messages: new Map(),
  };
  private listeners = new Set<() => void>();
  private scrollNonce = 0;

  constructor(protected readonly getHost: () => AppApi) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): ChatState => this.state;

  protected set(patch: Partial<ChatState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  /** The old `renderStream({ scroll })`: re-render the stream and say how to scroll afterwards. */
  protected render(scroll: ScrollKind = "auto", focusMessage?: string): void {
    this.scrollNonce += 1;
    this.set({ rendered: true, scroll: { kind: scroll, focusMessage, nonce: this.scrollNonce } });
  }

  /** Re-render the stream on behalf of the computers feature (`rerenderChat`). */
  rerender = (options?: { scroll?: ScrollKind }): void => this.render(options?.scroll ?? "auto");

  protected setStatus(message: string | null, isError = false): void {
    this.getHost().setStatus(message, isError);
  }

  /** Toast on behalf of the computers feature. */
  report(message: string | null, isError = false): void {
    this.setStatus(message, isError);
  }

  protected fail(error: unknown): void {
    this.setStatus(errorMessage(error), true);
  }

  focus(target: FocusTarget): void {
    this.set({ focus: { target, nonce: this.state.focus.nonce + 1 } });
  }

  setComposerText(composerText: string): void {
    this.set({ composerText });
  }

  protected setComposerBusy(composerBusy: boolean): void {
    this.set({ composerBusy });
  }

  /** Replace one turn (copy-on-write so React sees the change). */
  protected patchTurn(jobId: string, change: (turn: Turn) => Turn): void {
    const turn = this.state.turns.get(jobId);
    if (!turn) return;
    this.set({ turns: new Map(this.state.turns).set(jobId, change(turn)) });
  }

  setDetailOpen(key: string, open: boolean): void {
    if (this.state.openDetails.has(key) === open) return;
    const openDetails = new Set(this.state.openDetails);
    if (open) openDetails.add(key);
    else openDetails.delete(key);
    this.set({ openDetails });
  }

  /** Unsaved draft text per proposal id; only dirty text is kept. */
  setDraft(proposalId: string, text: string | null): void {
    const current = this.state.drafts.get(proposalId);
    if ((current ?? null) === text) return;
    const drafts = new Map(this.state.drafts);
    if (text === null) drafts.delete(proposalId);
    else drafts.set(proposalId, text);
    this.set({ drafts });
  }
}
