import type { KeyboardEvent } from "react";
import { PrismLogoIcon } from "@/components/ui";
import { useApp, type SidebarSection } from "@/lib/app-context";
import { useNavCount } from "@/lib/nav-counts";
import { PrismCreateButton } from "@/features/prisms/PrismCreateButton";
import { PrismSidebarSection } from "@/features/prisms/PrismSidebarSection";
import { NotificationsSidebarPanel } from "@/features/workspace/NotificationsSidebarPanel";
import { WorkspaceSidebarPanel } from "@/features/workspace/WorkspaceSidebarPanel";
import { ProfileMenu } from "./ProfileMenu";
import { useShell } from "./shell-context";

const SWITCHES: { section: SidebarSection; label: string; path: React.ReactNode }[] = [
  { section: "chat", label: "Chats", path: <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" /> },
  {
    section: "workspace",
    label: "Workspace",
    path: (
      <>
        <rect x="2" y="7" width="20" height="14" rx="2" />
        <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
      </>
    ),
  },
  { section: "notifications", label: "Notifications", path: <path d="m3 11 4.5-7h9l4.5 7v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8ZM3 11h5a4 4 0 0 0 8 0h5" /> },
];

export function Sidebar() {
  const app = useApp();
  const { toggleSidebar } = useShell();
  const agentCount = useNavCount("agent");
  const { v21, v22 } = app.modes;
  const navigate = (tab: "overview" | "agent") => {
    app.setActiveTab(tab);
    app.closeSidebarIfNarrow();
  };

  const onSwitcherKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const buttons = [...document.querySelectorAll<HTMLButtonElement>("[data-sidebar-target]")].filter((button) => !button.hidden);
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (index < 0) return;
    event.preventDefault();
    const next = buttons[(index + (event.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length]!;
    next.focus();
    app.setSidebarSection(next.dataset.sidebarTarget as SidebarSection);
  };

  return (
    <aside className="sidebar" aria-label="Primary">
      <div className="sidebar-head">
        <div className="brand">
          <span className="brand-logo" data-prism-brand aria-hidden="true"><PrismLogoIcon colorKey="purple" /></span>
          <span className="brand-name">Prism</span>
        </div>
        <PrismCreateButton />
        <button id="sidebar-close" className="icon-button" type="button" aria-label="Close sidebar" onClick={() => toggleSidebar(false)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m11 17-5-5 5-5M18 17l-5-5 5-5" /></svg>
        </button>
      </div>
      <div className="sidebar-switcher" data-v22-only hidden={v22 !== true}>
        <div className="sidebar-tabs" role="tablist" aria-label="Sidebar view" onKeyDown={onSwitcherKeys}>
          {SWITCHES.map(({ section, label, path }) => {
            const active = app.sidebarSection === section;
            return (
              <button
                key={section}
                className={`sidebar-switch${active ? " active" : ""}`}
                type="button"
                role="tab"
                id={`sidebar-${section === "chat" ? "chat" : section}-tab`}
                aria-label={label}
                title={label}
                data-sidebar-target={section}
                aria-selected={active}
                aria-controls={`sidebar-${section}-panel`}
                tabIndex={active ? 0 : -1}
                onClick={() => app.setSidebarSection(section)}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">{path}</svg>
                <span>{label}</span>
              </button>
            );
          })}
        </div>
        <button className="sidebar-switch sidebar-switch-end" type="button" id="sidebar-search-tab" aria-label="Search" title="Search (Ctrl/Cmd+K)" aria-haspopup="dialog" data-open-search onClick={() => app.openSearch()}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="m20 20-4-4" /></svg>
          <span>Search</span>
        </button>
      </div>
      <nav className="nav" aria-label="Dashboard sections">
        <div id="sidebar-chat-panel" className="sidebar-section" role="tabpanel" aria-labelledby="sidebar-chat-tab" hidden={app.sidebarSection !== "chat"}>
          <button
            className={`nav-item${app.activeTab === "overview" ? " active" : ""}`}
            type="button"
            data-tab-target="overview"
            data-hide-v22
            aria-selected={app.activeTab === "overview"}
            hidden={v22 === true}
            onClick={() => navigate("overview")}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11 12 3l9 8M5 10v10h14V10" /></svg>
            <span>Home</span>
          </button>
          <button
            className={`nav-item${app.activeTab === "agent" ? " active" : ""}`}
            type="button"
            data-tab-target="agent"
            data-v21-only
            data-hide-v22
            aria-selected={app.activeTab === "agent"}
            hidden={v21 !== true || v22 === true}
            onClick={() => navigate("agent")}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /><path d="M5 19h14" /></svg>
            <span>Assistant Prism</span>
            <span id="nav-agent-count" className="nav-count approval" aria-label="Drafts waiting for your approval" hidden={!agentCount}>{agentCount || ""}</span>
          </button>
          <PrismSidebarSection />
        </div>
        <div id="sidebar-workspace-panel" className="sidebar-section" role="tabpanel" aria-labelledby="sidebar-workspace-tab" hidden={app.sidebarSection !== "workspace"}>
          <WorkspaceSidebarPanel />
        </div>
        <div id="sidebar-notifications-panel" className="sidebar-section" role="tabpanel" aria-labelledby="sidebar-notifications-tab" hidden={app.sidebarSection !== "notifications"}>
          <NotificationsSidebarPanel />
        </div>
      </nav>
      <ProfileMenu />
    </aside>
  );
}
