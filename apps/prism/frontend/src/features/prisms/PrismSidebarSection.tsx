import { useApp } from "@/lib/app-context";
import { PrismLogo } from "@/components/ui";
import { isArchived, sidebarTime, stateLabel } from "./helpers";
import { usePrismsInternal } from "./internal";
import type { Prism } from "./types";

function PrismNavItem({ prism }: { prism: Prism }) {
  const app = useApp();
  const { selectedId, summaries, openPrismView } = usePrismsInternal();
  const selected = prism.id === selectedId;
  const unread = summaries.get(prism.id);
  const unreadTitle = unread?.unread
    ? `${unread.unread} unread update${unread.unread === 1 ? "" : "s"}${unread.urgent_unread ? `, ${unread.urgent_unread} urgent` : ""}`
    : "";
  const preview = prism.last_message_preview
    ? `${prism.last_message_role === "manager" ? "You: " : ""}${prism.last_message_preview}`
    : "No messages yet";
  return (
    <button
      type="button"
      className={`nav-item prism-nav-item${selected ? " selected" : ""}`}
      title={prism.description}
      aria-current={selected ? "page" : "false"}
      aria-label={unread?.unread ? `${prism.name}, ${unreadTitle}` : undefined}
      onClick={() => {
        openPrismView(prism);
        app.closeSidebarIfNarrow();
      }}
    >
      <PrismLogo prism={prism} className="prism-logo nav-logo" />
      <span className="prism-nav-text">
        <span className="prism-nav-top">
          <span className="nav-text prism-nav-name">{prism.name}</span>
          {prism.last_message_at ? <time className="prism-nav-time">{sidebarTime(prism.last_message_at)}</time> : null}
        </span>
        <span className="prism-nav-bottom">
          <span className="nav-text prism-nav-preview">{preview}</span>
          {prism.state === "draft" || isArchived(prism) ? <span className="nav-count">{stateLabel(prism)}</span> : null}
          {unread?.unread ? (
            <span className={`nav-count ${unread.urgent_unread ? "urgent" : "approval"}`} title={unreadTitle}>
              {String(unread.unread)}
            </span>
          ) : null}
        </span>
      </span>
    </button>
  );
}

/** `.sidebar-section-head` (title + archived toggle) and the Prism list `#prism-directory-list`. */
export function PrismSidebarSection() {
  const { modes } = useApp();
  const { prisms, loading, archivedPressed, toggleArchived } = usePrismsInternal();
  const hidden = modes.v22 !== true;
  return (
    <>
      <div className="sidebar-section-head" data-v22-only="" hidden={hidden}>
        <span>Prisms</span>
        <button
          id="prism-archived-button"
          className="icon-button small"
          type="button"
          aria-pressed={archivedPressed}
          aria-label="Show archived Prisms"
          data-tooltip={archivedPressed ? "Hide archived" : "Show archived"}
          data-v22-only=""
          hidden={hidden}
          onClick={toggleArchived}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 5h16v4H4zM6 9v10h12V9M10 13h4" />
          </svg>
        </button>
      </div>
      <div id="prism-directory-list" className="prism-nav-list" data-v22-only="" hidden={hidden} aria-live="polite">
        {loading && !prisms.length ? (
          <p className="prism-nav-empty">Loading…</p>
        ) : !prisms.length ? (
          <p className="prism-nav-empty">No Prisms yet.</p>
        ) : (
          prisms.map((prism) => <PrismNavItem key={prism.id} prism={prism} />)
        )}
      </div>
    </>
  );
}
