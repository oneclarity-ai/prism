import { useCallback, useEffect, useRef, type RefObject } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useLiveState } from "./live";
import type {
  ActivityPage,
  Loadable,
  ManualRun,
  ObservationsPage,
  RunsPage,
  TeamsPolicy,
  TeamsSource,
  TriggerPolicy,
} from "./types";

export interface PendingPolicy {
  mode: TeamsPolicy["mode"];
  externalIds: string[];
}

export interface MonitoringState {
  sourcePolicy: Loadable<TeamsPolicy>;
  activity: Loadable<ActivityPage>;
  observations: Loadable<ObservationsPage>;
  triggerPolicy: Loadable<TriggerPolicy>;
  runs: RunsPage | null;
  pendingPolicy: PendingPolicy | null;
  catalog: TeamsSource[];
  catalogLoading: boolean;
  policyError: string;
  policySearch: string;
  policySave: "idle" | "saving" | "saved";
  syncing: boolean;
}

const INITIAL: MonitoringState = {
  sourcePolicy: null,
  activity: null,
  observations: null,
  triggerPolicy: null,
  runs: null,
  pendingPolicy: null,
  catalog: [],
  catalogLoading: false,
  policyError: "",
  policySearch: "",
  policySave: "idle",
  syncing: false,
};

export interface MonitoringApi extends MonitoringState {
  reset: () => void;
  loadTeamsMonitoring: () => Promise<void>;
  loadRunStatus: () => Promise<void>;
  loadCatalog: () => Promise<TeamsSource[]>;
  openPolicy: () => Promise<void>;
  closePolicy: () => Promise<void>;
  savePolicy: () => Promise<void>;
  syncActivity: () => Promise<void>;
  setPolicyMode: (mode: TeamsPolicy["mode"]) => void;
  togglePolicySource: (externalId: string, checked: boolean) => void;
  setPolicySearch: (value: string) => void;
  setTriggerPolicy: (policy: TriggerPolicy) => void;
  /** Latest values for async callers (dialogs opened from a click read these, not a stale render). */
  live: RefObject<MonitoringState>;
}

const isObject = <T,>(value: Loadable<T> | null): value is T => Boolean(value) && typeof value === "object";

interface Host {
  selectedRef: RefObject<string | null>;
  hasSelectedPrism: () => boolean;
  setStatus: (message: string | null, isError?: boolean) => void;
}

