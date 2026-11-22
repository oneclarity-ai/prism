import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { emit } from "@/lib/events";
import { planRequest } from "@/features/computers";
import { ConversationController, hydrateTurn } from "./conversation";
import { codeOf, newTurn } from "./store";
import type { ActionPlan, Evidence, Job, Observation, Proposal, Review, Thread, Turn } from "./types";

export type ApprovalPhase = "approving" | "sending";

interface CreateRequest {
  path: string;
  body: Record<string, unknown>;
}

/** Asking, running and acting on a review: composer submit, job polling and the draft/approval flows. */
export abstract class JobsController extends ConversationController {
  private pollTimers = new Set<ReturnType<typeof setInterval>>();

  /** Stop job polling (the page is going away). */
  stopTimers(): void {
    this.pollTimers.forEach((timer) => clearInterval(timer));
    this.pollTimers.clear();
  }

  private requireThread(): Thread {
    const thread = this.state.activeThread;
    if (!thread) throw new Error("No conversation is open.");
    return thread;
  }

  /* Failures before a job exists (reconnect, permission, throttling) have no turn to live in. */
  private showComposerFailure(error: unknown): void {
    this.set({
      composerFailure: error ? { code: codeOf(error), message: errorMessage(error) } : null,
    });
  }

  private showPendingSubmission(content: string, label = "Getting Prism ready…"): void {
    this.set({ pendingSubmission: { content, label, createdAt: new Date().toISOString() } });
    this.render("bottom");
  }

  private updatePendingSubmission(label: string): void {
    const pending = this.state.pendingSubmission;
    if (!pending) return;
    this.set({ pendingSubmission: { ...pending, label } });
    this.render("bottom");
  }

  private clearPendingSubmission(): void {
    this.set({ pendingSubmission: null });
  }

  async draftFollowUp(job: Job): Promise<void> {
    const destination = job.source_label || "the selected Teams conversation";
    const instruction = await this.getHost().askDialog({
      title: "Draft a follow-up",
      message: `Prism will prepare a Teams draft for ${destination}. Nothing will be sent until you approve it.`,
      confirmLabel: "Create draft",
      field: {
        label: "Follow-up instruction",
        value: `Draft a follow-up message to ${destination} based on this update.`,
        placeholder: "Tell Prism what the follow-up should cover",
      },
    });
    if (typeof instruction !== "string" || !instruction.trim()) return;
    this.set({ composerText: instruction.trim() });
    await this.submitMessage();
  }

  /** Explicit drafting intent: Prism prepares the message for the chat where this was seen. The user still approves. */
  async draftFromUpdate(item: Observation): Promise<void> {
    const destination = item.source_label || "this Teams chat";
    const instruction = await this.getHost().askDialog({
      title: "Prepare a Teams draft",
      message: `Prism will prepare a draft to ${destination}, the chat where this was seen. Nothing is sent until you approve it.`,
      confirmLabel: "Create draft",
      field: {
        label: "What should the message cover?",
        value: "Ask for the current status, who owns it, and the expected resolution time.",
        placeholder: "Tell Prism what the message should cover",
      },
    });
    if (typeof instruction !== "string" || !instruction.trim() || !this.state.activeThread) return;
    this.showPendingSubmission(`Draft a follow-up to ${destination}`);
    try {
      this.updatePendingSubmission("Reading the chat and preparing a draft…");
      await this.createAndRunMessage("", null, {
        path: `/api/v2/prisms/${item.prism_id}/observations/${item.id}/drafts`,
        body: { request_id: crypto.randomUUID(), instruction: instruction.trim() },
      });
    } catch (error) {
      this.clearPendingSubmission();
      this.render("bottom");
      this.fail(error);
    }
  }

  async submitMessage(): Promise<void> {
    this.showComposerFailure(null);
    const content = this.state.composerText.trim();
    if (!content) return;
    this.setComposerBusy(true);
    this.set({ composerText: "" });
    this.showPendingSubmission(content);
    try {
      if (!this.state.activeThread) await this.openThread((await this.createThread()).id);
    } catch (error) {
      this.clearPendingSubmission();
      this.set({ composerText: content });
      this.render();
      this.fail(error);
      this.setComposerBusy(false);
      return;
    }
    try {
      const thread = this.requireThread();
      // A QA tester turns "test example.com" into a plan card; anything else carries on below.
      const prism = this.state.prism;
      if (prism && (await planRequest(prism, thread.id, content))) {
        await this.refreshMessages();
        this.clearPendingSubmission();
        this.render("bottom");
        return;
      }
      // Small talk ("hi", "thanks") never needs Teams, so Prism just answers.
      const chat = await agentApi<{ handled?: boolean }>(`/api/v2/agent/threads/${thread.id}/chat-reply`, {
        method: "POST",
        ...jsonBody({ content }),
      });
      if (chat.handled) {
        await this.refreshMessages();
        this.clearPendingSubmission();
        this.render("bottom");
        return;
      }
      this.updatePendingSubmission(
        this.requireThread().source_external_id ? "Reading the selected Teams chat…" : "Auto-selecting the relevant Teams chats…",
      );
      await this.createAndRunMessage(content, null);
    } catch (error) {
      if (this.state.pendingSubmission) {
        this.clearPendingSubmission();
        this.set({ composerText: content });
        this.render("bottom");
      }
      this.fail(error);
      this.showComposerFailure(error);
    } finally {
      this.setComposerBusy(false);
      this.focus("composer");
    }
  }

