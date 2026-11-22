import { PrismLogo } from "@/components/ui";
import { ComputerButton } from "@/features/computers";
import { useApp } from "@/lib/app-context";
import { useChatController, useChatState } from "./ChatContext";
import { formatTime, snippetFor, threadParticipants } from "./format";
import { Failure } from "./parts";

function SearchPanel() {
  const controller = useChatController();
  const { search } = useChatState();
  const { view } = search;
  return (
    <div id="agent-search-panel" className="agent-search" hidden={!search.open}>
      <label className="sr-only" htmlFor="agent-search-input">
        Search your conversation with Prism
      </label>
      <input
        id="agent-search-input"
        ref={(node) => {
          controller.refs.searchInput = node;
        }}
        type="search"
        autoComplete="off"
        maxLength={200}
        placeholder="Search your conversation with Prism"
        value={search.query}
        onChange={(event) => controller.onSearchInput(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") controller.setSearchOpen(false);
        }}
      />
      <div id="agent-search-results" className="agent-search-results" aria-live="polite">
        {view.kind === "short" ? <p className="panel-note">Type at least 2 characters.</p> : null}
        {view.kind === "searching" ? <p className="panel-note">Searching…</p> : null}
        {view.kind === "empty" ? <p className="panel-note">{`No messages match “${view.query}”.`}</p> : null}
        {view.kind === "error" ? <Failure {...view.failure} /> : null}
        {view.kind === "results" ? (
          <ul className="search-result-list">
            {view.items.map((message) => (
              <li key={message.id}>
                <button type="button" className="search-result" onClick={() => void controller.viewHistoryAt(message)}>
                  <strong>{message.role === "manager" ? "You" : "Prism"}</strong>
                  <time>{formatTime(message.created_at)}</time>
                  <span>{snippetFor(message.content, view.query)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

export function ChatHeader() {
  const controller = useChatController();
  const app = useApp();
  const { prism, activeThread, search, drawer, preferences } = useChatState();
  const label = activeThread?.source_label;
  const participants = threadParticipants(activeThread);
  const activePreferences = preferences.filter((preference) => preference.is_active).length;
  const sourceLabel = !activeThread
    ? ""
    : label
      ? participants.length
        ? `Source constraint · ${participants.slice(0, 4).join(", ")}${participants.length > 4 ? ` +${participants.length - 4}` : ""}`
        : `Source constraint · ${label}`
      : "";

  return (
    <header className="agent-bar">
      <button className="icon-button chat-sidebar-open" type="button" aria-label="Open sidebar" data-tooltip="Open sidebar" onClick={app.openSidebar}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <div className="agent-bar-title">
        <span id="agent-thread-logo" className="header-logo" aria-hidden="true" hidden={!prism}>
          {prism ? <PrismLogo prism={prism} className="prism-logo" /> : null}
        </span>
        <strong id="agent-thread-title">{prism?.name || "Prism"}</strong>
        <code id="agent-thread-code" className="prism-code" aria-label="Prism code" hidden={!prism?.code}>
          {prism?.code || ""}
        </code>
        <span id="agent-source-label" className="agent-bar-sub">
          {sourceLabel}
        </span>
      </div>
      <div className="agent-bar-actions">
        <SearchPanel />
        <ComputerButton />
        <button
          id="agent-search-button"
          ref={(node) => {
            controller.refs.searchButton = node;
          }}
          className={`icon-button${search.open ? " active" : ""}`}
          type="button"
          aria-expanded={search.open}
          aria-controls="agent-search-panel"
          aria-label="Search"
          data-tooltip="Search"
          onClick={() => controller.setSearchOpen(!search.open)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6" />
            <path d="m20 20-4-4" />
          </svg>
        </button>
        <button
          id="agent-preferences-button"
          className={`icon-button${drawer.open ? " active" : ""}`}
          type="button"
          aria-expanded={drawer.open}
          aria-controls="agent-preferences-panel"
          aria-label="Preferences and settings"
          data-tooltip="Preferences"
          onClick={() => controller.setPreferencesOpen(!drawer.open)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 7h8M16 7h4M4 17h4M12 17h8" />
            <circle cx="14" cy="7" r="2" />
            <circle cx="10" cy="17" r="2" />
          </svg>
          <span id="agent-preferences-count" className="icon-badge" hidden={!activePreferences}>
            {activePreferences}
          </span>
        </button>
      </div>
    </header>
  );
}
