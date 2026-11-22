import { useCallback, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useApp } from "@/lib/app-context";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { emit, useBusEvent, type PrismLike } from "@/lib/events";
import { prismColorKey, prismLogoIcon } from "@/lib/prism-logo";
import { readStorage, STORAGE_KEYS, writeStorage } from "@/lib/storage";
import { isArchived, isWorking, prismListKey } from "./helpers";
import { PrismsInternalContext, type PageCommands, type PrismsInternal } from "./internal";
import { useLiveState } from "./live";
import { useMonitoring } from "./monitoring";
import { PrismsContext, type PrismAction, type PrismsApi, type PrismUpdateSummary } from "./PrismsContext";
import type { Prism } from "./types";

const POLL_MS = 15000;

// One id per open page; the server uses it for presence and to give each notification a single claimant.
let cachedClientId: string | null = null;
function clientId(): string {
  if (cachedClientId) return cachedClientId;
  try {
    let id = sessionStorage.getItem("prism-client-id");
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem("prism-client-id", id);
    }
    cachedClientId = id;
  } catch {
    cachedClientId = crypto.randomUUID();
  }
  return cachedClientId;
}

const notificationsSupported = (): boolean => typeof window !== "undefined" && "Notification" in window;
export const notificationPermission = (): string => (notificationsSupported() ? Notification.permission : "unsupported");

interface DirectoryState {
  prisms: Prism[];
  loading: boolean;
  selectedId: string | null;
  includeArchived: boolean;
  archivedPressed: boolean;
  summaries: ReadonlyMap<string, PrismUpdateSummary>;
  selectionNonce: number;
  loadTick: number;
  renderTick: number;
}

interface ClaimedNotification {
  notification_id: string;
  prism_id: string;
  title: string;
  body: string;
  tag: string;
}

