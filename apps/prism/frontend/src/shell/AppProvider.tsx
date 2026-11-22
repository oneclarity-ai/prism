import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { flushSync } from "react-dom";
import {
  AppContext,
  type AppApi,
  type AskDialogOptions,
  type MicrosoftStatus,
  type Modes,
  type PageHeading,
  type ProviderStatus,
  type SettingsSection,
  type SidebarSection,
  type TabName,
} from "@/lib/app-context";
import { agentApi } from "@/lib/api";
import { emit, type PrismLike } from "@/lib/events";
import { createNavigation, type Navigation } from "@/lib/navigation";
import { initialTabFor, isUuid, parseRoute } from "@/lib/routes";
import { readStorage, STORAGE_KEYS, writeStorage } from "@/lib/storage";
import { ShellContext, type ConfirmRequest, type ShellState, type ToastState } from "./shell-context";
import { resolveTab, sectionFor, WORKSPACE_TABS } from "./tabs";

export const SETTINGS_SECTIONS: SettingsSection[] = [
  "account",
  "preferences",
  "notifications",
  "skills",
  "general",
  "teams",
  "archived",
  "connections",
  "provider",
  "access",
  "developer",
];

const NARROW_QUERY = "(max-width: 820px)";
const narrowMedia = window.matchMedia(NARROW_QUERY);
const subscribeNarrow = (listener: () => void) => {
  narrowMedia.addEventListener("change", listener);
  return () => narrowMedia.removeEventListener("change", listener);
};

function startTab(): TabName {
  const fromRoute = initialTabFor(parseRoute(location.pathname));
  if (fromRoute) return fromRoute as TabName;
  const saved = readStorage(STORAGE_KEYS.tab);
  return (saved === "records" ? "knowledge" : saved && saved !== "settings" ? saved : "prisms") as TabName;
}

function startSettingsSection(): SettingsSection {
  const saved = readStorage(STORAGE_KEYS.subtab("settings"));
  return SETTINGS_SECTIONS.includes(saved as SettingsSection) ? (saved as SettingsSection) : "preferences";
}

const UNAVAILABLE_PROVIDER: ProviderStatus = {
  provider: "unknown",
  model: null,
  state: "unavailable",
  ready: false,
  detail: "Provider status is unavailable",
};

