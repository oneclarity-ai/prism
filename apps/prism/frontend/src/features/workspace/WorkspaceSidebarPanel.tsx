import type { ReactNode } from "react";
import { useApp, type TabName } from "@/lib/app-context";
import { useNavCount } from "@/lib/nav-counts";
import { WorkspaceNavButton } from "./WorkspaceNavButton";

interface TabButtonProps {
  tab: TabName;
  label: string;
  id?: string;
  hidden?: boolean;
  v22Only?: boolean;
  leading?: ReactNode;
  trailing?: ReactNode;
}

/** Computer actions waiting in the Approvals inbox (filled by the unified-work loader). */
function ApprovalCount() {
  const count = useNavCount("work-approvals");
  return (
    <span id="work-approval-count" className="nav-count approval" hidden={count === 0}>
      {count}
    </span>
  );
}

/** `[data-tab-target]` sidebar entry: switches the page and closes the overlay sidebar on narrow screens. */
function TabButton({ tab, label, id, hidden, v22Only, leading, trailing }: TabButtonProps) {
  const { activeTab, setActiveTab, closeSidebarIfNarrow } = useApp();
  const active = activeTab === tab;
  return (
    <button
      id={id}
      className={`nav-item${active ? " active" : ""}`}
      type="button"
      data-tab-target={tab}
      {...(v22Only ? { "data-v22-only": "" } : {})}
      hidden={hidden}
      aria-selected={active}
      onClick={() => {
        setActiveTab(tab);
        closeSidebarIfNarrow();
      }}
    >
      {leading}
      <span>{label}</span>
      {trailing}
    </button>
  );
}

/** Everything inside `#sidebar-workspace-panel`. Gating follows applyV22Mode/applyV24Mode of the old app.js. */
export function WorkspaceSidebarPanel() {
  const { modes } = useApp();
  const v22 = modes.v22 === true;
  const v24 = modes.v24 === true;
  return (
    <>
      <div className="workspace-navigation">
        <div className="workspace-nav-label">Overview</div>
        <WorkspaceNavButton page="overview" glyph="layout-dashboard" label="Dashboard" gate="v24" hidden={!v24} />
        <TabButton
          tab="spending"
          label="Spending"
          id="nav-spending"
          v22Only
          hidden={!v22}
          leading={
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 7h18v12H3zM3 11h18M7 15h3" />
            </svg>
          }
        />
        <WorkspaceNavButton page="usage" glyph="wallet" label="Run analytics" gate="v24" hidden={!v24} />
      </div>
      <div className="workspace-navigation" data-v24-only="" hidden={!v24}>
        <div className="workspace-nav-label">Work</div>
        <WorkspaceNavButton page="tasks" glyph="list-checks" label="Tasks" />
        <WorkspaceNavButton page="runs" glyph="circle-play" label="Runs" />
        <WorkspaceNavButton page="approvals" glyph="shield-check" label="Approvals" />
        <WorkspaceNavButton page="bugs" glyph="bug" label="Bugs" />
        <div className="workspace-nav-label">Team</div>
        <WorkspaceNavButton page="agents" glyph="bot" label="Prisms" />
        <div className="workspace-nav-label">Setup</div>
        <WorkspaceNavButton page="targets" glyph="globe" label="Target apps" />
        <WorkspaceNavButton page="secrets" glyph="key-round" label="Secrets" />
      </div>
      <div className="workspace-navigation" data-v22-only="" hidden={!v22}>
        <div className="workspace-nav-label">Knowledge</div>
        <WorkspaceNavButton page="skills" glyph="brain" label="Skills" gate="v22" hidden={!v22} />
        <WorkspaceNavButton page="brain" glyph="brain" label="Brain" gate="v22" hidden={!v22} approvalBadge badgeLabel="Facts waiting for your approval" />
      </div>
      <div id="workspace-legacy-links" hidden={v24}>
        <TabButton tab="work" label="Work" />
        <TabButton tab="approvals" label="Approvals" trailing={<ApprovalCount />} />
      </div>
    </>
  );
}