export function PrismsProvider({ children }: { children: ReactNode }) {
  const app = useApp();
  const appRef = useRef(app);
  appRef.current = app;
  const enabled = app.modes.v22 === true;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const [state, patch, live] = useLiveState<DirectoryState>({
    prisms: [],
    loading: false,
    // A deep link to one Prism (or the legacy assistant) wins over the remembered selection.
    selectedId: app.routes.requestedPrism || app.routes.requestedLegacy ? null : readStorage(STORAGE_KEYS.selectedPrism),
    includeArchived: false,
    archivedPressed: false,
    summaries: new Map(),
    selectionNonce: 0,
    loadTick: 0,
    renderTick: 0,
  });

  const setStatus = useCallback((message: string | null, isError?: boolean) =>
      isError === undefined ? appRef.current.setStatus(message) : appRef.current.setStatus(message, isError), []);
  const selectedRef = useRef<string | null>(state.selectedId);
  selectedRef.current = state.selectedId;
  const prismsRef = useRef<Prism[]>(state.prisms);
  prismsRef.current = state.prisms;
  const hasSelectedPrism = useCallback(() => live.current.prisms.some((item) => item.id === live.current.selectedId), [live]);
  const monitoring = useMonitoring({ selectedRef, hasSelectedPrism, setStatus });
  const monitoringRef = useRef(monitoring);
  monitoringRef.current = monitoring;

  const bump = useCallback(() => patch({ renderTick: live.current.renderTick + 1 }), [patch, live]);

  // The old render() dropped a selection that is no longer in the loaded list.
  const normalize = useCallback(() => {
    const { loading, prisms, selectedId } = live.current;
    if (!loading && prisms.length && selectedId && !prisms.some((prism) => prism.id === selectedId)) {
      patch({ selectedId: null });
      selectedRef.current = null;
      writeStorage(STORAGE_KEYS.selectedPrism, null);
    }
  }, [patch, live]);

  const loadPrisms = useCallback(async () => {
    if (!enabledRef.current) return;
    patch({ loading: true });
    bump();
    try {
      const rows = await agentApi<Prism[]>(`/api/v2/prisms?include_archived=${live.current.includeArchived}`);
      patch({ prisms: rows });
      // This local workspace intentionally has one Executive Assistant. Open it immediately on a new
      // browser/profile so its preserved history is never hidden behind an empty-state screen.
      const { routes } = appRef.current;
      if (!live.current.selectedId && rows.length === 1 && !routes.requestedPrism && !routes.requestedLegacy) {
        patch({ selectedId: rows[0].id });
        writeStorage(STORAGE_KEYS.selectedPrism, rows[0].id);
      }
    } catch (error) {
      patch({ prisms: [] });
      setStatus(errorMessage(error), true);
    } finally {
      patch({ loading: false });
      normalize();
      bump();
    }
    patch({ loadTick: live.current.loadTick + 1 });
    if (!live.current.selectedId) emit("no-prism-selected");
  }, [patch, live, bump, normalize, setStatus]);

  // Quietly refresh the sidebar's latest-message previews; a failed poll keeps what is shown.
  const refreshingList = useRef(false);
  const refreshPrismList = useCallback(async () => {
    if (!enabledRef.current || live.current.loading || refreshingList.current) return;
    refreshingList.current = true;
    try {
      const rows = await agentApi<Prism[]>(`/api/v2/prisms?include_archived=${live.current.includeArchived}`);
      if (prismListKey(rows) !== prismListKey(live.current.prisms)) {
        patch({ prisms: rows });
        normalize();
        bump();
      }
    } catch {
      /* retried on the next poll */
    } finally {
      refreshingList.current = false;
    }
  }, [patch, live, normalize, bump]);

  const selectPrism = useCallback(
    (id: string) => {
      const selected = live.current.prisms.find((item) => item.id === id);
      if (selected) appRef.current.routes.prism(selected);
      patch({ selectedId: id, selectionNonce: live.current.selectionNonce + 1 });
      selectedRef.current = id;
      writeStorage(STORAGE_KEYS.selectedPrism, id);
      monitoringRef.current.reset();
      bump();
    },
    [patch, live, bump],
  );

  // Switching from another tab changes the view after selectPrism's render, so tell the chat explicitly.
  const openPrismView = useCallback(
    (prism: Prism) => {
      selectPrism(prism.id);
      appRef.current.setActiveTab(isWorking(prism) ? "agent" : "prisms");
      if (isWorking(prism)) emit("open-agent", { prism });
      appRef.current.routes.prism(prism);
    },
    [selectPrism],
  );

  const replacePrism = useCallback(
    (prism: Prism, options: { render?: boolean } = {}) => {
      patch({ prisms: live.current.prisms.map((item) => (item.id === prism.id ? prism : item)) });
      if (options.render !== false) bump();
    },
    [patch, live, bump],
  );

  const addAndSelect = useCallback(
    (prism: Prism) => {
      patch({ prisms: [prism, ...live.current.prisms.filter((item) => item.id !== prism.id)] });
      selectPrism(prism.id);
      appRef.current.setActiveTab("prisms");
    },
    [patch, live, selectPrism],
  );

  const clearSelection = useCallback(
    (id: string) => {
      if (live.current.selectedId !== id) return;
      patch({ selectedId: null });
      selectedRef.current = null;
      writeStorage(STORAGE_KEYS.selectedPrism, null);
    },
    [patch, live],
  );

  const deletePrism = useCallback(
    async (prism: Prism) => {
      const confirmed = await appRef.current.askDialog({
        title: `Delete ${prism.name}?`,
        message: "This removes the Prism, its chats and its saved logins for good. It cannot be undone.",
        confirmLabel: "Delete Prism",
        danger: true,
      });
      if (!confirmed) return;
      try {
        await agentApi(`/api/v2/prisms/${prism.id}`, { method: "DELETE" });
        clearSelection(prism.id);
        setStatus(`${prism.name} deleted.`);
        await loadPrisms();
      } catch (error) {
        setStatus(errorMessage(error), true);
        await loadPrisms();
      }
    },
    [clearSelection, setStatus, loadPrisms],
  );

  const archivePrism = useCallback(
    async (prism: Prism, alreadyConfirmed = false) => {
      if (isArchived(prism)) return deletePrism(prism);
      const confirmed =
        alreadyConfirmed ||
        (await appRef.current.askDialog({
          title: `Archive ${prism.name}?`,
          message: "It will be hidden from the default directory. Its audit history remains intact.",
          confirmLabel: "Archive Prism",
          danger: true,
        }));
      if (!confirmed) return;
      try {
        await agentApi(`/api/v2/prisms/${prism.id}/archive`, {
          method: "POST",
          ...jsonBody({ expected_lifecycle_version: prism.lifecycle_version }),
        });
        clearSelection(prism.id);
        setStatus(`${prism.name} archived.`);
        await loadPrisms();
      } catch (error) {
        setStatus(errorMessage(error), true);
        await loadPrisms();
      }
    },
    [deletePrism, clearSelection, setStatus, loadPrisms],
  );

  const toggleArchived = useCallback(() => {
    const next = !live.current.includeArchived;
    patch({ includeArchived: next, archivedPressed: next });
    void loadPrisms();
  }, [patch, live, loadPrisms]);

  // Keep the URL and visible tab in step with the selected Prism after every list render (old syncView).
  useEffect(() => {
    const { prisms, selectedId } = live.current;
    const prism = prisms.find((item) => item.id === selectedId);
    const view = appRef.current.activeTab;
    if (!prism || (view !== "prisms" && view !== "agent")) return;
    appRef.current.routes.prism(prism, true);
    if (isWorking(prism)) {
      if (view !== "agent") appRef.current.setActiveTab("agent");
      emit("open-agent", { prism });
    } else if (view === "agent") appRef.current.setActiveTab("prisms");
  }, [state.renderTick, live]);

  // Page-level commands (editor, dialogs) are registered by PrismsPage.
  const commands = useRef<Partial<PageCommands>>({});
  const registerCommands = useCallback((next: PageCommands) => {
    commands.current = next;
    return () => {
      if (commands.current === next) commands.current = {};
    };
  }, []);

  const runAction = useCallback((action: PrismAction) => {
    const handlers: Record<PrismAction, () => void> = {
      "prism-policy-button": () => void monitoringRef.current.openPolicy(),
      "prism-sync-button": () => void monitoringRef.current.syncActivity(),
      "prism-trigger-button": () => commands.current.openTrigger?.(),
      "prism-notify-button": () => commands.current.openNotify?.(),
      "prism-health-button": () => commands.current.openHealth?.(),
    };
    handlers[action]();
  }, []);

  /* Teams updates poller and browser alerts (old prism-updates.js). */
  const refreshSummaries = useCallback(async () => {
    const rows = await agentApi<PrismUpdateSummary[]>("/api/v2/prisms/updates/summary");
    emit("updates", { summaries: new Map(rows.map((row) => [row.prism_id, row])) });
  }, []);

  const deliver = useCallback(async () => {
    // Never claim without permission: a claim is the one attempt, so it must be able to succeed.
    if (notificationPermission() !== "granted") return;
    const { notification } = await agentApi<{ notification: ClaimedNotification | null }>("/api/v2/prisms/notifications/claim", {
      method: "POST",
      ...jsonBody({ client_id: clientId() }),
    });
    if (!notification) return;
    let result = "delivered";
    try {
      const prism = live.current.prisms.find((item) => item.id === notification.prism_id);
      const icon = await prismLogoIcon(prismColorKey(prism || { id: notification.prism_id }));
      const shown = new Notification(notification.title, { body: notification.body, tag: notification.tag, icon });
      shown.onclick = () => {
        window.focus();
        emit("open-prism", { id: notification.prism_id });
        shown.close();
      };
    } catch {
      result = "error";
    }
    await agentApi(`/api/v2/prisms/notifications/${notification.notification_id}/result`, {
      method: "POST",
      ...jsonBody({ client_id: clientId(), result }),
    });
  }, [live]);

  const busy = useRef(false);
  const tick = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      await agentApi("/api/v2/prisms/notifications/presence", { method: "POST", ...jsonBody({ client_id: clientId() }) });
      await refreshSummaries();
      await deliver();
    } catch {
      // Updates and alerts are additive; a failed poll never blocks the workspace and retries next tick.
    } finally {
      busy.current = false;
    }
  }, [refreshSummaries, deliver]);

  const timer = useRef<number | null>(null);
  useEffect(() => {
    if (!enabled) return undefined;
    void loadPrisms();
    void tick();
    timer.current = window.setInterval(() => void tick(), POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible" && timer.current !== null) void tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      if (timer.current !== null) window.clearInterval(timer.current);
      timer.current = null;
    };
  }, [enabled, loadPrisms, tick]);

  useBusEvent("prisms-changed", () => void loadPrisms());
  useBusEvent("updates-refresh", () => void refreshSummaries().catch(() => {}));
  useBusEvent("updates", ({ summaries }) => {
    patch({ summaries: summaries as ReadonlyMap<string, PrismUpdateSummary> });
    bump();
    void refreshPrismList();
  });
  useBusEvent("open-prism-route", ({ prism }) => {
    const routed = prism as Prism;
    if (isArchived(routed)) patch({ includeArchived: true });
    patch({ prisms: [routed, ...live.current.prisms.filter((item) => item.id !== routed.id)] });
    openPrismView(routed);
  });
  useBusEvent("open-prism", ({ id }) => {
    const prism = live.current.prisms.find((item) => item.id === id);
    if (prism) openPrismView(prism);
  });
  useBusEvent("search-result", async ({ prismId, message }) => {
    let prism = live.current.prisms.find((item) => item.id === prismId);
    if (!prism) {
      await loadPrisms();
      prism = live.current.prisms.find((item) => item.id === prismId);
    }
    if (!prism) {
      setStatus("This Prism is no longer available.", true);
      return;
    }
    openPrismView(prism);
    if (message && isWorking(prism)) emit("open-agent-message", { prism, message });
  });
  useBusEvent("prism-updated", ({ prism }) => {
    patch({ prisms: live.current.prisms.map((item) => (item.id === prism.id ? ({ ...item, ...prism } as Prism) : item)) });
    bump();
  });
  useBusEvent("archive-confirmed", ({ id }) => {
    const prism = live.current.prisms.find((item) => item.id === id);
    if (prism) void archivePrism(prism, true);
  });
  useBusEvent("edit-organization", ({ prism }) => {
    if (prism) commands.current.openEditor?.(prism as Prism);
  });
  useBusEvent("scope-open", () => void monitoringRef.current.openPolicy());

  const selectedPrism = useMemo(() => state.prisms.find((item) => item.id === state.selectedId), [state.prisms, state.selectedId]);

  const reload = useCallback(() => loadPrisms(), [loadPrisms]);
  const publicValue = useMemo<PrismsApi>(
    () => ({
      prisms: state.prisms as PrismLike[],
      loading: state.loading,
      selectedId: state.selectedId,
      reload,
      summaries: state.summaries,
      runAction,
    }),
    [state.prisms, state.loading, state.selectedId, state.summaries, reload, runAction],
  );

  const internal: PrismsInternal = {
    prisms: state.prisms,
    loading: state.loading,
    selectedId: state.selectedId,
    selectedPrism,
    summaries: state.summaries,
    archivedPressed: state.archivedPressed,
    selectionNonce: state.selectionNonce,
    loadTick: state.loadTick,
    prismsRef,
    selectedRef,
    monitoring,
    loadPrisms,
    toggleArchived,
    openPrismView,
    selectPrism,
    archivePrism,
    replacePrism,
    addAndSelect,
    registerCommands,
    commands,
  };

  return (
    <PrismsContext.Provider value={publicValue}>
      <PrismsInternalContext.Provider value={internal}>{children}</PrismsInternalContext.Provider>
    </PrismsContext.Provider>
  );
}
