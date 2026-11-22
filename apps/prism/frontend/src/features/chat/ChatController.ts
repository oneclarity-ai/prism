import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { emit } from "@/lib/events";
import { onPrism as onQaPrism, setOpen as setComputerOpen } from "@/features/computers";
import { messagesUrl } from "./conversation";
import { JobsController } from "./jobs";
import { codeOf } from "./store";
import type { ChatPrism, DrawerTab, Message, Preference, SearchView, TeamsSource, Thread } from "./types";

/** The whole Agent workspace behaviour; components only read `state` and call these methods. */
export class ChatController extends JobsController {
  private searchToken = 0;
  private searchTimer: ReturnType<typeof setTimeout> | undefined;
  private sourcesWarmed = 0;
  private legacyStarted = false;

  /* Header side effects of the old renderHeader (the visible header itself is derived from state). */
  protected renderHeader(): void {
    const { prism, preferencesFor } = this.state;
    onQaPrism(prism);
    if ((prism?.id || null) !== preferencesFor) {
      this.set({ preferences: [], preferencesFor: prism?.id || null });
      void this.loadPreferences({ silent: true });
    }
    if (!prism) this.setDrawerTab("preferences");
  }

  refreshHeader(): void {
    this.renderHeader();
  }

  /** Merge an edited Prism (profile save, or another page editing it) into the open one. */
  applyPrismUpdate(updated: ChatPrism): void {
    const prism = this.state.prism;
    if (prism?.id === updated.id) this.set({ prism: { ...prism, ...updated } });
  }

  /* Threads. ---------------------------------------------------------------- */

  openLegacy(): void {
    this.set({ prism: null, activeThread: null });
    void this.loadThreads();
  }

  // v2.2 migrates the original Assistant conversation into the Executive Assistant Prism. Waiting for
  // the feature decision avoids creating a second, empty legacy conversation during page startup.
  startLegacyWorkspace(): void {
    if (this.legacyStarted) return;
    this.legacyStarted = true;
    void this.loadThreads();
  }

  async loadThreads(): Promise<void> {
    if (this.state.prism || this.loadingLegacyThreads) return;
    this.loadingLegacyThreads = true;
    try {
      const requested = new URLSearchParams(location.search).get("thread");
      let conversation = await this.fetchConversation();
      if (requested && requested !== conversation.id) {
        const fallback = conversation;
        conversation = await agentApi<Thread>(`/api/v2/agent/threads/${requested}/resolve`).catch(() => fallback);
      }
      if (this.state.prism) return;
      this.set({ threads: [conversation] });
      if (requested) this.getHost().setActiveTab("agent");
      await this.openThread(conversation.id);
    } catch (error) {
      this.fail(error);
    } finally {
      this.loadingLegacyThreads = false;
    }
  }

  async newChat(): Promise<void> {
    this.getHost().setActiveTab("agent");
    try {
      const thread = this.state.threads[0] || (await this.createThread());
      await this.openThread(thread.id);
      this.focus("composer");
    } catch (error) {
      this.fail(error);
    }
  }

  /* Choosing a Teams chat. -------------------------------------------------- */

  async chooseSource(): Promise<void> {
    try {
      if (!this.state.activeThread) await this.openThread((await this.createThread()).id);
    } catch (error) {
      this.fail(error);
      return;
    }
    this.set({ sourcePicker: { status: "loading", error: "", query: "", choosing: null } });
    this.refs.sourceDialog?.showModal();
    this.refs.sourceSearch?.focus();
    try {
      const result = await agentApi<{ items: TeamsSource[] }>("/api/v2/agent/sources/teams");
      this.set({ sources: result.items, sourcePicker: { ...this.state.sourcePicker, status: "ready" } });
    } catch (error) {
      this.set({ sourcePicker: { ...this.state.sourcePicker, status: "error", error: errorMessage(error) } });
    }
  }

  setSourceQuery(query: string): void {
    this.set({ sourcePicker: { ...this.state.sourcePicker, query } });
  }