  private async createAndRunMessage(content: string, sourceExternalId: string | null, request: CreateRequest | null = null): Promise<void> {
    const thread = this.requireThread();
    const job = await agentApi<Job>(request?.path || `/api/v2/agent/threads/${thread.id}/messages`, {
      method: "POST",
      ...jsonBody(request?.body || { content, source_external_id: sourceExternalId }),
    });
    this.clearPendingSubmission();
    this.set({ composerText: "" });
    const active = this.state.activeThread;
    this.set({
      jobs: [job, ...this.state.jobs],
      currentJob: job,
      turns: new Map(this.state.turns).set(job.id, newTurn(job)),
      ...(active ? { threads: [active, ...this.state.threads.filter((item) => item.id !== active.id)] } : {}),
    });
    await this.refreshMessages();
    this.render("bottom");
    await this.runJob(job.id);
  }

  private async runJob(jobId: string): Promise<void> {
    const threadId = this.state.activeThread?.id;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    const stopPolling = () => {
      if (pollTimer === undefined) return;
      clearInterval(pollTimer);
      this.pollTimers.delete(pollTimer);
    };
    try {
      pollTimer = setInterval(() => {
        agentApi<Job>(`/api/v2/agent/jobs/${jobId}`)
          .then((job) => this.updateTurnJob(job))
          .catch(() => {});
      }, 900);
      this.pollTimers.add(pollTimer);
      const synced = await agentApi<{ evidence: Evidence[] }>(`/api/v2/agent/jobs/${jobId}/evidence/sync`, { method: "POST" });
      this.patchTurn(jobId, (turn) => ({ ...turn, evidence: new Map(synced.evidence.map((item) => [item.id, item])) }));
      const review = await agentApi<Review>(`/api/v2/agent/jobs/${jobId}/review`, { method: "POST" });
      this.patchTurn(jobId, (turn) => ({ ...turn, review }));
      stopPolling();
      if (this.state.activeThread?.id !== threadId) return;
      await Promise.all([this.reloadTurn(jobId), this.refreshMessages()]);
      this.render("bottom");
    } catch (error) {
      stopPolling();
      if (this.state.activeThread?.id === threadId) await this.failTurn(jobId, error);
    } finally {
      stopPolling();
      emit("agent-changed");
    }
  }

  async recoverJob(job: Job): Promise<void> {
    try {
      const recovered = await agentApi<Job>(`/api/v2/agent/jobs/${job.id}/recover`, { method: "POST" });
      this.updateTurnJob(recovered);
      const turn = this.state.turns.get(job.id);
      if (turn) {
        const hydrated = await hydrateTurn(turn);
        this.patchTurn(job.id, (current) => ({ ...current, evidence: hydrated.evidence, review: hydrated.review }));
      }
      await this.refreshMessages();
      this.render();
      emit("agent-changed");
    } catch (error) {
      await this.failTurn(job.id, error);
    }
  }

  async cancelJob(job: Job): Promise<void> {
    try {
      this.updateTurnJob(
        await agentApi<Job>(`/api/v2/agent/jobs/${job.id}/transition`, {
          method: "POST",
          ...jsonBody({ target: "cancelled", expected_version: job.version }),
        }),
      );
    } catch (error) {
      await this.failTurn(job.id, error);
    }
  }

  async retryJob(job: Job, regenerate: boolean): Promise<void> {
    try {
      if (regenerate) {
        await agentApi(`/api/v2/agent/jobs/${job.id}/feedback`, {
          method: "POST",
          ...jsonBody({ event_type: "regeneration_requested", details: {} }),
        });
      }
      const content = regenerate ? `Regenerate the review and proposed reply for this request: ${job.goal}` : job.goal;
      const replacement = await agentApi<Job>(`/api/v2/agent/threads/${job.thread_id}/messages`, {
        method: "POST",
        ...jsonBody({ content }),
      });
      this.set({
        jobs: [replacement, ...this.state.jobs],
        currentJob: replacement,
        turns: new Map(this.state.turns).set(replacement.id, newTurn(replacement)),
      });
      await this.refreshMessages();
      this.render("bottom");
      await this.runJob(replacement.id);
    } catch (error) {
      await this.failTurn(job.id, error);
    }
  }

