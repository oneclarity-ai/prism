import { useChatController, useChatState } from "./ChatContext";
import { formatTime, stampLabel } from "./format";
import { AssistantMessage, PendingTurn, ProgressTurn, UserMessage } from "./Messages";
import { buildTimeline, type TimelineItem } from "./build-timeline";
import { UpdateCard } from "./UpdateCard";
import { Welcome } from "./Welcome";

function Item({ item }: { item: TimelineItem }) {
  const controller = useChatController();
  switch (item.type) {
    case "history-banner":
      return (
        <div className="callout quiet history-banner">
          <span className="callout-icon">↑</span>
          <div className="callout-body">Viewing earlier history.</div>
          <button type="button" className="mini-button" onClick={() => void controller.backToLatest()}>
            Back to latest
          </button>
        </div>
      );
    case "load-earlier":
      return (
        <button type="button" className="button secondary load-earlier" onClick={() => void controller.loadEarlier()}>
          Load earlier messages
        </button>
      );
    case "stamp":
      return (
        <time className="chat-stamp" dateTime={new Date(item.value).toISOString()} title={formatTime(item.value)}>
          {stampLabel(item.value)}
        </time>
      );
    case "update":
      return <UpdateCard item={item.item} />;
    case "separator":
      return (
        <div className="topic-separator" role="separator">
          <span>{item.text}</span>
        </div>
      );
    case "user":
      return <UserMessage message={item.message} />;
    case "progress":
      return <ProgressTurn turn={item.turn} />;
    case "assistant":
      return <AssistantMessage message={item.message} turn={item.turn} />;
    case "pending":
      return <PendingTurn pending={item.pending} />;
  }
}

export function Timeline() {
  const state = useChatState();
  const view = buildTimeline(state);
  return (
    <div id="agent-timeline" className="agent-timeline" aria-live="polite">
      {!state.rendered ? (
        "Ask Prism what needs your attention. You can constrain the request to a Teams chat."
      ) : view.kind === "loading" ? (
        <p className="agent-loading">Loading conversation…</p>
      ) : view.kind === "welcome" ? (
        <Welcome />
      ) : (
        view.items.map((item) => <Item key={item.key} item={item} />)
      )}
    </div>
  );
}
