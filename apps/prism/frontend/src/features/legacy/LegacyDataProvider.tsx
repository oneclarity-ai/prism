import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { useBusEvent } from "@/lib/events";
import { setNavCount } from "@/lib/nav-counts";
import { today } from "./format";
import {
  EMPTY_DATASET,
  type AgentFoundation,
  type Journey,
  type LegacyAction,
  type LegacyDataset,
  type MemoryEpisode,
} from "./types";

export interface LegacyDataValue {
  data: LegacyDataset;
  /** `false` until the first full load finished (the old static placeholders show until then). */
  loaded: boolean;
  loading: boolean;
  /** Increments after every successful load; forms keyed on it reset like the old `renderSelectedForm()`. */
  version: number;
  /** `null` hides the "Prism activity" panel (v2.1 foundation unavailable). */
  foundation: AgentFoundation | null;
  reload: () => Promise<void>;
  setJourneys: (journeys: Journey[]) => void;
  runAction: (action: LegacyAction, id: string) => Promise<void>;
  nameFor: (id: string | null | undefined) => string;
  recordOpen: boolean;
  openRecord: () => void;
  closeRecord: () => void;
  revisionFor: string | null;
  openRevision: (commitmentId: string) => void;
  closeRevision: () => void;
}

const noop = async () => {};
const LegacyContext = createContext<LegacyDataValue>({
  data: EMPTY_DATASET,
  loaded: false,
  loading: false,
  version: 0,
  foundation: null,
  reload: noop,
  setJourneys: () => {},
  runAction: noop,
  nameFor: () => "Unassigned",
  recordOpen: false,
  openRecord: () => {},
  closeRecord: () => {},
  revisionFor: null,
  openRevision: () => {},
  closeRevision: () => {},
});

export const useLegacyData = (): LegacyDataValue => useContext(LegacyContext);

type Page<T> = { items: T[]; total: number };

const FAILED_HINT = ". Check that the API and database are running.";