  /** Listing chats is slow on the first call; start it as soon as the user reaches for the picker. */
  warmSources(): void {
    if (Date.now() - this.sourcesWarmed < 30000) return;
    this.sourcesWarmed = Date.now();
    agentApi("/api/v2/agent/sources/teams").catch(() => {});
  }

  // Choosing a chat saves it on the server, which can take a few seconds: show it working, and ignore
  // further clicks until it is done.
  private markChoosing(key: string, text: string): () => void {
    this.set({ sourcePicker: { ...this.state.sourcePicker, choosing: { key, text } } });
    return () => this.set({ sourcePicker: { ...this.state.sourcePicker, choosing: null } });
  }

  private applySource(updated: Thread): void {
    this.set({ activeThread: updated, threads: this.state.threads.map((item) => (item.id === updated.id ? updated : item)) });
    this.refs.sourceDialog?.close();
    this.renderHeader();
    if (!this.state.messages.length) this.render();
    this.focus("composer");
  }

  async clearSourceConstraint(): Promise<void> {
    const thread = this.state.activeThread;
    if (!thread) return;
    const done = this.markChoosing("all", "Switching to all chats…");
    try {
      this.applySource(await agentApi<Thread>(`/api/v2/agent/threads/${thread.id}/source/teams`, { method: "DELETE" }));
    } catch (error) {
      this.fail(error);
      done();
    }
  }

  async selectSource(source: TeamsSource): Promise<void> {
    const thread = this.state.activeThread;
    if (!thread) return;
    if (thread.source_external_id && thread.source_external_id !== source.external_id && this.state.jobs.length) {
      const confirmed = await this.getHost().askDialog({
        title: "Change the Teams chat?",
        message: "Future reviews in this Prism conversation will use the new source constraint. Existing reviews keep their original source.",
        confirmLabel: "Change constraint",
      });
      if (confirmed === null) return;
    }
    const done = this.markChoosing(source.external_id, "Selecting this chat…");
    try {
      this.applySource(
        await agentApi<Thread>(`/api/v2/agent/threads/${thread.id}/source/teams`, {
          method: "PUT",
          ...jsonBody({ external_id: source.external_id }),
        }),
      );
    } catch (error) {
      this.fail(error);
      done();
    }
  }

  /* Search: find anything in the one conversation, then view history at that point. */

  setSearchOpen(open: boolean): void {
    this.set({ search: { ...this.state.search, open } });
    if (open) {
      this.focus("search");
      return;
    }
    this.searchToken += 1;
    clearTimeout(this.searchTimer);
    this.set({ search: { open: false, query: "", view: { kind: "idle" } } });
    this.focus("searchButton");
  }