export function AppProvider({ children }: { children: ReactNode }) {
  const [modes, setModes] = useState<Modes>({ v21: null, v22: null, v24: null, singleExecutive: false });
  const [activeTab, setActiveTabState] = useState<TabName>(startTab);
  const [sidebarSection, setSidebarSectionState] = useState<SidebarSection>(() => sectionFor(startTab()));
  const [routeError, setRouteErrorState] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsSection, setSettingsSectionState] = useState<SettingsSection>(startSettingsSection);
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [microsoft, setMicrosoft] = useState<MicrosoftStatus | null>(null);
  const [heading, setHeadingState] = useState<{ tab: TabName; heading: PageHeading } | null>(null);
  const [toast, setToast] = useState<ToastState>({ message: "", isError: false, show: false });
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => !narrowMedia.matches && readStorage(STORAGE_KEYS.sidebar) === "closed");
  const [sidebarOpenNarrow, setSidebarOpenNarrow] = useState(false);
  const [profileMenuResetKey, setProfileMenuResetKey] = useState(0);
  const [pageActionsRoot, setPageActionsRoot] = useState<HTMLElement | null>(null);
  const narrow = useSyncExternalStore(subscribeNarrow, () => narrowMedia.matches);

  // Latest values for the navigation host and async callbacks.
  const live = useRef({ modes, view: activeTab, routeError, settingsOpen, settingsSection, narrow });
  useLayoutEffect(() => {
    live.current.modes = modes;
    live.current.routeError = routeError;
    live.current.settingsOpen = settingsOpen;
    live.current.settingsSection = settingsSection;
    live.current.narrow = narrow;
  });
  const transition = useRef<Promise<unknown>>(Promise.resolve());
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const actions = useRef<{
    setActiveTab: (tab: TabName | "settings") => Promise<void> | void;
    openSettings: (section?: SettingsSection) => void;
    closeSettings: () => void;
  }>({ setActiveTab: () => {}, openSettings: () => {}, closeSettings: () => {} });

  const nav = useRef<Navigation | null>(null);
  if (nav.current === null) {
    nav.current = createNavigation({
      getView: () => (live.current.routeError !== null ? "route-error" : live.current.view),
      isSettingsOpen: () => live.current.settingsOpen,
      transition: () => transition.current,
      closeSettings: () => actions.current.closeSettings(),
      openSettings: (section) => actions.current.openSettings(section as SettingsSection),
      setActiveTab: (tab) => actions.current.setActiveTab(tab as TabName),
      setRouteError: (message) => {
        live.current.routeError = message;
        setRouteErrorState(message);
      },
      resolvePrism: (key) =>
        agentApi<PrismLike>(isUuid(key) ? `/api/v2/prisms/${encodeURIComponent(key)}` : `/api/v2/prisms/by-code/${encodeURIComponent(key)}`),
      modes: () => live.current.modes,
      openPrismForRoute: (prism) => emit("open-prism-route", { prism }),
      workspaceNavigate: (detail) => emit("workspace-navigate", detail),
      openLegacyAgent: () => emit("open-legacy-agent"),
    });
  }
  const navigation = nav.current;

  const setStatus = useCallback((message: string | null, isError = false) => {
    clearTimeout(toastTimer.current);
    if (!message) {
      setToast((current) => ({ ...current, show: false }));
      return;
    }
    setToast({ message, isError, show: true });
    toastTimer.current = setTimeout(() => setToast((current) => ({ ...current, show: false })), isError ? 8000 : 4500);
  }, []);

  const askDialog = useCallback(
    (options: AskDialogOptions) =>
      new Promise<true | string | null>((resolve) => {
        setConfirmRequest({ options, resolve });
      }),
    [],
  );

  const setSidebarSection = useCallback((section: SidebarSection) => {
    setSidebarSectionState(["chat", "workspace", "notifications"].includes(section) ? section : "chat");
  }, []);

  const setActiveTab = useCallback(
    (requested: TabName | "settings"): Promise<void> | void => {
      if (requested === "settings") {
        actions.current.openSettings();
        return;
      }
      setProfileMenuResetKey((key) => key + 1);
      const tab = resolveTab(requested, live.current.modes);
      const previous = live.current.view;
      const commit = () => {
        if (previous !== tab) {
          if (WORKSPACE_TABS.has(tab)) setSidebarSection(sectionFor(tab));
          else if (tab === "agent" || tab === "prisms") setSidebarSection("chat");
          setHeadingState(null);
        }
        live.current.view = tab;
        setActiveTabState(tab);
        navigation.tab(tab);
        writeStorage(STORAGE_KEYS.tab, tab);
      };
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (previous !== tab && !navigation.restoring && typeof document.startViewTransition === "function" && !reduced) {
        const viewTransition = document.startViewTransition(() => flushSync(commit));
        // A newer transition skips this one; its settled promises reject, which is expected.
        viewTransition.ready.catch(() => {});
        viewTransition.finished.catch(() => {});
        transition.current = viewTransition.updateCallbackDone;
        return viewTransition.updateCallbackDone;
      }
      commit();
    },
    [navigation, setSidebarSection],
  );

  const setSettingsSection = useCallback(
    (requested: SettingsSection) => {
      const section = SETTINGS_SECTIONS.includes(requested) ? requested : "account";
      live.current.settingsSection = section;
      setSettingsSectionState(section);
      writeStorage(STORAGE_KEYS.subtab("settings"), section);
      if (live.current.settingsOpen) navigation.settings(section);
    },
    [navigation],
  );

  const openSettings = useCallback(
    (section?: SettingsSection) => {
      setProfileMenuResetKey((key) => key + 1);
      live.current.settingsOpen = true;
      setSettingsOpen(true);
      if (section) setSettingsSection(section);
      navigation.settings(live.current.settingsSection);
    },
    [navigation, setSettingsSection],
  );

  const closeSettings = useCallback(() => {
    if (!live.current.settingsOpen) return;
    live.current.settingsOpen = false;
    setSettingsOpen(false);
    navigation.settingsClosed();
  }, [navigation]);

  useLayoutEffect(() => {
    actions.current = { setActiveTab, openSettings, closeSettings };
  }, [setActiveTab, openSettings, closeSettings]);

  const refreshStatus = useCallback(async () => {
    const [provider, microsoft] = await Promise.all([
      agentApi<ProviderStatus>("/api/v1/provider/status").catch(() => UNAVAILABLE_PROVIDER),
      agentApi<MicrosoftStatus>("/api/v1/microsoft/status").catch(() => null),
    ]);
    setProviderStatus(provider);
    setMicrosoft(microsoft);
  }, []);

  // Capability probes + provider/Microsoft status: the old loadDashboard's shell-owned half.
  useEffect(() => {
    let cancelled = false;
    setRefreshing(true);
    const patch = (value: Partial<Modes>) => {
      if (!cancelled) setModes((current) => ({ ...current, ...value }));
    };
    const probes = [
      agentApi("/api/v2/agent/foundation").then(() => patch({ v21: true }), () => patch({ v21: false })),
      agentApi<{ single_executive_mode?: boolean }>("/api/v2/prisms/foundation").then(
        (foundation) => patch({ v22: true, singleExecutive: Boolean(foundation.single_executive_mode) }),
        () => patch({ v22: false, singleExecutive: false }),
      ),
      agentApi<{ computers?: boolean }>("/api/v2/qa/status").then(
        (status) => patch({ v24: Boolean(status.computers) }),
        () => patch({ v24: false }),
      ),
      refreshStatus(),
    ];
    void Promise.all(probes).finally(() => {
      if (!cancelled) setRefreshing(false);
    });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, refreshStatus]);

  // Re-apply tab gating whenever a capability answer changes (old applyV21/22/24Mode).
  useEffect(() => {
    if (modes.v22 === false) setSidebarSection("chat");
    void setActiveTab(live.current.view);
    if (modes.v21 !== null && modes.v22 !== null && modes.v24 !== null) navigation.markModesKnown();
  }, [modes, navigation, setActiveTab, setSidebarSection]);

  useEffect(() => {
    navigation.markDomReady();
    const params = new URLSearchParams(window.location.search);
    if (params.get("microsoft") === "connected") setStatus("Microsoft account connected. Import your organization directory next.");
    const failure = params.get("microsoft_error");
    if (failure) setStatus(failure, true);
    return () => navigation.dispose();
  }, [navigation, setStatus]);

  const toggleSidebar = useCallback((open: boolean) => {
    if (live.current.narrow) {
      setSidebarOpenNarrow(open);
      return;
    }
    setSidebarCollapsed(!open);
    writeStorage(STORAGE_KEYS.sidebar, open ? "open" : "closed");
  }, []);

  const setPageHeading = useCallback((next: PageHeading | null) => {
    setHeadingState(next ? { tab: live.current.view, heading: next } : null);
  }, []);

  const view = routeError !== null ? "route-error" : activeTab;
  useEffect(() => {
    live.current.view = activeTab;
  }, [activeTab]);

  const app: AppApi = useMemo(
    () => ({
      activeTab,
      setActiveTab,
      sidebarSection,
      setSidebarSection,
      modes,
      setStatus,
      askDialog,
      settings: { isOpen: settingsOpen, section: settingsSection, open: openSettings, close: closeSettings, setSection: setSettingsSection },
      refreshKey,
      refresh: () => setRefreshKey((key) => key + 1),
      providerStatus,
      microsoftConnected: microsoft ? Boolean(microsoft.is_connected) : null,
      microsoft,
      narrow,
      openSidebar: () => toggleSidebar(true),
      closeSidebarIfNarrow: () => {
        if (live.current.narrow) toggleSidebar(false);
      },
      openSearch: () => emit("open-search"),
      go: (path) => void navigation.go(path),
      refreshStatus,
      setPageHeading,
      pageActionsRoot,
      routes: {
        prism: navigation.prism,
        workspace: navigation.workspace,
        requestedPrism: navigation.requestedPrism,
        requestedLegacy: navigation.requestedLegacy,
      },
    }),
    [
      activeTab,
      setActiveTab,
      sidebarSection,
      setSidebarSection,
      modes,
      setStatus,
      askDialog,
      settingsOpen,
      settingsSection,
      openSettings,
      closeSettings,
      setSettingsSection,
      refreshKey,
      providerStatus,
      microsoft,
      narrow,
      toggleSidebar,
      navigation,
      refreshStatus,
      setPageHeading,
      pageActionsRoot,
    ],
  );

  // The e2e journeys (and ad-hoc scripts) drive the page through the old `window.prism` helpers.
  const appRef = useRef(app);
  appRef.current = app;
  useEffect(() => {
    Object.assign(window, {
      prism: {
        setPageHeading: (title: string, subtitle: string, icon: string) => appRef.current.setPageHeading({ title, subtitle, icon }),
        setActiveTab: (tab: TabName | "settings") => appRef.current.setActiveTab(tab),
        setSubtab: (group: string, name: string) => {
          if (group === "settings") appRef.current.settings.setSection(name as SettingsSection);
        },
        setStatus: (message: string | null, isError?: boolean) => appRef.current.setStatus(message, isError),
        askDialog: (options: AskDialogOptions) => appRef.current.askDialog(options),
        isV22Enabled: () => live.current.modes.v22,
        isV24Enabled: () => live.current.modes.v24,
        applyV24Mode: (enabled: boolean) => setModes((current) => ({ ...current, v24: Boolean(enabled) })),
        setSidebarSection: (section: SidebarSection) => appRef.current.setSidebarSection(section),
        openSettings: (section?: SettingsSection) => appRef.current.settings.open(section),
        closeSettings: () => appRef.current.settings.close(),
        openSearch: () => appRef.current.openSearch(),
      },
    });
  }, []);

  // The e2e journeys also dispatch the old document events; forward them to the bus.
  useEffect(() => {
    const forward = (name: "workspace-navigate" | "search-result") => (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (name === "workspace-navigate") emit(name, detail);
      else emit(name, detail);
    };
    const nav = forward("workspace-navigate");
    const search = forward("search-result");
    document.addEventListener("prism:workspace-navigate", nav);
    document.addEventListener("prism:search-result", search);
    return () => {
      document.removeEventListener("prism:workspace-navigate", nav);
      document.removeEventListener("prism:search-result", search);
    };
  }, []);

  const shell: ShellState = {
    view,
    heading: heading && heading.tab === activeTab ? heading.heading : null,
    routeError,
    refreshing,
    toast,
    confirmRequest,
    clearConfirm: () => setConfirmRequest(null),
    sidebarCollapsed,
    sidebarOpenNarrow,
    toggleSidebar,
    profileMenuResetKey,
    setPageActionsRoot,
    singleExecutive: modes.singleExecutive,
  };

  return (
    <AppContext.Provider value={app}>
      <ShellContext.Provider value={shell}>{children}</ShellContext.Provider>
    </AppContext.Provider>
  );
}
