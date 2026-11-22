import { useApp } from "@/lib/app-context";
import { WorkspaceNavButton } from "./WorkspaceNavButton";

/** Everything inside `#sidebar-notifications-panel`. */
export function NotificationsSidebarPanel() {
  const { settings, closeSidebarIfNarrow } = useApp();
  return (
    <div className="workspace-navigation">
      <div className="workspace-nav-label">Needs your attention</div>
      <WorkspaceNavButton page="approvals" glyph="shield-check" label="Approvals waiting" approvalBadge />
      <WorkspaceNavButton page="brain" glyph="brain" label="Brain facts to review" approvalBadge badgeLabel="Facts waiting for your approval" />
      <div className="workspace-nav-label">Settings</div>
      <button
        className="nav-item"
        type="button"
        id="sidebar-notify-settings"
        onClick={() => {
          settings.open("notifications");
          closeSidebarIfNarrow();
        }}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7M10 20a2 2 0 0 0 4 0" />
        </svg>
        <span>Notification settings</span>
      </button>
    </div>
  );
}
