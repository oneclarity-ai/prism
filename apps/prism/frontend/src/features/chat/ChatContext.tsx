import { createContext, useContext, useSyncExternalStore } from "react";
import type { ChatController } from "./ChatController";
import type { ChatState } from "./types";

export const ChatContext = createContext<ChatController | null>(null);

export function useChatController(): ChatController {
  const controller = useContext(ChatContext);
  if (!controller) throw new Error("Chat components must render inside <AgentPage>");
  return controller;
}

export function useChatState(): ChatState {
  const controller = useChatController();
  return useSyncExternalStore(controller.subscribe, controller.getSnapshot);
}