export function LegacyDataProvider({ children }: { children: ReactNode }) {
  const app = useApp();
  const appRef = useRef(app);
  appRef.current = app;
  const [data, setData] = useState<LegacyDataset>(EMPTY_DATASET);
  const dataRef = useRef(data);
  dataRef.current = data;
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [version, setVersion] = useState(0);
  const [foundation, setFoundation] = useState<AgentFoundation | null>(null);
  const [recordOpen, setRecordOpen] = useState(false);
  const [revisionFor, setRevisionFor] = useState<string | null>(null);
  const pending = useRef(0);

  const renderFoundation = useCallback((next: AgentFoundation) => {
    setFoundation(next);
    setNavCount("agent", next.pending_approvals);
  }, []);

  const refreshFoundation = useCallback(
    () =>
      agentApi<AgentFoundation>("/api/v2/agent/foundation")
        .then(renderFoundation)
        .catch(() => {}),
    [renderFoundation],
  );

  const reload = useCallback(async () => {
    pending.current += 1;
    setLoading(true);
    agentApi<AgentFoundation>("/api/v2/agent/foundation")
      .then(renderFoundation)
      .catch(() => setFoundation(null));
    try {
      const [employees, projects, tasks, updates, blockers, commitments, escalations, findings, journeys, knowledge, memoryFacts, memoryEpisodes, attention, brief] =
        await Promise.all([
          agentApi<Page<LegacyDataset["employees"][number]>>("/api/v1/employees?limit=100&is_active=true"),
          agentApi<Page<LegacyDataset["projects"][number]>>("/api/v1/projects?limit=100"),
          agentApi<Page<LegacyDataset["tasks"][number]>>("/api/v1/tasks?limit=100"),
          agentApi<Page<LegacyDataset["updates"][number]>>("/api/v1/daily-updates?limit=100&update_date=" + today()),
          agentApi<Page<LegacyDataset["blockers"][number]>>("/api/v1/blockers?limit=100&status=open"),
          agentApi<Page<LegacyDataset["commitments"][number]>>("/api/v1/commitments?limit=100&status=open"),
          agentApi<Page<LegacyDataset["escalations"][number]>>("/api/v1/escalations?limit=100&status=open"),
          agentApi<LegacyDataset["findings"]>("/api/v1/management/rule-findings"),
          agentApi<LegacyDataset["journeys"]>("/api/v1/management/journeys"),
          agentApi<Page<LegacyDataset["knowledge"][number]>>("/api/v1/management-context?limit=100"),
          agentApi<Page<LegacyDataset["memoryFacts"][number]>>("/api/v1/memory/facts?limit=12&status=current"),
          agentApi<MemoryEpisode[]>("/api/v1/memory/episodes?limit=8"),
          agentApi<LegacyDataset["attention"]>("/api/v2/management/attention"),
          agentApi<NonNullable<LegacyDataset["brief"]>>("/api/v2/management/brief/daily"),
        ]);
      setData({
        employees: employees.items,
        projects: projects.items,
        tasks: tasks.items,
        updates: updates.items,
        blockers: blockers.items,
        commitments: commitments.items,
        escalations: escalations.items,
        findings,
        journeys,
        knowledge: knowledge.items,
        memoryFacts: memoryFacts.items,
        memoryEpisodes,
        attention,
        brief,
        totals: {
          employees: employees.total,
          updates: updates.total,
          blockers: blockers.total,
          commitments: commitments.total,
          escalations: escalations.total,
        },
      });
      setNavCount("today", attention.length);
      setNavCount("work", blockers.total + commitments.total + escalations.total);
      setLoaded(true);
      setVersion((value) => value + 1);
    } catch (error) {
      appRef.current.setStatus(errorMessage(error) + FAILED_HINT, true);
    } finally {
      pending.current -= 1;
      if (pending.current === 0) setLoading(false);
    }
  }, [renderFoundation]);

  useEffect(() => {
    void reload();
  }, [reload, app.refreshKey]);

  useBusEvent("agent-changed", () => {
    void refreshFoundation();
  });

  const nameFor = useCallback(
    (id: string | null | undefined) => dataRef.current.employees.find((employee) => employee.id === id)?.name ?? "Unassigned",
    [],
  );

  const setJourneys = useCallback((journeys: Journey[]) => setData((current) => ({ ...current, journeys })), []);

  const runAction = useCallback(
    async (action: LegacyAction, id: string) => {
      const { setStatus, askDialog } = appRef.current;
      const current = dataRef.current;
      const recordMessageIntent = async (employeeId: string, content: string) => {
        await agentApi("/api/v1/message-intents", {
          method: "POST",
          ...jsonBody({ employee_id: employeeId, channel: "teams", content }),
        });
        setStatus("Teams follow-up recorded locally. It has not been sent.");
      };
      try {
        if (action === "daily-reminder") {
          const employee = current.employees.find((item) => item.id === id);
          if (!employee) throw new Error("Team member not found.");
          await recordMessageIntent(
            id,
            `Hi ${employee.name}, please share your daily update for today: what you completed, what you will deliver today, and any blockers.`,
          );
        }
        if (action === "blocker-follow-up") {
          const blocker = current.blockers.find((item) => item.id === id);
          const owner = current.employees.find((item) => item.id === blocker?.dependency_owner_id);
          if (!blocker || !owner) throw new Error("Dependency owner not found.");
          await recordMessageIntent(
            owner.id,
            `Hi ${owner.name}, ${nameFor(blocker.blocked_employee_id)} is blocked: ${blocker.description} Please share a specific ETA.`,
          );
        }
        if (action === "resolve-blocker") {
          if (!(await askDialog({ title: "Mark blocker as resolved?", confirmLabel: "Resolve" }))) return;
          await agentApi(`/api/v1/blockers/${id}`, { method: "PATCH", ...jsonBody({ status: "resolved" }) });
          setStatus("Blocker marked as resolved. Update the task status separately when work resumes.");
        }
        if (action === "mark-missed") {
          const reason = await askDialog({
            title: "Mark commitment as missed?",
            message: "You can leave the reason blank and add it with a revised ETA later.",
            confirmLabel: "Mark missed",
            field: { label: "Why was it missed?" },
          });
          if (reason === null) return;
          const text = reason === true ? "" : reason.trim();
          await agentApi(`/api/v1/commitments/${id}/mark-missed`, { method: "POST", ...jsonBody(text ? { reason: text } : {}) });
          setStatus("Commitment marked as missed. It remains in its history.");
        }
        if (action === "revise-commitment") {
          setRevisionFor(id);
          return;
        }
        if (action === "acknowledge-escalation") {
          await agentApi(`/api/v1/escalations/${id}/acknowledge`, { method: "POST" });
          setStatus("Escalation acknowledged.");
        }
        if (action === "resolve-escalation") {
          if (!(await askDialog({ title: "Resolve this escalation?", confirmLabel: "Resolve" }))) return;
          await agentApi(`/api/v1/escalations/${id}/resolve`, { method: "POST" });
          setStatus("Escalation resolved.");
        }
        await reload();
      } catch (error) {
        setStatus(errorMessage(error), true);
      }
    },
    [nameFor, reload],
  );

  const value = useMemo<LegacyDataValue>(
    () => ({
      data,
      loaded,
      loading,
      version,
      foundation,
      reload,
      setJourneys,
      runAction,
      nameFor,
      recordOpen,
      openRecord: () => setRecordOpen(true),
      closeRecord: () => setRecordOpen(false),
      revisionFor,
      openRevision: setRevisionFor,
      closeRevision: () => setRevisionFor(null),
    }),
    [data, loaded, loading, version, foundation, reload, setJourneys, runAction, nameFor, recordOpen, revisionFor],
  );

  return <LegacyContext.Provider value={value}>{children}</LegacyContext.Provider>;
}
