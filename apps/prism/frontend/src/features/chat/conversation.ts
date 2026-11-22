import { agentApi, errorMessage } from "@/lib/api";
import { emit } from "@/lib/events";
import { PAGE_SIZE } from "./format";
import { ChatStore, codeOf, newTurn } from "./store";
import type {
  ChatPrism,
  Evidence,
  Job,
  Message,
  Observation,
  ObservationPage,
  Review,
  Thread,
  Turn,
} from "./types";

export const messagesUrl = (threadId: string, params: Record<string, string | number> = {}): string => {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  Object.entries(params).forEach(([key, value]) => query.set(key, String(value)));
  return `/api/v2/agent/threads/${threadId}/messages?${query}`;
};

/** Evidence and the review are both optional: a queued or failed job may not have either yet. */
export async function hydrateTurn(turn: Turn): Promise<Turn> {
  const [evidence, review] = await Promise.allSettled([
    agentApi<Evidence[]>(`/api/v2/agent/jobs/${turn.job.id}/evidence`),
    agentApi<Review>(`/api/v2/agent/jobs/${turn.job.id}/review`),
  ]);
  return {
    ...turn,
    evidence: evidence.status === "fulfilled" ? new Map(evidence.value.map((item) => [item.id, item])) : turn.evidence,
    review: review.status === "fulfilled" ? review.value : turn.review,
  };
}

/** Threads, messages, turns and proactive updates: everything that loads the conversation. */
export abstract class ConversationController extends ChatStore {
  protected openPromise: Promise<void> | null = null;
  protected openToken = 0;
  protected loadingLegacyThreads = false;

  protected abstract renderHeader(): void;
  abstract setSearchOpen(open: boolean): void;

  /* The legacy page shows one global conversation; inside a Prism it shows that Prism's own canonical
     thread. Everything after loading is thread-id based. */
  protected async fetchConversation(): Promise<Thread> {
    const prism = this.state.prism;
    if (!prism) return agentApi<Thread>("/api/v2/agent/conversation");
    return (await agentApi<{ thread: Thread }>(`/api/v2/prisms/${prism.id}/conversation`)).thread;
  }

  async openPrism(prism: ChatPrism): Promise<void> {
    const current = this.state;
    if (current.prism?.id === prism.id && (current.activeThread || current.loading)) {
      this.set({ prism });
      this.renderHeader();
      if (this.openPromise) await this.openPromise;
      return;
    }
    this.set({
      prism,
      threads: [],
      activeThread: null,
      messages: [],
      jobs: [],
      turns: new Map(),
      currentJob: null,
      updates: [],
      loading: true,
    });
    this.renderHeader();
    this.render();
    const opening = (async () => {
      try {
        const thread = await this.fetchConversation();
        if (this.state.prism?.id !== prism.id) return;
        this.set({ threads: [thread] });
        await this.openThread(thread.id);
        void this.loadUpdates();
      } catch (error) {
        this.set({ loading: false });
        this.fail(error);
        this.render();
      }
    })();
    this.openPromise = opening;
    await opening;
    if (this.openPromise === opening) this.openPromise = null;
  }

  protected async createThread(): Promise<Thread> {
    const thread = await this.fetchConversation();
    this.set({ threads: [thread] });
    return thread;
  }

  async openThread(threadId: string): Promise<void> {
    const thread = this.state.threads.find((item) => item.id === threadId);
    if (!thread) return;
    const token = ++this.openToken;
    this.set({
      activeThread: thread,
      messages: [],
      jobs: [],
      currentJob: null,
      turns: new Map(),
      loading: true,
      hasEarlier: false,
      anchor: null,
    });
    const url = new URL(location.href);
    url.searchParams.delete("thread");
    history.replaceState(history.state, "", url);
    this.renderHeader();
    this.render();
    try {
      const [messages, jobs] = await Promise.all([
        agentApi<Message[]>(messagesUrl(threadId)),
        agentApi<Job[]>(`/api/v2/agent/threads/${threadId}/jobs`),
      ]);
      if (token !== this.openToken) return;
      const turns = await this.loadTurns(messages, new Map(jobs.map((job) => [job.id, newTurn(job)])));
      if (token !== this.openToken) return;
      this.set({ messages, jobs, currentJob: jobs[0] || null, turns, loading: false, hasEarlier: messages.length >= PAGE_SIZE });
    } catch (error) {
      if (token !== this.openToken) return;
      this.set({ loading: false });
      this.fail(error);
    }
    this.render("bottom");
  }

  /** Older pages can reference jobs beyond the recent-jobs list; load and hydrate those on demand. */
  private async loadTurns(messages: Message[], base: Map<string, Turn>): Promise<Map<string, Turn>> {
    const turns = new Map(base);
    const missing = [...new Set(messages.map((message) => message.job_id).filter((id): id is string => Boolean(id) && !turns.has(id as string)))];
    const loaded = await Promise.all(missing.map((id) => agentApi<Job>(`/api/v2/agent/jobs/${id}`).catch(() => null)));
    loaded.forEach((job) => {
      if (job) turns.set(job.id, newTurn(job));
    });
    const ordered = [...new Set(messages.map((message) => message.job_id).filter((id): id is string => Boolean(id)))]
      .reverse()
      .slice(0, 10);
    const pending = ordered.map((id) => turns.get(id)).filter((turn): turn is Turn => Boolean(turn) && !turn?.review);
    const hydrated = await Promise.all(pending.map(hydrateTurn));
    hydrated.forEach((turn) => turns.set(turn.job.id, turn));
    return turns;
  }