  onSearchInput(query: string): void {
    this.set({ search: { ...this.state.search, query } });
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => void this.runSearch(), 250);
  }

  private async runSearch(): Promise<void> {
    const thread = this.state.activeThread;
    const query = this.state.search.query.trim();
    const token = ++this.searchToken;
    const show = (view: SearchView) => this.set({ search: { ...this.state.search, view } });
    if (!thread || query.length < 2) {
      show(query ? { kind: "short" } : { kind: "idle" });
      return;
    }
    show({ kind: "searching" });
    try {
      const found = await agentApi<Message[]>(messagesUrl(thread.id, { q: query, limit: 20 }));
      if (token !== this.searchToken) return;
      show(found.length ? { kind: "results", query, items: [...found].reverse() } : { kind: "empty", query });
    } catch (error) {
      if (token === this.searchToken) show({ kind: "error", failure: { code: codeOf(error), message: errorMessage(error) } });
    }
  }

  /* Reply preferences and the settings drawer. -------------------------------- */

  setPreferencesOpen(open: boolean): void {
    if (open) setComputerOpen(false);
    const drawer = this.state.drawer;
    this.set({ drawer: { ...drawer, open, openNonce: open ? drawer.openNonce + 1 : drawer.openNonce } });
    if (open) {
      void this.loadPreferences();
      this.setDrawerTab("preferences");
      this.focus("preferenceInput");
    }
  }

  // Settings tabs live in the right drawer. Prism management stays with the Prism list; rows just trigger those actions.
  setDrawerTab(tab: DrawerTab): void {
    const { drawer, prism } = this.state;
    this.set({
      drawer: { ...drawer, tab, archiveConfirm: false, profileNonce: tab === "profile" && prism ? drawer.profileNonce + 1 : drawer.profileNonce },
    });
    if (tab === "scope" && prism) emit("scope-open");
    if (tab === "people" && prism) emit("people-open", { prismId: prism.id, prismName: prism.name });
  }

  setArchiveConfirm(archiveConfirm: boolean): void {
    this.set({ drawer: { ...this.state.drawer, archiveConfirm } });
    if (archiveConfirm) this.focus("archiveYes");
  }

  confirmArchive(): void {
    const prism = this.state.prism;
    if (!prism) return;
    this.setPreferencesOpen(false);
    emit("archive-confirmed", { id: prism.id });
  }

  openMoreSettings(): void {
    const prism = this.state.prism;
    if (!prism) return;
    this.setPreferencesOpen(false);
    this.getHost().setSidebarSection("workspace");
    emit("workspace-navigate", { page: "prism", id: prism.id });
  }

  editOrganization(): void {
    const prism = this.state.prism;
    if (!prism) return;
    this.setPreferencesOpen(false);
    emit("edit-organization", { prism });
  }

  // A Prism's instructions live under that Prism; only the old unscoped assistant uses the global list.
  private preferencesPath(): string {
    const prism = this.state.prism;
    return prism ? `/api/v2/prisms/${prism.id}/preferences` : "/api/v2/agent/preferences";
  }

  async loadPreferences({ silent = false } = {}): Promise<void> {
    const owner = this.state.prism?.id || null;
    try {
      const items = await agentApi<Preference[]>(this.preferencesPath());
      if ((this.state.prism?.id || null) !== owner) return;
      this.set({ preferences: items, preferencesFor: owner });
    } catch (error) {
      if (!silent) this.fail(error);
    }
  }

  async deletePreference(preference: Preference): Promise<void> {
    const confirmed = await this.getHost().askDialog({
      title: "Delete this preference?",
      message: `Prism will stop following "${preference.instruction}". This can't be undone.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await agentApi(`${this.preferencesPath()}/${preference.id}`, { method: "DELETE" });
      await this.loadPreferences();
      this.setStatus("Preference deleted.");
    } catch (error) {
      this.fail(error);
    }
  }

  private async putPreference(preference: Preference, changes: Partial<Pick<Preference, "instruction" | "is_active">>): Promise<void> {
    try {
      await agentApi(`${this.preferencesPath()}/${preference.id}`, {
        method: this.state.prism ? "PATCH" : "PUT",
        ...jsonBody(
          this.state.prism
            ? changes
            : { instruction: preference.instruction, scope: preference.scope, is_active: preference.is_active, ...changes },
        ),
      });
      await this.loadPreferences();
    } catch (error) {
      this.fail(error);
    }
  }

  updatePreference(preference: Preference, isActive: boolean): Promise<void> {
    return this.putPreference(preference, { is_active: isActive });
  }

  async editPreference(preference: Preference): Promise<void> {
    const instruction = await this.getHost().askDialog({
      title: "Edit preference",
      confirmLabel: "Save",
      field: { label: "Instruction", value: preference.instruction },
    });
    if (typeof instruction !== "string" || !instruction.trim() || instruction.trim() === preference.instruction) return;
    await this.putPreference(preference, { instruction: instruction.trim() });
  }

  /** Resolves true when saved, so the form can clear its field. */
  async savePreference(instruction: string): Promise<boolean> {
    const prism = this.state.prism;
    try {
      await agentApi(this.preferencesPath(), {
        method: "POST",
        ...jsonBody(prism ? { instruction: instruction.trim() } : { instruction: instruction.trim(), scope: "general" }),
      });
      this.setStatus(prism ? `Saved. Only ${prism.name} will follow this.` : "Preference saved. Prism will use it in future drafts.");
      await this.loadPreferences();
      return true;
    } catch (error) {
      this.fail(error);
      return false;
    }
  }
}
