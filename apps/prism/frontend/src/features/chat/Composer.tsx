import { useLayoutEffect, type FormEvent, type KeyboardEvent } from "react";
import { usePref } from "@/lib/prefs";
import { useChatController, useChatState } from "./ChatContext";
import { autoGrow } from "./DraftCard";
import { Failure } from "./parts";

export function Composer({ jumpHidden, onJump }: { jumpHidden: boolean; onJump: () => void }) {
  const controller = useChatController();
  const { composerText, composerBusy, composerFailure, prism, activeThread } = useChatState();
  const enterNewline = usePref("enter-newline") === "1";
  const label = activeThread?.source_label;

  useLayoutEffect(() => {
    if (controller.refs.composer) autoGrow(controller.refs.composer, 200);
  }, [composerText, controller]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void controller.submitMessage();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
    // "Use Enter to add a new line" (Preferences) makes Cmd/Ctrl+Enter the send shortcut.
    const send = enterNewline ? event.metaKey || event.ctrlKey : !event.shiftKey;
    if (!send) return;
    event.preventDefault();
    if (composerText.trim()) void controller.submitMessage();
  };

  return (
    <div className="agent-dock">
      <div id="agent-composer-notice" className="agent-composer-notice" aria-live="assertive">
        {composerFailure ? <Failure {...composerFailure} /> : null}
      </div>
      <button
        id="agent-jump-latest"
        className="jump-latest"
        type="button"
        aria-label="Jump to latest message"
        title="Jump to latest"
        hidden={jumpHidden}
        onClick={onJump}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 5v14M5 12l7 7 7-7" />
        </svg>
      </button>
      <form id="agent-composer" className="agent-composer pill" onSubmit={submit}>
        <label className="sr-only" htmlFor="agent-message-input">
          Message Prism
        </label>
        <textarea
          id="agent-message-input"
          ref={(node) => {
            controller.refs.composer = node;
          }}
          rows={1}
          maxLength={4000}
          placeholder={`Message ${prism?.name || "Prism"}`}
          required
          disabled={composerBusy}
          value={composerText}
          onChange={(event) => controller.setComposerText(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          id="agent-source-chip"
          className={`source-chip${label ? "" : " empty"}`}
          type="button"
          disabled={composerBusy}
          title={
            label
              ? "Requests are limited to this chat. Choose All chats to let Prism pick and disclose sources."
              : "All chats: Prism picks the relevant Teams chats and shows what it read. Choose one to limit requests."
          }
          onClick={() => void controller.chooseSource()}
          onPointerEnter={() => controller.warmSources()}
          onFocus={() => controller.warmSources()}
        >
          <svg className="chip-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 5h11v8H9l-5 4V5ZM18 9h2v9l-4-3h-4" />
          </svg>
          <span id="agent-source-chip-label">{label || "All chats"}</span>
        </button>
        <button id="agent-send-button" className="send-button" type="submit" aria-label="Ask Prism" title="Ask Prism" disabled={composerBusy || !composerText.trim()}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      </form>
    </div>
  );
}
