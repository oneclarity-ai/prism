import { createContext, useContext } from "react";
import type { PrismLike } from "./events";
import type { WorkspaceLocation } from "./routes";

export type TabName =
  | "overview"
  | "prisms"
  | "agent"
  | "work"
  | "approvals"
  | "operations"
  | "spending"
  | "ask"
  | "management"
  | "journey"
  | "knowledge"
  | "memory";
export type SidebarSection = "chat" | "workspace" | "notifications";
export type SettingsSection =
  | "account"
  | "preferences"
  | "notifications"
  | "general"
  | "teams"
  | "archived"
  | "connections"
  | "provider"
  | "access"
  | "developer"
  | "skills";

/** `null` until the matching capability probe answered (same as the old v21Mode/v22Mode/v24Mode). */
export interface Modes {
  v21: boolean | null;
  v22: boolean | null;
  v24: boolean | null;
  singleExecutive: boolean;
}

export interface AskDialogOptions {
  title: string;
  message?: string;
  confirmLabel?: string;
  danger?: boolean;
  field?: { label: string; type?: string; placeholder?: string; value?: string } | null;
}

export interface PageHeading {
  title: string;
  subtitle: string;
  icon: string;
}

export interface MicrosoftStatus {
  is_connected?: boolean;
  is_auth_configured?: boolean;
  connection?: { display_name?: string | null; user_principal_name?: string | null } | null;
  [key: string]: unknown;
}

export interface ProviderStatus {
  provider: string;
  model: string | null;
  state: string;
  ready: boolean;
  detail: string;
  credential_source?: string | null;
  masked_key?: string | null;
  can_manage?: boolean;
}

/** Shell capabilities features may use; mirrors the old `window.prism` helper object. */
export interface AppApi {
  activeTab: TabName;
  /** Switch the visible page (same gating rules as the old setActiveTab). "settings" opens the settings dialog. */
  setActiveTab: (tab: TabName | "settings") => void;
  sidebarSection: SidebarSection;
  setSidebarSection: (section: SidebarSection) => void;
  modes: Modes;
  /** Toast (role=status). `null` message hides it. Errors stay up longer. */
  setStatus: (message: string | null, isError?: boolean) => void;
  /** Promise-based confirm/prompt dialog (#confirm-dialog). Resolves true, the typed text when `field` is set, or null. */
  askDialog: (options: AskDialogOptions) => Promise<true | string | null>;
  settings: {
    isOpen: boolean;
    section: SettingsSection;
    open: (section?: SettingsSection) => void;
    close: () => void;
    /** Switch section while open; remembered in localStorage and reflected in the URL. */
    setSection: (section: SettingsSection) => void;
  };
  /** Increments whenever the user hits "Reload all data"; features reload their data when it changes. */
  refreshKey: number;
  refresh: () => void;
  /** Provider and Microsoft status shown in the profile menu and preferences. */
  providerStatus: ProviderStatus | null;
  microsoftConnected: boolean | null;
  /** Full /api/v1/microsoft/status answer (account name for greetings, avatar initials, connect button state). */
  microsoft: MicrosoftStatus | null;
  /** Narrow (<=820px) layout: the sidebar is an overlay. */
  narrow: boolean;
  openSidebar: () => void;
  closeSidebarIfNarrow: () => void;
  openSearch: () => void;
  /** Navigate by URL path exactly like the old `prismRoutes.go`. */
  go: (path: string) => void;
  /** Re-read provider + Microsoft status (after saving a key, connecting Microsoft...). */
  refreshStatus: () => Promise<void>;
  /** Override the page heading (title/subtitle/icon); `null` restores the tab's default. Icon "" shows the Prism logo. */
  setPageHeading: (heading: PageHeading | null) => void;
  /** `#workspace-page-actions` element: render page-level action buttons into it with a React portal. */
  pageActionsRoot: HTMLElement | null;
  /** Tell the URL layer which Prism / workspace page is showing (old `prismRoutes.prism` / `.workspace`). */
  routes: {
    prism: (prism: PrismLike, replace?: boolean) => void;
    workspace: (value: WorkspaceLocation) => void;
    /** Deep-link info captured at load: do not auto-select a stored Prism when one was requested. */
    requestedPrism: string | null;
    requestedLegacy: boolean;
  };
}

export const AppContext = createContext<AppApi | null>(null);

export function useApp(): AppApi {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside <AppProvider>");
  return value;
}
