import { useEffect, useRef, useState } from "react";
import { ComputerPanel, focusRun, initQa, setOpen as setComputerOpen, useComputerOpen } from "@/features/computers";
import { useApp, type AppApi } from "@/lib/app-context";
import { useBusEvent } from "@/lib/events";
import { ChatContext, useChatState } from "./ChatContext";
import { ChatController } from "./ChatController";
import { ChatHeader } from "./ChatHeader";
import { ChatScroller } from "./ChatScroller";
import { PreferencesDrawer } from "./PreferencesDrawer";
import { SourceDialog } from "./SourceDialog";
import type { ChatPrism, FocusTarget, Message } from "./types";

interface UpdateSummary {
  unread?: number;
}

/** Everything the Agent workspace does that is not rendering: bus events, tab/mode reactions, global keys. */
function useChatWiring(controller: ChatController, app: AppApi) {
  const { activeTab, modes } = app;

  useEffect(() => {
    initQa({
      refreshMessages: () => controller.refreshMessages(),
      rerenderChat: (options) => controller.rerender(options),
      setStatus: (message, isError) => controller.report(message, isError),
    });
    void controller.loadPreferences({ silent: true });
    return () => controller.stopTimers();
  }, [controller]);

  // With v2.2 on, the page always shows a Prism's own thread; without it the original conversation loads.
  useEffect(() => {
    if (modes.v22 === false) controller.startLegacyWorkspace();
  }, [controller, modes.v22]);

  // Reopening the chat tab picks up (and marks read) new updates.
  useEffect(() => {
    if (activeTab === "agent") void controller.loadUpdates();
  }, [controller, activeTab]);

  useBusEvent("open-agent", ({ prism }) => void controller.openPrism(prism as ChatPrism));
  useBusEvent("open-legacy-agent", () => controller.openLegacy());
  useBusEvent("open-agent-message", async (detail) => {
    const { prism, message } = detail || {};
    if (!prism || !message) return;
    await controller.openPrism(prism as ChatPrism);
    const state = controller.state;
    if (state.prism?.id === prism.id && state.activeThread && !state.loading) {
      await controller.viewHistoryAt(message as Pick<Message, "id" | "created_at">);
    }
  });
  useBusEvent("new-chat", () => void controller.newChat());
  useBusEvent("no-prism-selected", () => controller.startLegacyWorkspace());
  useBusEvent("prism-updated", ({ prism }) => controller.applyPrismUpdate(prism as ChatPrism));
  // New unread updates for the open Prism arrive through the shared poller.
  useBusEvent("updates", ({ summaries }) => {
    const prism = controller.state.prism;
    const current = prism ? (summaries.get(prism.id) as UpdateSummary | undefined) : undefined;
    if (current?.unread) void controller.loadUpdates();
  });
  useBusEvent("show-computer", () => setComputerOpen(true));
  useBusEvent("focus-computer-run", ({ runId }) => void focusRun(runId));
  useBusEvent("computer-opened", () => controller.setPreferencesOpen(false));

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest("[data-agent-new]")) void controller.newChat();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && controller.state.drawer.open && !document.querySelector("dialog[open]")) {
        controller.setPreferencesOpen(false);
      }
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [controller]);
}

/** Moves focus after React has committed, so a just-enabled or just-shown element can take it. */
function useFocusRequests(controller: ChatController, nonce: number, target: FocusTarget) {
  useEffect(() => {
    if (!nonce) return;
    const nodes = {
      composer: controller.refs.composer,
      search: controller.refs.searchInput,
      searchButton: controller.refs.searchButton,
      preferenceInput: controller.refs.preferenceInput,
      archiveYes: controller.refs.archiveYes,
    } as const;
    nodes[target]?.focus();
  }, [controller, nonce, target]);
}

function ChatBody({ controller }: { controller: ChatController }) {
  const { drawer, focus } = useChatState();
  const computerOpen = useComputerOpen();
  useFocusRequests(controller, focus.nonce, focus.target);

  const classes = ["agent-chat", drawer.open ? "drawer-open" : "", computerOpen ? "computer-open" : ""].filter(Boolean).join(" ");
  return (
    <>
      <div className={classes} id="agent-chat">
        <ChatHeader />
        <ChatScroller />
        <ComputerPanel />
        <PreferencesDrawer />
      </div>
      <SourceDialog />
    </>
  );
}

/** Inner content of `<section class="view tab-panel agent-workspace" data-tab="agent">` (the shell renders the wrapper). */
export function AgentPage() {
  const app = useApp();
  const hostRef = useRef(app);
  hostRef.current = app;
  const [controller] = useState(() => new ChatController(() => hostRef.current));
  useChatWiring(controller, app);
  return (
    <ChatContext.Provider value={controller}>
      <ChatBody controller={controller} />
    </ChatContext.Provider>
  );
}
