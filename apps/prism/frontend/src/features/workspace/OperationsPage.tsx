import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button, Icon, Panel, StatusChip, useFormDialog } from "@/components/ui";
import { SkillLibrary } from "@/features/prisms/SkillLibrary";
import { usePrisms } from "@/features/prisms/PrismsContext";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit, useBusEvent } from "@/lib/events";
import { money, time } from "@/lib/format";
import { setNavCount } from "@/lib/nav-counts";
import { prismOrganization } from "@/lib/prism-organization";
import { BrainPage, useBrainEditor } from "./BrainPage";
import { PrismDetail } from "./PrismDetail";
import { RunDetail } from "./RunDetail";
import { brainApi, brainProposedCount } from "./brain";
import { WORKSPACE_PAGES } from "./constants";
import { AgentsPage, agentsActions } from "./pages/Agents";
import { BugsPage } from "./pages/Bugs";
import { DashboardPage, dashboardActions } from "./pages/Dashboard";
import { OrganizationPage } from "./pages/Organization";
import { ApprovalsWorkspacePage } from "./pages/OperationsApprovals";
import { RunsPage } from "./pages/Runs";
import { SecretsPage, TargetsPage, secretsActions, targetsActions } from "./pages/Setup";
import { TasksPage, tasksActions } from "./pages/Tasks";
import { UsagePage, usageActions } from "./pages/Usage";
import type { Filters, PageContext } from "./pages/shared";
import type { Agent, Analytics, BrainEntry, EngineOverview, ManagedApproval, OrgMember, PrismTool, Secret, Target, Task, WorkspaceData } from "./types";
import { getWorkspaceNav, setPrismTab, showRunNav, useWorkspaceNav, useWorkspaceNavigate } from "./workspace-nav";

type Mode =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "page" }
  | { kind: "run"; runId: string };

interface OrganizationAnswer {
  owner_name: string;
  members: OrgMember[];
}

const EMPTY_OVERVIEW: EngineOverview = { agents: [], positions: [], tasks: [], runs: [], approvals: [], bugs: [] };
/** Pages that still work when the computer service is unreachable. */
const ENGINE_FREE = ["positions", "prism", "brain", "skills"];
const CACHE_MS = 30000;

/** State that async code reads after an `await` (a ref) and the view renders from (React state). */
function useMirrored<T>(initial: T) {
  const [value, setValue] = useState(initial);
  const ref = useRef(initial);
  const set = useCallback((next: T) => {
    ref.current = next;
    setValue(next);
  }, []);
  return [value, set, ref] as const;
}

function greeting(name: string | undefined): string {
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  return name && name !== "Microsoft account" ? `${hello}, ${name.split(" ")[0]}` : hello;
}

