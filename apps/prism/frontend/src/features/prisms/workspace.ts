import { useCallback, useEffect, useRef } from "react";
import { agentApi, ApiError, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { choiceLabel } from "./helpers";
import { usePrismsInternal } from "./internal";
import { useLiveState } from "./live";
import type {
  Agreement,
  AgreementState,
  Conversation,
  ConversationState,
  OnboardingQuestion,
  OnboardingSession,
  OnboardingState,
  Prism,
  TeamsSource,
} from "./types";

export interface PendingMessage {
  prismId: string;
  content: string;
  stage: string;
}

/** What the composer shows for the question on screen; `key` changes whenever a new question is displayed. */
export interface Composer {
  key: string;
  choices: string[];
  text: string;
}

export interface WorkspaceState {
  onboarding: OnboardingState;
  starting: boolean;
  answering: { text: string } | null;
  agreement: AgreementState;
  conversation: ConversationState;
  editingQuestionId: string | null;
  pending: PendingMessage | null;
  selectedSources: TeamsSource[];
  answerError: string;
  sending: boolean;
  composer: Composer;
}

const INITIAL: WorkspaceState = {
  onboarding: null,
  starting: false,
  answering: null,
  agreement: null,
  conversation: null,
  editingQuestionId: null,
  pending: null,
  selectedSources: [],
  answerError: "",
  sending: false,
  composer: { key: "", choices: [], text: "" },
};

const REMEMBER = /^remember\s*:\s*(.+)$/i;

/** The onboarding / private conversation of the selected Prism (old prism-directory.js `state` + loaders). */
export function useWorkspace() {
  const app = useApp();
  // Stable identity: the effects below must not restart because the shell re-created its toast function.
  const appRef = useRef(app);
  appRef.current = app;
  const setStatus = useCallback((message: string | null, isError?: boolean) =>
      isError === undefined ? appRef.current.setStatus(message) : appRef.current.setStatus(message, isError), []);
  const { selectedRef, prismsRef, loadPrisms, replacePrism, monitoring } = usePrismsInternal();
  const { live: monitorLive, loadTeamsMonitoring, loadRunStatus } = monitoring;
  const [state, patch, live] = useLiveState<WorkspaceState>(INITIAL);
  const forceScroll = useRef(false);
  // Only the newest onboarding request may update the screen, so a slow earlier load can't undo a started session.
  const onboardingSeq = useRef(0);

  const current = useCallback((): Prism | undefined => prismsRef.current.find((item) => item.id === selectedRef.current), [prismsRef, selectedRef]);
  const toast = useCallback((error: unknown) => setStatus(errorMessage(error), true), [setStatus]);

  const reset = useCallback(
    () =>
      patch({
        editingQuestionId: null,
        onboarding: null,
        agreement: null,
        conversation: null,
        selectedSources: [],
        answerError: "",
      }),
    [patch],
  );

  const loadAgreement = useCallback(async () => {
    const prismId = selectedRef.current;
    if (!prismId) return;
    patch({ agreement: "loading" });
    try {
      const agreement = await agentApi<Agreement>(`/api/v2/prisms/${prismId}/agreement`);
      if (selectedRef.current === prismId) patch({ agreement });
    } catch (error) {
      if (selectedRef.current === prismId) {
        patch({ agreement: "error" });
        toast(error);
      }
    }
  }, [patch, selectedRef, toast]);

  const loadConversation = useCallback(async () => {
    const prismId = selectedRef.current;
    if (!prismId) return;
    // Keep the visible conversation while refreshing; only the first load shows a placeholder.
    if (!live.current.conversation || live.current.conversation === "error") patch({ conversation: "loading" });
    try {
      const result = await agentApi<Conversation>(`/api/v2/prisms/${prismId}/conversation`);
      if (selectedRef.current === prismId) patch({ conversation: result });
    } catch (error) {
      if (selectedRef.current === prismId) {
        patch({ conversation: "error" });
        toast(error);
      }
    }
    if (selectedRef.current === prismId) {
      if (monitorLive.current.sourcePolicy === null) void loadTeamsMonitoring();
      if (monitorLive.current.triggerPolicy === null) void loadRunStatus();
    }
  }, [patch, live, selectedRef, toast, monitorLive, loadTeamsMonitoring, loadRunStatus]);

  const startOnboarding = useCallback(async () => {
    if (live.current.starting) return;
    const prismId = selectedRef.current;
    onboardingSeq.current += 1;
    try {
      patch({ onboarding: "loading", starting: true });
      const session = await agentApi<OnboardingSession>(`/api/v2/prisms/${prismId}/onboarding/start`, { method: "POST", body: "{}" });
      if (selectedRef.current !== prismId) {
        patch({ starting: false });
        return;
      }
      patch({ starting: false, onboarding: session });
      setStatus("Onboarding started. Your answers are saved after every step.");
    } catch (error) {
      patch({ starting: false, onboarding: "error" });
      toast(error);
    }
  }, [patch, live, selectedRef, setStatus, toast]);

  const loadOnboarding = useCallback(async () => {
    const prismId = selectedRef.current;
    if (!prismId || live.current.starting) return;
    const seq = (onboardingSeq.current += 1);
    patch({ onboarding: "loading" });
    try {
      const session = await agentApi<OnboardingSession>(`/api/v2/prisms/${prismId}/onboarding`);
      if (seq !== onboardingSeq.current || live.current.starting) return;
      patch({ onboarding: session });
      if (session.status === "completed") void loadAgreement();
      if (current()?.state === "active") void loadConversation();
    } catch (error) {
      if (seq !== onboardingSeq.current || live.current.starting) return;
      patch({ onboarding: error instanceof ApiError && error.status === 404 ? "missing" : "error" });
      if (live.current.onboarding === "error") toast(error);
    }
    // A new Prism goes straight into its first conversation; there is no extra "get started" click.
    if (live.current.onboarding === "missing" && String(current()?.state).toLowerCase() === "draft") void startOnboarding();
  }, [patch, live, selectedRef, current, loadAgreement, loadConversation, startOnboarding, toast]);

  const setPendingStage = useCallback(
    (stage: string) => {
      const pending = live.current.pending;
      if (!pending) return;
      forceScroll.current = true;
      patch({ pending: { ...pending, stage } });
    },
    [patch, live],
  );

  const setComposerText = useCallback((text: string) => patch({ composer: { ...live.current.composer, text } }), [patch, live]);
  const setComposerChoices = useCallback((choices: string[]) => patch({ composer: { ...live.current.composer, choices } }), [patch, live]);
  /** Called while rendering: a new question starts from the saved answer instead of the previous typing. */
  const syncComposer = useCallback(
    (key: string, choices: string[], text: string) => {
      if (live.current.composer.key !== key) patch({ composer: { key, choices, text }, answerError: "" });
    },
    [patch, live],
  );

  const sendConversationMessage = useCallback(async () => {
    const prism = current();
    const content = live.current.composer.text.trim();
    if (!prism || !content) return;
    patch({ sending: true });
    try {
      const remembered = content.match(REMEMBER);
      if (remembered) {
        await agentApi(`/api/v2/prisms/${prism.id}/memory`, { method: "POST", ...jsonBody({ instruction: remembered[1] }) });
        setComposerText("");
        setStatus(`Saved to ${prism.name}’s private memory.`);
        await loadConversation();
        return;
      }
      const selectedExternalIds = live.current.selectedSources.map((source) => source.external_id);
      forceScroll.current = true;
      patch({ pending: { prismId: prism.id, content, stage: "Sending your message…" }, sending: false });
      setComposerText("");
      const job = await agentApi<{ id: string }>(`/api/v2/prisms/${prism.id}/conversation/messages`, {
        method: "POST",
        ...jsonBody({ content, source_external_ids: selectedExternalIds }),
      });
      patch({ selectedSources: [] });
      setPendingStage(selectedExternalIds.length ? "Searching the selected Teams chats…" : "Searching your Teams chats for relevant messages…");
      await agentApi(`/api/v2/agent/jobs/${job.id}/evidence/sync`, { method: "POST" });
      setPendingStage("Reading what it found and preparing a response…");
      await agentApi(`/api/v2/agent/jobs/${job.id}/review`, { method: "POST" });
      patch({ pending: null });
      await loadConversation();
    } catch (error) {
      toast(error);
      const pending = live.current.pending;
      if (pending && !live.current.composer.text) setComposerText(pending.content);
      patch({ pending: null });
      await loadConversation();
    } finally {
      patch({ sending: false });
    }
  }, [patch, live, current, setComposerText, setStatus, toast, loadConversation, setPendingStage]);

  const confirmAgreement = useCallback(async () => {
    const prism = current();
    const agreement = live.current.agreement;
    if (!prism || !agreement || typeof agreement !== "object") return;
    try {
      const result = await agentApi<{ agreement: Agreement; prism: Prism; skills_created?: number; skills_error?: string | null }>(
        `/api/v2/prisms/${prism.id}/agreement/confirm`,
        {
          method: "POST",
          ...jsonBody({ expected_agreement_revision: agreement.revision, expected_lifecycle_version: prism.lifecycle_version }),
        },
      );
      patch({ agreement: result.agreement });
      replacePrism(result.prism);
      setStatus(
        result.skills_error ||
          (result.skills_created
            ? `${result.skills_created} skills created from onboarding. Edit them in this Prism’s settings → Skills.`
            : `${result.prism.name} is active.`),
        Boolean(result.skills_error),
      );
      await loadConversation();
    } catch (error) {
      toast(error);
      await loadPrisms();
      await loadAgreement();
    }
  }, [patch, live, current, replacePrism, setStatus, toast, loadConversation, loadPrisms, loadAgreement]);

  const submitAnswer = useCallback(
    async (question: OnboardingQuestion, session: OnboardingSession, skipped = false) => {
      const { composer } = live.current;
      // Chosen values in the order the choices are listed (the old code read the checked inputs in DOM order).
      const selectedValues = question.choices.map((choice) => choice.value).filter((value) => composer.choices.includes(value));
      const customText = composer.text;
      patch({ answerError: "" });
      const text = skipped ? "Skip for now" : customText.trim() || selectedValues.map((value) => choiceLabel(question, value)).join(", ") || "Skip for now";
      forceScroll.current = true;
      patch({ answering: { text } });
      const beat = new Promise((resolve) => setTimeout(resolve, 700));
      try {
        const next = await agentApi<OnboardingSession>(`/api/v2/prisms/${selectedRef.current}/onboarding/questions/${question.id}/answer`, {
          method: "POST",
          ...jsonBody({
            expected_revision: session.revision,
            selected_values: skipped ? [] : selectedValues,
            custom_text: skipped ? null : customText,
            skipped,
          }),
        });
        patch({ onboarding: next, editingQuestionId: null });
        await beat;
        patch({ answering: null });
        if (next.status === "completed") void loadAgreement();
        await loadPrisms();
      } catch (error) {
        patch({ answering: null, answerError: errorMessage(error) });
      } finally {
        patch({ answering: null });
      }
    },
    [patch, live, selectedRef, loadAgreement, loadPrisms],
  );

  const setEditingQuestion = useCallback((id: string | null) => patch({ editingQuestionId: id }), [patch]);
  const setSelectedSources = useCallback((selectedSources: TeamsSource[]) => patch({ selectedSources }), [patch]);

  /** True once after a message was sent or an answer submitted: the stream jumps to the bottom even if scrolled up. */
  const consumeScroll = useCallback(() => {
    const force = forceScroll.current;
    forceScroll.current = false;
    return force;
  }, []);

  return {
    state,
    live,
    current,
    reset,
    loadOnboarding,
    loadConversation,
    startOnboarding,
    sendConversationMessage,
    confirmAgreement,
    submitAnswer,
    setEditingQuestion,
    setSelectedSources,
    setComposerText,
    setComposerChoices,
    syncComposer,
    consumeScroll,
  };
}

export type Workspace = ReturnType<typeof useWorkspace>;

/** Effects that tie the workspace to the directory's selection and list loads. */
export function useWorkspaceLifecycle(ws: Workspace): void {
  const { selectedId, selectionNonce, loadTick, prismsRef, selectedRef } = usePrismsInternal();
  const { reset, loadOnboarding, live } = ws;

  // Selecting a Prism (even the one already open) starts its conversation over.
  useEffect(() => {
    reset();
    if (selectedId && prismsRef.current.some((item) => item.id === selectedId)) void loadOnboarding();
  }, [selectedId, selectionNonce, reset, loadOnboarding, prismsRef]);

  // A refresh restores the selected Prism id from localStorage: load its conversation once the list is in.
  const seenTick = useRef(loadTick);
  useEffect(() => {
    if (seenTick.current === loadTick) return;
    seenTick.current = loadTick;
    const id = selectedRef.current;
    const onboarding = live.current.onboarding;
    if (id && prismsRef.current.some((item) => item.id === id) && (onboarding === null || onboarding === "missing")) void loadOnboarding();
  }, [loadTick, loadOnboarding, live, prismsRef, selectedRef]);
}