  /** Fold turns loaded in the background into the current ones without overwriting newer changes. */
  private mergeTurns(loaded: Map<string, Turn>): Map<string, Turn> {
    const merged = new Map(this.state.turns);
    loaded.forEach((turn, id) => {
      const current = merged.get(id);
      if (!current) merged.set(id, turn);
      else if (!current.review && turn.review) merged.set(id, { ...current, review: turn.review, evidence: turn.evidence });
    });
    return merged;
  }

  async refreshMessages(): Promise<void> {
    const thread = this.state.activeThread;
    if (!thread) return;
    // Keep already-loaded older pages instead of collapsing back to the newest page.
    const messages = await agentApi<Message[]>(
      messagesUrl(thread.id, { limit: Math.min(Math.max(this.state.messages.length, PAGE_SIZE), 200) }),
    );
    if (this.state.activeThread?.id !== thread.id) return;
    const loaded = await this.loadTurns(messages, this.state.turns);
    this.set({ turns: this.mergeTurns(loaded), messages });
    this.render();
    emit("updates-refresh");
  }

  async loadEarlier(): Promise<void> {
    const thread = this.state.activeThread;
    const oldest = this.state.messages[0];
    if (!thread || !oldest) return;
    try {
      const earlier = await agentApi<Message[]>(messagesUrl(thread.id, { before: oldest.created_at }));
      if (this.state.activeThread?.id !== thread.id) return;
      const loaded = await this.loadTurns(earlier, this.state.turns);
      this.set({
        turns: this.mergeTurns(loaded),
        messages: [...earlier, ...this.state.messages],
        hasEarlier: earlier.length >= PAGE_SIZE,
      });
      this.render("keep");
      this.setStatus(earlier.length ? `Loaded ${earlier.length} earlier messages.` : "No earlier messages.");
    } catch (error) {
      this.fail(error);
    }
  }

  /** Search results jump into history without turning past topics into separate chats. */
  async viewHistoryAt(message: { id: string; created_at?: string | null }): Promise<void> {
    const thread = this.state.activeThread;
    if (!thread) return;
    try {
      const upTo = new Date(new Date(message.created_at ?? "").getTime() + 1).toISOString();
      const messages = await agentApi<Message[]>(messagesUrl(thread.id, { before: upTo }));
      const loaded = await this.loadTurns(messages, this.state.turns);
      this.set({ turns: this.mergeTurns(loaded), messages, anchor: message.id, hasEarlier: messages.length >= PAGE_SIZE });
      this.setSearchOpen(false);
      this.render("bottom", message.id);
    } catch (error) {
      this.fail(error);
    }
  }

  async backToLatest(): Promise<void> {
    this.set({ anchor: null });
    await this.refreshMessages();
    this.render("bottom");
    this.focus("composer");
  }

  async reloadTurn(jobId: string, { clearError = true } = {}): Promise<void> {
    if (!this.state.turns.has(jobId)) return;
    const [job, review] = await Promise.all([
      agentApi<Job>(`/api/v2/agent/jobs/${jobId}`),
      agentApi<Review>(`/api/v2/agent/jobs/${jobId}/review`).catch(() => null),
    ]);
    this.patchTurn(jobId, (turn) => ({
      ...turn,
      job,
      review: review ?? turn.review,
      ...(clearError ? { error: null, errorCode: null } : {}),
    }));
    if (this.state.currentJob?.id === jobId) this.set({ currentJob: job });
    this.render();
  }

  protected async failTurn(jobId: string, error: unknown): Promise<void> {
    await this.reloadTurn(jobId, { clearError: false }).catch(() => {});
    this.patchTurn(jobId, (turn) => ({ ...turn, error: errorMessage(error), errorCode: codeOf(error) }));
    this.fail(error);
    this.render();
  }

  /** A polled job changed: only that turn re-renders (no scroll change). */
  protected updateTurnJob(job: Job): void {
    this.patchTurn(job.id, (turn) => ({ ...turn, job }));
    if (this.state.currentJob?.id === job.id) this.set({ currentJob: job });
  }

  /* Proactive updates: durable observations rendered as first-class turns in this Prism's conversation. */

  async loadUpdates(): Promise<void> {
    const prism = this.state.prism;
    if (!prism) return;
    try {
      const page = await agentApi<ObservationPage>(`/api/v2/prisms/${prism.id}/observations`);
      if (this.state.prism?.id !== prism.id) return;
      const changed = JSON.stringify(page.items) !== JSON.stringify(this.state.updates);
      if (changed) {
        this.set({ updates: page.items });
        this.render();
      }
      this.markUpdatesRead(prism.id, page.items);
    } catch {
      // Updates are additive; a failed fetch must never block the conversation itself.
    }
  }

  private markUpdatesRead(prismId: string, items: Observation[]): void {
    // Only a visible conversation counts as reading.
    if (this.getHost().activeTab !== "agent" || document.visibilityState !== "visible") return;
    const unread = items.filter((item) => !item.read_at).map((item) => item.id);
    if (!unread.length) return;
    agentApi(`/api/v2/prisms/${prismId}/observations/read`, { method: "POST", body: JSON.stringify({ observation_ids: unread }) })
      .then(() => emit("updates-refresh"))
      .catch(() => {});
  }
}