function AgentDialog({ agent, onClose }: { agent: Agent; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  const rows: Array<[string, unknown]> = [
    ["Role", agent.role],
    ["Model", agent.model || "Default model"],
    ["Runtime", agent.runtime],
    ["Run budget", money(agent.run_budget_usd)],
    ["Monthly budget", money(agent.monthly_budget_usd)],
    ["Created", time(agent.created_at)],
  ];
  return createPortal(
    <dialog ref={ref} className="workspace-dialog" onClose={onClose}>
      <div className="workspace-form">
        <Panel title={agent.name} subtitle={agent.description ?? ""} />
        <StatusChip value={agent.status} />
        {rows.map(([title, value]) => (
          <p key={title}>{`${title}: ${value}`}</p>
        ))}
        <Button text="Close" onClick={() => ref.current?.close()} />
      </div>
    </dialog>,
    document.body,
  );
}

/** Prisms page views: the card grid or the org chart. */
function ViewToggle({ page, onChange }: { page: string; onChange: (view: string) => void }) {
  return (
    <div className="workspace-status-tabs workspace-view-toggle" role="group" aria-label="Prisms view">
      {(
        [
          ["agents", "Cards"],
          ["positions", "Org chart"],
        ] as const
      ).map(([key, text]) => (
        <Button key={key} className={`workspace-status-tab${key === page ? " active" : ""}`} text={text} aria-pressed={key === page} onClick={() => onChange(key)}>
          <span className="workspace-tab-count" />
        </Button>
      ))}
    </div>
  );
}

/** Inner content of `data-tab="operations"`: the workspace pages, run detail and Prism detail. */
export function OperationsPage() {
  const app = useApp();
  const latest = useRef(app);
  latest.current = app;
  const visible = app.activeTab === "operations";
  const visibleRef = useRef(visible);
  visibleRef.current = visible;
  const { prisms: listed, loading: listLoading } = usePrisms();
  const nav = useWorkspaceNav();
  const navigate = useWorkspaceNavigate();
  const { openFormDialog } = useFormDialog();

  const [mode, setMode] = useState<Mode>({ kind: "idle" });
  const [data, setData, dataRef] = useMirrored<WorkspaceData | null>(null);
  const [members, setMembers, membersRef] = useMirrored<OrgMember[]>([]);
  const [brain, setBrain, brainRef] = useMirrored<BrainEntry[]>([]);
  const [managed, setManaged] = useState<ManagedApproval[]>([]);
  const [analytics, setAnalytics, analyticsRef] = useMirrored<Analytics | null>(null);
  const [prismData, setPrismData, prismRef] = useMirrored<OrgMember | null>(null);
  const [prismTools, setPrismTools] = useState<PrismTool[]>([]);
  const [revision, setRevision] = useState(0);
  const [filters, setFilters, filtersRef] = useMirrored<Record<string, Filters>>({});
  const [department, setDepartment, departmentRef] = useMirrored("");
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [agentDialog, setAgentDialog] = useState<Agent | null>(null);

  const listDeliveredRef = useRef(false);
  const requestRef = useRef(0);
  const pendingRef = useRef<Promise<WorkspaceData> | null>(null);
  const loadedAtRef = useRef(0);
  const adoptionTriedRef = useRef(false);
  const engineErrorRef = useRef<Error | null>(null);
  const ownerNameRef = useRef<string | undefined>(undefined);
  const analyticsKeyRef = useRef("");
  const refreshingRef = useRef(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const microsoft = app.microsoft;
  const accountName = microsoft?.is_connected && microsoft.connection ? (microsoft.connection.display_name ?? undefined) : undefined;
  const accountNameRef = useRef(accountName);
  accountNameRef.current = accountName;

  const currentFilters = (): Filters => filtersRef.current[getWorkspaceNav().page] ?? {};

  function syncHeading(): void {
    const a = latest.current;
    const n = getWorkspaceNav();
    const detail = prismRef.current?.id === n.prismId ? prismRef.current : null;
    a.routes.workspace({
      page: n.page,
      id: n.prismId ?? undefined,
      prism: detail || membersRef.current.find((item) => item.id === n.prismId),
      section: n.prismTab,
      runId: n.runId ?? undefined,
    });
    const [title, subtitle, icon] = WORKSPACE_PAGES[n.page];
    a.setPageHeading({ title: n.page === "overview" ? greeting(accountNameRef.current) : title, subtitle, icon });
  }

  function render(): void {
    syncHeading();
    const n = getWorkspaceNav();
    const prism = prismRef.current;
    if (n.page === "prism" && prism && prism.id === n.prismId) {
      latest.current.setPageHeading({ title: prism.name, subtitle: `${prism.job_role} · ${prism.department}`, icon: "" });
    }
    setMode({ kind: "page" });
  }

  function updateNavigation(next: WorkspaceData, entries: readonly BrainEntry[]): void {
    const prisms = next.organization.filter((item) => item.kind === "prism");
    setNavCount("workspace:brain", brainProposedCount(entries));
    setNavCount("workspace:agents", prisms.length);
    setNavCount("workspace:tasks", next.tasks.filter((item) => ["todo", "in_progress", "blocked"].includes(item.status)).length);
    setNavCount("workspace:approvals", next.approvals.filter((item) => item.status === "pending").length);
    const departments = new Set(prisms.map((item) => item.department).filter(Boolean));
    if (departmentRef.current && !departments.has(departmentRef.current)) setDepartment("");
  }

  const ensureData = useCallback(
    async function ensure(force = false): Promise<WorkspaceData> {
      if (pendingRef.current) return pendingRef.current;
      if (dataRef.current && !force && Date.now() - loadedAtRef.current < CACHE_MS) return dataRef.current;
      const promise = Promise.all([
        agentApi<EngineOverview>("/api/v2/operations/overview")
          .then((overview) => ({ overview, error: null as Error | null }))
          .catch((error: unknown) => ({ overview: EMPTY_OVERVIEW, error: error instanceof Error ? error : new Error(errorMessage(error)) })),
        agentApi<OrganizationAnswer>("/api/v2/prisms/organization"),
        brainApi.list().catch(() => brainRef.current),
      ])
        .then(([engine, organization, entries]) => {
          setBrain(entries);
          engineErrorRef.current = engine.error;
          ownerNameRef.current = organization.owner_name;
          // Once the shared Prism list (sidebar order) has arrived it wins, like the old `prism:list`.
          if (!listDeliveredRef.current) setMembers(organization.members);
          const next: WorkspaceData = {
            ...engine.overview,
            targets: engine.overview.targets ?? [],
            organization: prismOrganization(membersRef.current, [], [], organization.owner_name),
            secrets: dataRef.current?.secrets || [],
          };
          setData(next);
          loadedAtRef.current = Date.now();
          updateNavigationRef.current(next, entries);
          return next;
        })
        .then(async (next) => {
          // Every engine agent becomes a Prism, once, so a Prism is the only kind of agent.
          if (adoptionTriedRef.current || !next.agents?.length || engineErrorRef.current) return next;
          adoptionTriedRef.current = true;
          try {
            const adopted = await agentApi<unknown[]>("/api/v2/prisms/adopt-engine-agents", { method: "POST" });
            if (adopted.length) {
              emit("prisms-changed");
              pendingRef.current = null;
              return await ensure(true);
            }
          } catch {
            /* Adoption is retried on the next page load. */
          }
          return next;
        })
        .finally(() => {
          pendingRef.current = null;
        });
      pendingRef.current = promise;
      return promise;
    },
    // Everything the callback touches is a ref or a stable setter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const updateNavigationRef = useRef(updateNavigation);
  updateNavigationRef.current = updateNavigation;

  async function loadPrismDetail(): Promise<void> {
    const id = getWorkspaceNav().prismId;
    const [prism, tools] = await Promise.all([agentApi<OrgMember>(`/api/v2/prisms/${id}`), agentApi<{ tools: PrismTool[] }>(`/api/v2/prisms/${id}/tools`)]);
    setPrismData(prism);
    setPrismTools(tools.tools);
    setRevision((value) => value + 1);
  }

  async function loadAnalytics(): Promise<void> {
    const f = currentFilters();
    const days = f.days || "30";
    const agent = f.agent || "";
    const key = `${days}:${agent}`;
    if (analyticsKeyRef.current === key && analyticsRef.current) return;
    const params = new URLSearchParams({ days });
    if (agent) params.set("agent_id", agent);
    const result = await agentApi<Analytics>(`/api/v2/operations/analytics?${params}`);
    const now = currentFilters();
    if (getWorkspaceNav().page === "usage" && key === `${now.days || "30"}:${now.agent || ""}`) {
      setAnalytics(result);
      analyticsKeyRef.current = key;
    }
  }

  function openRun(runId: string): void {
    showRunNav(runId);
    setMode({ kind: "run", runId });
    syncHeading();
  }

  async function load(force = false): Promise<void> {
    const serial = ++requestRef.current;
    setMode({ kind: "loading" });
    syncHeading();
    try {
      await ensureData(force);
      if (serial !== requestRef.current || !visibleRef.current) return;
      const page = getWorkspaceNav().page;
      if (engineErrorRef.current && !ENGINE_FREE.includes(page)) throw engineErrorRef.current;
      if (page === "secrets" && dataRef.current) setData({ ...dataRef.current, secrets: await agentApi<Secret[]>("/api/v2/operations/secrets") });
      if (page === "prism") await loadPrismDetail();
      if (page === "brain") {
        const entries = await brainApi.list();
        setBrain(entries);
        if (dataRef.current) updateNavigation(dataRef.current, entries);
      }
      if (page === "approvals") setManaged(await agentApi<ManagedApproval[]>("/api/v2/work/approvals?limit=200"));
      if (page === "usage") await loadAnalytics();
      if (serial !== requestRef.current || !visibleRef.current) return;
      const after = getWorkspaceNav();
      if (after.page === "runs" && after.runId) {
        openRun(after.runId);
        return;
      }
      render();
    } catch (error) {
      if (serial !== requestRef.current || !visibleRef.current) return;
      setMode({ kind: "error", message: errorMessage(error) });
      syncHeading();
    }
  }
  const loadRef = useRef(load);
  loadRef.current = load;

  const refresh = (): Promise<void> => {
    analyticsKeyRef.current = "";
    return load(true);
  };

  // Load whenever the tab becomes visible or something navigated (old `prism:tab` + navigate).
  useEffect(() => {
    if (visible) void loadRef.current();
    else requestRef.current += 1;
  }, [visible, nav.token]);

  const v24 = app.modes.v24;
  useEffect(() => {
    if (v24 === true) ensureData().catch(() => {});
  }, [v24, ensureData]);
  const section = app.sidebarSection;
  useEffect(() => {
    if (section === "workspace" && v24 === true) ensureData().catch(() => {});
  }, [section, v24, ensureData]);

  // The shared Prism list replaces the organization members once it changes (old `prism:list`).
  useEffect(() => {
    if (listLoading) return;
    listDeliveredRef.current = true;
    const prisms = listed as unknown as OrgMember[];
    setMembers(prisms);
    const current = dataRef.current;
    if (!current) return;
    const next = { ...current, organization: prismOrganization(prisms, [], [], ownerNameRef.current) };
    setData(next);
    updateNavigationRef.current(next, brainRef.current);
  }, [listed, listLoading, setMembers, setData, dataRef, brainRef]);

  // Greeting changes once the Microsoft account name arrives.
  const lastName = useRef(accountName);
  useEffect(() => {
    if (lastName.current === accountName) return;
    lastName.current = accountName;
    if (visibleRef.current && getWorkspaceNav().page === "overview") syncHeading();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountName]);

  useBusEvent("workspace-navigate", (detail) => {
    if (detail.page === "positions") setDepartment("");
    navigate(detail.page, detail.id ?? null, detail.section, detail.runId ?? null);
  });

  // While an approval decision is in flight every button on the page is disabled.
  const disabledByBusy = useRef<HTMLButtonElement[]>([]);
  useEffect(() => {
    if (busy) {
      contentRef.current?.querySelectorAll("button").forEach((button) => {
        if (!button.disabled) {
          button.disabled = true;
          disabledByBusy.current.push(button);
        }
      });
    } else {
      disabledByBusy.current.forEach((button) => {
        button.disabled = false;
      });
      disabledByBusy.current = [];
    }
  }, [busy]);

  const openPrism = (prismId: string, runId: string | null = null): void => {
    const a = latest.current;
    if (!membersRef.current.some((item) => item.id === prismId)) {
      a.setStatus("That Prism is not available in the current list.", true);
      return;
    }
    emit("search-result", { prismId });
    if (runId) emit("focus-computer-run", { runId });
  };

  async function save(sectionName: string, item: { id: string } | null, values: object): Promise<void> {
    await agentApi(`/api/v2/operations/${sectionName}${item ? `/${item.id}` : ""}`, { method: item ? "PATCH" : "POST", ...jsonBody(values) });
    analyticsKeyRef.current = "";
    await load(true);
  }

  const editTask = (item: Task | null = null, defaults: { agent_id?: string } = {}): void => {
    const current = dataRef.current;
    if (!current) return;
    openFormDialog(
      item ? "Edit task" : "New task",
      [
        { name: "title", label: "Task", required: true, maxLength: 300, value: item?.title },
        { name: "goal", label: "Goal", type: "textarea", value: item?.goal },
        { name: "agent_id", label: "Prism", required: true, options: [["", "Choose a Prism"], ...current.agents.map((agent) => [agent.id, agent.name] as const)], value: item?.agent_id ?? defaults.agent_id },
        { name: "target_app_id", label: "Target app", options: [["", "No target"], ...current.targets.map((target) => [target.id, target.name] as const)], value: item?.target_app_id },
      ],
      (values) => save("tasks", item, { ...values, target_app_id: values.target_app_id || null }),
      { description: "Save the task here. Ask its Prism to prepare and start the work from your conversation." },
    );
  };
  const editTarget = (item: Target | null = null): void => {
    openFormDialog(
      item ? "Edit target app" : "Add target app",
      [
        { name: "name", label: "App name", required: true, maxLength: 200, value: item?.name },
        { name: "base_url", label: "Website URL", type: "url", required: true, value: item?.base_url, placeholder: "https://example.com" },
        {
          name: "environment",
          label: "Environment",
          options: [["local", "Local"], ["dev", "Development"], ["staging", "Staging"], ["production", "Production"]],
          value: item?.environment || "staging",
        },
        { name: "notes", label: "Notes", type: "textarea", value: item?.notes },
      ],
      (values) => save("targets", item, values),
    );
  };
  const editSecret = (): void => {
    openFormDialog(
      "New secret",
      [
        { name: "name", label: "Name", required: true, maxLength: 200 },
        { name: "scope", label: "Scope", required: true, maxLength: 200, value: "general" },
        { name: "value", label: "Value", type: "password", required: true },
      ],
      (values) => save("secrets", null, values),
      { description: "The value is stored encrypted by the computer service and cannot be read back." },
    );
  };
  const remove: PageContext["remove"] = async (sectionName, item) => {
    const a = latest.current;
    const confirmed = await a.askDialog({
      title: `Delete ${item.title || item.name}?`,
      message: sectionName === "positions" ? "This removes the position. Its reporting positions will follow the computer service's organization rules." : "This removes this record from the connected computer service.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await agentApi(`/api/v2/operations/${sectionName}/${item.id}`, { method: "DELETE" });
      await load(true);
    } catch (error) {
      a.setStatus(errorMessage(error), true);
    }
  };
  const decide: PageContext["decide"] = async (item, decision) => {
    if (refreshingRef.current) return;
    const a = latest.current;
    const confirmed = await a.askDialog({
      title: `${decision === "approve" ? "Approve" : "Reject"} this action?`,
      message: item.payload?.summary || item.payload?.title,
      confirmLabel: decision === "approve" ? "Approve" : "Reject",
    });
    if (!confirmed) return;
    refreshingRef.current = true;
    setBusy(true);
    try {
      await agentApi(`/api/v2/qa/approvals/${item.id}/decision`, { method: "POST", ...jsonBody({ decision }) });
      await load(true);
    } catch (error) {
      a.setStatus(errorMessage(error), true);
      render();
    } finally {
      refreshingRef.current = false;
      setBusy(false);
    }
  };
  const linkedPrism = (agent: Agent): OrgMember | undefined =>
    members.find((prism) => agent.key === `prism-${prism.id.slice(0, 8)}` || agent.name?.replace(/^Prism:\s*/i, "").toLowerCase() === prism.name.toLowerCase());
  const openAgent = (agent: Agent): void => {
    const prism = linkedPrism(agent);
    if (prism) navigate("prism", prism.id);
    else setAgentDialog(agent);
  };
  const filter: PageContext["filter"] = (key, value, remote = false) => {
    const page = getWorkspaceNav().page;
    setFilters({ ...filtersRef.current, [page]: { ...(filtersRef.current[page] ?? {}), [key]: value } });
    if (remote) void load();
  };
  const brainEdit = useBrainEditor(() => load(true));

  const ctx: PageContext | null = data && {
    data,
    prisms: members,
    analytics,
    filters: filters[nav.page] ?? {},
    managedApprovals: managed,
    busy,
    navigate,
    openRun,
    openPrism,
    openAgent,
    editTask,
    editTarget,
    editSecret,
    remove,
    decide,
    createPrism: () => document.getElementById("prism-create-button")?.click(),
    filter,
  };

  const refreshButton = <Button key="refresh" glyph="refresh-cw" className="icon-button" title="Refresh workspace" onClick={() => void refresh()} />;
  const viewToggle = (
    <ViewToggle
      key="toggle"
      page={nav.page}
      onChange={(view) => {
        if (view === "positions") setDepartment("");
        navigate(view);
      }}
    />
  );

  let actions: ReactNode = null;
  let body: ReactNode = null;
  if (ctx) {
    switch (nav.page) {
      case "prism": {
        const prism = prismData && prismData.id === nav.prismId ? prismData : null;
        if (!prism) {
          body = (
            <div className="workspace-empty">
              <Icon name="bot" />
              <strong>That Prism is not available</strong>
              <p>Go back to your Prisms and pick one.</p>
            </div>
          );
          break;
        }
        actions = (
          <>
            <Button text="All Prisms" glyph="arrow-left" onClick={() => navigate("agents")} />
            <Button text="Open chat" glyph="message-square" className="button" onClick={() => openPrism(prism.id)} />
          </>
        );
        body = (
          <PrismDetail
            key={`${prism.id}-${revision}`}
            ctx={ctx}
            prism={prism}
            tools={prismTools}
            agent={ctx.data.agents.find((agent) => linkedPrism(agent)?.id === prism.id)}
            tab={nav.prismTab}
            setTab={(tab) => {
              setPrismTab(tab);
              render();
            }}
            reload={async () => {
              await loadPrismDetail();
              await ensureData(true);
              render();
            }}
          />
        );
        break;
      }
      case "skills":
        body = <SkillLibrary />;
        break;
      case "brain":
        actions = <Button text="Add to Brain" glyph="plus" className="button" onClick={() => brainEdit(null)} />;
        body = <BrainPage entries={brain} reload={() => load(true)} edit={brainEdit} />;
        break;
      case "positions":
        actions = (
          <>
            {viewToggle}
            <Button text="Create Prism" glyph="plus" className="button" onClick={ctx.createPrism} />
            {refreshButton}
          </>
        );
        body = (
          <OrganizationPage
            items={ctx.data.organization}
            department={department}
            setDepartment={(next) => setDepartment(next)}
            collapsed={collapsed}
            setCollapsed={setCollapsed}
            openPrism={(id) => openPrism(id)}
          />
        );
        break;
      default: {
        const pages: Record<string, { actions?: (c: PageContext) => ReactNode; Page: (props: { ctx: PageContext }) => ReactNode }> = {
          overview: { actions: dashboardActions, Page: DashboardPage },
          tasks: { actions: tasksActions, Page: TasksPage },
          runs: { Page: RunsPage },
          approvals: { Page: ApprovalsWorkspacePage },
          bugs: { Page: BugsPage },
          agents: { actions: agentsActions, Page: AgentsPage },
          targets: { actions: targetsActions, Page: TargetsPage },
          secrets: { actions: secretsActions, Page: SecretsPage },
          usage: { actions: usageActions, Page: UsagePage },
        };
        const entry = Object.hasOwn(pages, nav.page) ? pages[nav.page] : pages.overview;
        actions = (
          <>
            {nav.page === "agents" ? viewToggle : null}
            {entry.actions?.(ctx)}
            {refreshButton}
          </>
        );
        body = <entry.Page ctx={ctx} />;
      }
    }
  }

  let content: ReactNode;
  if (mode.kind === "idle") content = <p className="panel-note">Open Operations to load execution details.</p>;
  else if (mode.kind === "loading")
    content = (
      <p className="panel-note workspace-loading" role="status">
        Loading workspace…
      </p>
    );
  else if (mode.kind === "error")
    content = (
      <div className="workspace-empty">
        <Icon name="refresh-cw" />
        <strong>Workspace could not load</strong>
        <p>{mode.message}</p>
        <Button text="Try again" onClick={() => void load(true)} />
      </div>
    );
  else if (mode.kind === "run") content = <RunDetail runId={mode.runId} active={visible} onBack={() => navigate("runs")} />;
  else content = body;

  const portalRoot = app.pageActionsRoot;
  return (
    <div id="operations-content" aria-live="polite" data-workspace-view={nav.page} ref={contentRef}>
      {content}
      {visible && portalRoot && mode.kind === "page" ? createPortal(actions, portalRoot) : null}
      {agentDialog ? <AgentDialog agent={agentDialog} onClose={() => setAgentDialog(null)} /> : null}
    </div>
  );
}