  async reviseProposal(turn: Turn, proposal: Proposal, body: string): Promise<void> {
    try {
      const revised = await agentApi<Proposal>(`/api/v2/agent/proposals/${proposal.id}/revisions`, {
        method: "POST",
        ...jsonBody({ body, reason: "Edited by manager in Prism workspace" }),
      });
      this.setDraft(proposal.id, null);
      this.patchTurn(turn.job.id, (current) => {
        const review = current.review;
        if (!review) return { ...current, error: null, errorCode: null };
        const next: Review = review.action_plan
          ? {
              ...review,
              action_plan: {
                ...review.action_plan,
                actions: review.action_plan.actions.map((action) => (action.proposal.id === proposal.id ? { ...action, proposal: revised } : action)),
              },
            }
          : { ...review, proposal: revised };
        return { ...current, review: next, error: null, errorCode: null };
      });
      this.render();
      this.setStatus("Edit saved. Review it, then approve to send.");
    } catch (error) {
      await this.failTurn(proposal.job_id, error);
    }
  }

  private async postDecision(proposal: Proposal, decision: "approved" | "rejected", reason?: string): Promise<void> {
    await agentApi(`/api/v2/agent/proposals/${proposal.id}/decision`, {
      method: "POST",
      ...jsonBody({
        decision,
        expected_revision: proposal.revision,
        expected_payload_hash: proposal.payload_hash,
        ...(reason ? { reason } : {}),
      }),
    });
  }

  async rejectDraft(proposal: Proposal): Promise<void> {
    const reason = await this.getHost().askDialog({
      title: "Reject this draft?",
      message: "Nothing will be sent. You can ask Prism to regenerate it.",
      confirmLabel: "Reject",
      danger: true,
      field: { label: "Reason (optional)" },
    });
    if (reason === null || reason === undefined) return;
    try {
      await this.postDecision(proposal, "rejected", String(reason).trim());
      await this.reloadTurn(proposal.job_id);
      emit("agent-changed");
    } catch (error) {
      await this.failTurn(proposal.job_id, error);
    }
  }

  requestActionRedraft(proposal: Proposal): void {
    const destination = proposal.destination.label || "the selected Teams chat";
    this.set({
      composerText: `Redraft only the message to ${destination}. Keep the same purpose, but improve this draft: ${proposal.body}`,
    });
    this.focus("composer");
  }

  async approveActionPlan(turn: Turn): Promise<void> {
    const plan: ActionPlan | null | undefined = turn.review?.action_plan;
    if (!plan) return;
    const pending = plan.actions.filter(({ proposal }) => proposal.state === "pending");
    if (!pending.length || pending.some(({ proposal }) => this.state.drafts.has(proposal.id))) return;
    try {
      const approved = await agentApi<ActionPlan>(`/api/v2/agent/plans/${plan.id}/approve-all`, {
        method: "POST",
        ...jsonBody({
          items: pending.map(({ proposal }) => ({
            proposal_id: proposal.id,
            expected_revision: proposal.revision,
            expected_payload_hash: proposal.payload_hash,
          })),
        }),
      });
      this.patchTurn(turn.job.id, (current) => (current.review ? { ...current, review: { ...current.review, action_plan: approved } } : current));
      this.render();
      const failures: string[] = [];
      for (const { proposal, execution } of [...approved.actions].sort((left, right) => left.proposal.sequence - right.proposal.sequence)) {
        if (proposal.state !== "approved" || execution) continue;
        try {
          await agentApi(`/api/v2/agent/proposals/${proposal.id}/execution`, { method: "POST" });
        } catch (error) {
          failures.push(`${proposal.destination.label || "Teams action"}: ${errorMessage(error)}`);
        }
      }
      await Promise.all([this.reloadTurn(plan.job_id), this.refreshMessages()]);
      emit("agent-changed");
      if (failures.length) this.setStatus(`Some actions need attention: ${failures.join(" ")}`, true);
    } catch (error) {
      await this.failTurn(plan.job_id, error);
    }
  }

  async approveAndSend(proposal: Proposal, onPhase: (phase: ApprovalPhase) => void): Promise<void> {
    onPhase("approving");
    try {
      await this.postDecision(proposal, "approved");
      onPhase("sending");
      await this.executeProposal(proposal);
    } catch (error) {
      await this.failTurn(proposal.job_id, error);
      emit("agent-changed");
    }
  }

  async sendApprovedProposal(proposal: Proposal, onPhase: (phase: ApprovalPhase) => void): Promise<void> {
    onPhase("sending");
    try {
      await this.executeProposal(proposal);
    } catch (error) {
      await this.failTurn(proposal.job_id, error);
      emit("agent-changed");
    }
  }

  private async executeProposal(proposal: Proposal): Promise<void> {
    await agentApi(`/api/v2/agent/proposals/${proposal.id}/execution`, { method: "POST" });
    await Promise.all([this.reloadTurn(proposal.job_id), this.refreshMessages()]);
    emit("agent-changed");
  }
}
