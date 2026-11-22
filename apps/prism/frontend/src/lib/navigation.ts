/**
 * History navigation controller (port of navigation.js). It owns the URL <-> page rules and talks to the
 * React shell through `NavigationHost`; it holds no React state itself.
 */
import type { Modes } from "./app-context";
import type { PrismLike } from "./events";
import {
  chatPath,
  initialTabFor,
  pathForView,
  pathForWorkspace,
  parseRoute,
  type ParsedRoute,
  type WorkspaceLocation,
} from "./routes";

export interface NavigationHost {
  /** Current view name; "route-error" while the error panel shows. */
  getView: () => string;
  isSettingsOpen: () => boolean;
  /** Resolves when the running view transition (if any) finished. */
  transition: () => Promise<unknown>;
  closeSettings: () => void;
  openSettings: (section: string) => void;
  setActiveTab: (tab: string) => Promise<unknown> | void;
  setRouteError: (message: string | null) => void;
  resolvePrism: (key: string) => Promise<PrismLike>;
  modes: () => Modes;
  openPrismForRoute: (prism: PrismLike) => void;
  workspaceNavigate: (detail: { page: string; id?: string; section?: string; runId?: string }) => void;
  openLegacyAgent: () => void;
}

export interface Navigation {
  initialRoute: ParsedRoute;
  initialTab: ReturnType<typeof initialTabFor>;
  requestedPrism: string | null;
  requestedLegacy: boolean;
  readonly restoring: boolean;
  go: (path: string) => Promise<void>;
  tab: (tab: string) => void;
  prism: (item: PrismLike, replace?: boolean) => void;
  workspace: (value: WorkspaceLocation) => void;
  settings: (section: string) => void;
  settingsClosed: () => void;
  /** Called when all three capability probes answered and the first render happened. */
  markModesKnown: () => void;
  markDomReady: () => void;
  dispose: () => void;
}

export function createNavigation(host: NavigationHost): Navigation {
  const initialUrl = new URL(location.href);
  const initial = parseRoute(initialUrl.pathname);
  let ready = false;
  let restoring = 0;
  let serial = 0;
  let domReady = false;
  let modesKnown = false;
  let prism: PrismLike | null = null;
  let workspace: WorkspaceLocation = { page: "overview" };
  let settingsBackground: string | null = null;

  const currentPath = (): string => {
    const view = host.getView();
    if (view === "operations") return pathForWorkspace(workspace);
    if (["agent", "prisms"].includes(view) && prism && host.modes().v22 !== false) return chatPath(prism);
    return pathForView(view);
  };

  function write(path: string, replace = false, extra: Record<string, unknown> = {}): void {
    if (!ready || restoring) return;
    const url = new URL(location.href);
    url.pathname = path;
    if (url.pathname === location.pathname) return;
    history[replace ? "replaceState" : "pushState"]({ ...history.state, ...extra, prismRoute: true }, "", url);
  }

  async function apply(url: URL, _replace = false): Promise<void> {
    const target = parseRoute(url.pathname);
    const token = ++serial;
    restoring += 1;
    try {
      await host.transition();
      if (token !== serial) return;
      host.setRouteError(null);
      if (target.kind !== "settings") host.closeSettings();
      if (target.kind === "settings") {
        const background: string = history.state?.settingsBackground || currentPath();
        settingsBackground = background.startsWith("/settings") ? "/chats" : background;
        if (host.getView() === "route-error") await host.setActiveTab("prisms");
        host.openSettings(target.section);
      } else if (target.kind === "chat" || target.kind === "prism-settings") {
        if (!host.modes().v22) throw new Error("Prisms are unavailable while this feature is disabled.");
        const selected = await host.resolvePrism(target.key);
        if (token !== serial) return;
        prism = selected;
        if (target.kind === "chat") host.openPrismForRoute(selected);
        else {
          if (!host.modes().v24) throw new Error("Prism workspace settings are unavailable while computers are disabled.");
          host.workspaceNavigate({ page: "prism", id: selected.id, section: target.section });
        }
      } else if (target.kind === "workspace" || target.kind === "run") {
        if (!host.modes().v24) throw new Error("This workspace page is unavailable while computers are disabled.");
        if (target.kind === "run") host.workspaceNavigate({ page: "runs", runId: target.id });
        else host.workspaceNavigate({ page: target.page });
      } else if (target.kind === "page") {
        if (target.page === "agent") {
          prism = null;
          host.openLegacyAgent();
        }
        await host.setActiveTab(target.page);
      } else if (target.kind === "default") {
        // Existing /dashboard/?thread=... links retain their legacy resolver.
        if (url.searchParams.has("thread")) {
          prism = null;
          host.openLegacyAgent();
          await host.setActiveTab("agent");
        }
      } else throw new Error("That dashboard page could not be found.");
      if (token !== serial) return;
      const path =
        target.kind === "chat" && prism
          ? chatPath(prism)
          : target.kind === "prism-settings" && prism
            ? `${chatPath(prism)}/settings/${target.section}`
            : ["default", "page"].includes(target.kind)
              ? currentPath()
              : url.pathname;
      const canonical = new URL(url);
      canonical.pathname = path;
      history.replaceState({ ...history.state, prismRoute: true }, "", canonical);
    } catch (error) {
      if (token === serial) host.setRouteError(error instanceof Error && error.message ? error.message : "This page could not be opened.");
    } finally {
      restoring -= 1;
    }
  }

  async function go(path: string): Promise<void> {
    const url = new URL(path, location.origin);
    write(url.pathname);
    await apply(url);
  }

  function start(): void {
    if (ready || !domReady || !modesKnown) return;
    ready = true;
    void apply(initialUrl, true);
  }

  const onPopState = () => {
    if (ready) void apply(new URL(location.href));
  };
  window.addEventListener("popstate", onPopState);

  return {
    initialRoute: initial,
    initialTab: initialTabFor(initial),
    requestedPrism: initial.kind === "chat" || initial.kind === "prism-settings" ? initial.key : null,
    requestedLegacy: initialUrl.searchParams.has("thread"),
    get restoring() {
      return restoring > 0;
    },
    go,
    tab(tab) {
      if (tab !== "settings" && !host.isSettingsOpen()) {
        host.setRouteError(null);
        if (tab === "operations") return;
        write(currentPath());
      }
    },
    prism(item, replace = false) {
      prism = item;
      if (["agent", "prisms"].includes(host.getView()) && !host.isSettingsOpen()) write(chatPath(item), replace);
    },
    workspace(value) {
      const old = workspace;
      workspace = value;
      if (host.getView() === "operations" && !host.isSettingsOpen()) {
        write(pathForWorkspace(value), old.page === "prism" && value.page === "prism" && old.id === value.id && old.section === value.section);
      }
    },
    settings(section) {
      if (!ready || restoring) return;
      settingsBackground ||= location.pathname;
      write(`/settings/${section}`, false, { settingsBackground });
    },
    settingsClosed() {
      if (!restoring && ready && location.pathname.startsWith("/settings")) write(settingsBackground || currentPath());
      settingsBackground = null;
    },
    markModesKnown() {
      modesKnown = true;
      start();
    },
    markDomReady() {
      domReady = true;
      start();
    },
    dispose() {
      window.removeEventListener("popstate", onPopState);
    },
  };
}
