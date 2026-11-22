import { useEffect, useRef, type ReactNode } from "react";
import { PrismLogoIcon } from "@/components/ui";
import { useApp, type TabName } from "@/lib/app-context";
import { usePrisms } from "@/features/prisms/PrismsContext";
import { AgentPage } from "@/features/chat/AgentPage";
import { AskPage } from "@/features/legacy/AskPage";
import { JourneyPage } from "@/features/legacy/JourneyPage";
import { KnowledgePage } from "@/features/legacy/KnowledgePage";
import { LegacyDialogs } from "@/features/legacy/LegacyDialogs";
import { ManagementPage } from "@/features/legacy/ManagementPage";
import { MemoryPage } from "@/features/legacy/MemoryPage";
import { useLegacyData } from "@/features/legacy";
import { OverviewPage } from "@/features/legacy/OverviewPage";
import { PrismsPage } from "@/features/prisms/PrismsPage";
import { CommandPalette } from "@/features/search/CommandPalette";
import { SettingsDialog } from "@/features/settings/SettingsDialog";
import { useTodayAiCost } from "@/features/spending";
import { SpendingPage } from "@/features/spending/SpendingPage";
import { ApprovalsPage } from "@/features/workspace/ApprovalsPage";
import { OperationsPage } from "@/features/workspace/OperationsPage";
import { WorkPage } from "@/features/workspace/WorkPage";
import { ConfirmDialog } from "./ConfirmDialog";
import { Sidebar } from "./Sidebar";
import { useShell } from "./shell-context";
import { headingFor, panelHidden } from "./tabs";

interface PanelSpec {
  tab: TabName;
  className: string;
  v21Legacy?: boolean;
  v21Only?: boolean;
  v22Only?: boolean;
  v24Only?: boolean;
  render: () => ReactNode;
}

const PANELS: PanelSpec[] = [
  { tab: "overview", className: "view tab-panel", render: () => <OverviewPage /> },
  { tab: "prisms", className: "view tab-panel prism-directory-view", v22Only: true, render: () => <PrismsPage /> },
  { tab: "work", className: "view tab-panel unified-work-view", v22Only: true, render: () => <WorkPage /> },
  { tab: "approvals", className: "view tab-panel unified-work-view", v22Only: true, render: () => <ApprovalsPage /> },
  { tab: "operations", className: "view tab-panel operations-view", v22Only: true, v24Only: true, render: () => <OperationsPage /> },
  { tab: "ask", className: "view tab-panel", v21Legacy: true, render: () => <AskPage /> },
  { tab: "management", className: "view tab-panel", v21Legacy: true, render: () => <ManagementPage /> },
  { tab: "journey", className: "view tab-panel", v21Legacy: true, render: () => <JourneyPage /> },
  { tab: "agent", className: "view tab-panel agent-workspace", v21Only: true, render: () => <AgentPage /> },
  { tab: "knowledge", className: "view tab-panel", v21Legacy: true, render: () => <KnowledgePage /> },
  { tab: "memory", className: "view tab-panel", v21Legacy: true, render: () => <MemoryPage /> },
  { tab: "spending", className: "view tab-panel spending-view", v22Only: true, render: () => <SpendingPage /> },
];

export function Shell() {
  const app = useApp();
  const shell = useShell();
  const { prisms, selectedId } = usePrisms();
  const cost = useTodayAiCost();
  const legacy = useLegacyData();
  const workspace = useRef<HTMLDivElement>(null);

  const heading = shell.routeError !== null ? { title: "Page unavailable", subtitle: shell.routeError, icon: "" } : (shell.heading ?? headingFor(app.activeTab));

  // Tab title follows the page; a Prism's chat shows that Prism's name (old tab-identity.js).
  useEffect(() => {
    const prism = prisms.find((item) => item.id === selectedId);
    document.title =
      prism && shell.routeError === null && (app.activeTab === "agent" || app.activeTab === "prisms") && !shell.heading
        ? `${prism.name} · Prism`
        : `${heading.title} · Prism`;
  }, [heading.title, prisms, selectedId, app.activeTab, shell.heading, shell.routeError]);

  useEffect(() => {
    workspace.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [app.activeTab]);

  const appClass = ["app", shell.sidebarCollapsed ? "sidebar-collapsed" : "", shell.sidebarOpenNarrow ? "sidebar-open" : ""].filter(Boolean).join(" ");

  return (
    <div className={appClass} id="app" data-view={shell.view}>
      <Sidebar />
      <div className="scrim" id="scrim" onClick={() => shell.toggleSidebar(false)}></div>
      <div className="workspace" ref={workspace}>
        <button id="sidebar-open" className="icon-button floating-sidebar-open" type="button" aria-label="Open sidebar" onClick={() => shell.toggleSidebar(true)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <div className="topbar" hidden>
          <div className="breadcrumb">
            <span id="crumb-icon" aria-hidden="true" hidden={!heading.icon}>{heading.icon}</span>
            <span id="crumb-logo" className="brand-logo crumb-logo" data-prism-brand hidden={Boolean(heading.icon)}><PrismLogoIcon colorKey="purple" /></span>
            <span id="crumb-title">{heading.title}</span>
          </div>
          <div className="topbar-actions">
            <span id="ai-cost-today" aria-live="polite" title={cost.title}>{cost.text}</span>
            <button id="refresh-button" className={`icon-button${shell.refreshing || legacy.loading ? " spinning" : ""}`} type="button" aria-label="Refresh dashboard" data-tooltip="Reload all data" onClick={app.refresh}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0 1.4 4.5M20 4v7h-7" /></svg>
            </button>
          </div>
        </div>
        <div className="page">
          <header className="page-head">
            <div id="page-icon" className="page-icon" aria-hidden="true" hidden={!heading.icon}>{heading.icon}</div>
            <div id="page-logo" className="page-logo" data-prism-brand hidden={Boolean(heading.icon)}><PrismLogoIcon colorKey="purple" /></div>
            <h1 id="page-title">{heading.title}</h1>
            <p id="page-subtitle" className="page-subtitle">{heading.subtitle}</p>
            <div id="workspace-page-actions" className="workspace-page-actions" ref={shell.setPageActionsRoot}></div>
          </header>
          <main>
            <p id="status-message" className={`status-message${shell.toast.show ? " show" : ""}${shell.toast.isError ? " error" : ""}`} role="status" aria-live="polite">
              {shell.toast.message}
            </p>
            {PANELS.map((panel) => (
              <section
                key={panel.tab}
                className={panel.className}
                data-tab={panel.tab}
                data-v21-legacy={panel.v21Legacy ? "" : undefined}
                data-v21-only={panel.v21Only ? "" : undefined}
                data-v22-only={panel.v22Only ? "" : undefined}
                data-v24-only={panel.v24Only ? "" : undefined}
                hidden={shell.routeError !== null || panelHidden(panel, app.activeTab, app.modes)}
              >
                {panel.render()}
              </section>
            ))}
          </main>
        </div>
        {shell.routeError !== null && (
          <section id="route-error-panel" className="page">
            <p role="alert">{shell.routeError}</p>
            <button className="button secondary" type="button" onClick={() => app.go("/chats")}>Open chats</button>
          </section>
        )}
      </div>
      <CommandPalette />
      <SettingsDialog />
      <ConfirmDialog />
      <LegacyDialogs />
    </div>
  );
}
