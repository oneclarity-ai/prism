import type { Modes, PageHeading, SidebarSection, TabName } from "@/lib/app-context";

export const LEGACY_V21_TABS = new Set<string>(["ask", "management", "journey", "knowledge", "memory", "records"]);
export const WORKSPACE_TABS = new Set<string>(["work", "approvals", "operations", "spending"]);

export const PAGE_TITLES: Record<TabName | "settings", [string, string, string]> = {
  overview: ["Home", "Your Prisms and what needs you.", ""],
  spending: ["Spending", "What Prisms and the agentic swarm cost, in one place.", "💳"],
  prisms: ["Prisms", "Create private specialist assistants for the work you want covered.", "✦"],
  work: ["Work", "One place to follow every Prism task and computer run.", "💼"],
  approvals: ["Approvals", "Review computer actions before a Prism proceeds.", "✅"],
  operations: ["Operations", "See the connected Prisms, tasks, runs, and setup in one workspace.", "⚙️"],
  ask: ["Ask", "Ask about team state. Answers cite their evidence.", "💡"],
  management: ["Work", "Escalations, blockers, commitments, and today's updates.", "✅"],
  journey: ["Journeys", "How Prism followed each blocker between people.", "🧭"],
  agent: ["Assistant Prism", "Ask what matters across your team, then approve each exact message.", "✦"],
  knowledge: ["My knowledge", "Context and preferences Prism should keep in mind.", "📚"],
  memory: ["Memory", "Evidence-backed facts and history Prism relies on.", "🧠"],
  settings: ["Settings", "Account, preferences, connections, and access.", "⚙️"],
};

export const headingFor = (tab: TabName): PageHeading => {
  const [title, subtitle, icon] = PAGE_TITLES[tab];
  return { title, subtitle, icon };
};

export const sectionFor = (tab: string): SidebarSection => (WORKSPACE_TABS.has(tab) ? "workspace" : "chat");

/** The old setActiveTab gating, minus DOM work: which tab is actually shown for a requested one. */
export function resolveTab(requested: string, modes: Modes): TabName {
  let tab = requested;
  if (!(tab in PAGE_TITLES) || tab === "settings") tab = "overview";
  if (modes.v21 === false && tab === "agent") tab = "overview";
  if (modes.v22 === false && (tab === "prisms" || tab === "spending" || WORKSPACE_TABS.has(tab))) tab = "overview";
  if (modes.v24 === false && tab === "operations") tab = "overview";
  if (modes.v22 === true && tab === "overview") tab = "prisms"; // Home is retired once Prisms are on.
  if (modes.v21 === true && LEGACY_V21_TABS.has(tab)) tab = "overview";
  return tab as TabName;
}

/** Wrapper visibility of `<section data-tab>` panels (`hidden` attribute in the old DOM). */
export function panelHidden(
  panel: { tab: TabName; v21Legacy?: boolean; v21Only?: boolean; v22Only?: boolean; v24Only?: boolean },
  activeTab: string,
  modes: Modes,
): boolean {
  if (panel.tab !== activeTab) return true;
  if (modes.v21 === true && panel.v21Legacy) return true;
  if (modes.v22 !== true && panel.v22Only) return true;
  if (panel.v24Only && modes.v24 !== true) return true;
  return false;
}