/** Teams monitoring scope, activity, observations, schedule and runs of the selected Prism (old prism-directory.js). */
export function useMonitoring({ selectedRef, hasSelectedPrism, setStatus }: Host): MonitoringApi {
  const [state, patch, live] = useLiveState<MonitoringState>(INITIAL);
  const savedTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(savedTimer.current), []);

  const loadTeamsMonitoring = useCallback(async () => {
    const prismId = selectedRef.current;
    if (!prismId) return;
    patch({ sourcePolicy: "loading" });
    try {
      const [policy, activity, observations] = await Promise.all([
        agentApi<TeamsPolicy>(`/api/v2/prisms/${prismId}/teams-policy`),
        agentApi<ActivityPage>(`/api/v2/prisms/${prismId}/teams-activity`),
        agentApi<ObservationsPage>(`/api/v2/prisms/${prismId}/observations`),
      ]);
      if (selectedRef.current === prismId) patch({ sourcePolicy: policy, activity, observations });
    } catch (error) {
      if (selectedRef.current === prismId) {
        patch({ sourcePolicy: "error" });
        setStatus(errorMessage(error), true);
      }
    }
    if (selectedRef.current === prismId && live.current.sourcePolicy === null) void loadTeamsMonitoring();
  }, [patch, live, selectedRef, setStatus]);

  const loadRunStatus = useCallback(async () => {
    const prismId = selectedRef.current;
    if (!prismId) return;
    patch({ triggerPolicy: "loading" });
    try {
      const [policy, runs] = await Promise.all([
        agentApi<TriggerPolicy>(`/api/v2/prisms/${prismId}/trigger-policy`),
        agentApi<RunsPage>(`/api/v2/prisms/${prismId}/runs`),
      ]);
      if (selectedRef.current === prismId) patch({ triggerPolicy: policy, runs });
    } catch (error) {
      if (selectedRef.current === prismId) {
        patch({ triggerPolicy: "error" });
        setStatus(errorMessage(error), true);
      }
    }
  }, [patch, selectedRef, setStatus]);

  const loadCatalog = useCallback(async () => {
    const result = await agentApi<{ items?: TeamsSource[] }>("/api/v2/agent/sources/teams");
    const catalog = result.items || [];
    patch({ catalog });
    return catalog;
  }, [patch]);

  const openPolicy = useCallback(async () => {
    if (!hasSelectedPrism()) return;
    patch({ policyError: "" });
    if (!isObject(live.current.sourcePolicy)) await loadTeamsMonitoring();
    const policy = live.current.sourcePolicy;
    if (!isObject(policy)) {
      patch({ policyError: "Teams monitoring scope is unavailable. Try again." });
      return;
    }
    // The saved choice shows at once; the (slow) chat list fills in below it.
    patch({ pendingPolicy: { mode: policy.mode, externalIds: (policy.rules || []).map((rule) => rule.external_id) }, policySearch: "" });
    if (live.current.catalog.length) return;
    patch({ catalogLoading: true });
    try {
      await loadCatalog();
    } catch {
      patch({ policyError: "Could not load accessible Teams chats." });
    } finally {
      patch({ catalogLoading: false });
    }
  }, [hasSelectedPrism, patch, live, loadTeamsMonitoring, loadCatalog]);

  // The scope editor lives in the chat's settings drawer; cancelling just reloads the saved scope.
  const closePolicy = useCallback(async () => {
    patch({ pendingPolicy: null });
    await openPolicy();
  }, [patch, openPolicy]);

  const savePolicy = useCallback(async () => {
    const prismId = selectedRef.current;
    const { sourcePolicy: policy, pendingPolicy: pending } = live.current;
    if (!prismId || !hasSelectedPrism() || !isObject(policy) || !pending) return;
    patch({ policySave: "saving", policyError: "" });
    try {
      const saved = await agentApi<TeamsPolicy>(`/api/v2/prisms/${prismId}/teams-policy`, {
        method: "PUT",
        ...jsonBody({
          expected_revision: policy.revision,
          mode: pending.mode,
          external_ids: pending.mode === "all_chats" ? [] : pending.externalIds,
        }),
      });
      patch({ sourcePolicy: saved, pendingPolicy: null });
      setStatus("Teams monitoring scope saved. It applies before Prism reads chats.");
      // Show the saved state, so it is plain that the choice was kept.
      patch({
        pendingPolicy: { mode: saved.mode, externalIds: (saved.rules || []).map((rule) => rule.external_id) },
        policySave: "saved",
      });
      window.clearTimeout(savedTimer.current);
      savedTimer.current = window.setTimeout(() => patch({ policySave: "idle" }), 1500);
      return;
    } catch (error) {
      patch({ policyError: errorMessage(error) });
      await loadTeamsMonitoring();
    }
    patch({ policySave: "idle" });
  }, [selectedRef, live, hasSelectedPrism, patch, setStatus, loadTeamsMonitoring]);

  const syncActivity = useCallback(async () => {
    const prismId = selectedRef.current;
    if (!prismId || !hasSelectedPrism()) return;
    patch({ syncing: true });
    try {
      const run = await agentApi<ManualRun>(`/api/v2/prisms/${prismId}/runs/manual`, { method: "POST", body: "{}" });
      if (run.state === "queued" || run.state === "running") {
        setStatus("Monitoring run started. Its status will appear in the pinned Teams monitoring panel.");
      } else {
        const result = run.result || {};
        const degraded = Boolean(run.safe_error || result.status === "degraded");
        const scanned = result.scanned_chats || 0;
        const created = result.created_events || 0;
        setStatus(
          degraded
            ? `Monitoring run is degraded: ${run.safe_error || "try again shortly"}`
            : `Checked ${scanned} Teams ${result.scanned_chats === 1 ? "chat" : "chats"}; found ${created} new activity ${created === 1 ? "event" : "events"}.`,
          degraded,
        );
      }
      await Promise.all([loadTeamsMonitoring(), loadRunStatus()]);
    } catch (error) {
      setStatus(errorMessage(error), true);
      await Promise.all([loadTeamsMonitoring(), loadRunStatus()]);
    } finally {
      patch({ syncing: false });
    }
  }, [selectedRef, hasSelectedPrism, patch, setStatus, loadTeamsMonitoring, loadRunStatus]);

  const reset = useCallback(
    () =>
      patch({
        sourcePolicy: null,
        activity: null,
        observations: null,
        triggerPolicy: null,
        runs: null,
      }),
    [patch],
  );

  const setPolicyMode = useCallback(
    (mode: TeamsPolicy["mode"]) => {
      const pending = live.current.pendingPolicy;
      if (!pending) return;
      patch({ pendingPolicy: { ...pending, mode }, policyError: "" });
    },
    [live, patch],
  );

  const togglePolicySource = useCallback(
    (externalId: string, checked: boolean) => {
      const pending = live.current.pendingPolicy;
      if (!pending) return;
      const ids = new Set(pending.externalIds);
      if (checked) ids.add(externalId);
      else ids.delete(externalId);
      patch({ pendingPolicy: { ...pending, externalIds: [...ids] } });
    },
    [live, patch],
  );

  const setPolicySearch = useCallback((policySearch: string) => patch({ policySearch }), [patch]);
  const setTriggerPolicy = useCallback((triggerPolicy: TriggerPolicy) => patch({ triggerPolicy }), [patch]);

  return {
    ...state,
    live,
    reset,
    loadTeamsMonitoring,
    loadRunStatus,
    loadCatalog,
    openPolicy,
    closePolicy,
    savePolicy,
    syncActivity,
    setPolicyMode,
    togglePolicySource,
    setPolicySearch,
    setTriggerPolicy,
  };
}
