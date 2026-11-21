import { agentApi } from "./api.js";
import * as pages from "./workspace-pages.js";
import { el, icon, button, formDialog, empty, time, money, status, panel, tabs } from "./workspace-ui.js";
import { prismOrganization } from "./prism-organization.js";
import { prismDetail } from "./prism-detail.js";
import { brain, brainApi, brainProposedCount } from "./brain.js";
import { skillLibrary } from "./prism-skills.js";

export const WORKSPACE_PAGES = {
  overview: ["Dashboard", "Here is what your Prism team is working on.", "📊"],
  tasks: ["Tasks", "Work assigned to your Prisms. Every task can trace back to a goal.", "📋"],
  runs: ["Runs", "Every work session of every Prism. Open a run to see its progress and results.", "▶️"],
  approvals: ["Approvals", "Actions your Prisms want to take that need your decision first.", "✅"],
  bugs: ["Bugs", "Every bug your Prisms found, across all runs.", "🐞"],
  agents: ["Prisms", "Your AI team. Each Prism has a role, instructions, tools, and a budget.", "🤖"],
  positions: ["Prisms", "You lead the Chief of Staff, who coordinates your Prisms across departments.", "🏢"],
  targets: ["Target apps", "Web apps your Prisms work with. Test logins are stored encrypted.", "🌐"],
  secrets: ["Secrets", "API tokens and passwords your Prisms need. Only names are ever shown.", "🔑"],
  prism: ["Prisms", "Role, instructions, tools and limits.", "🤖"],
  brain: ["Brain", "What every Prism knows about your organisation. Add it here, or approve what Prisms learn from your chats.", "🧠"],
  skills: ["Skills", "Shared know-how for every department; each Prism chooses what it uses.", "📚"],
  usage: ["Run analytics", "Results, tokens, and run cost per Prism and per model.", "📈"],
};

export function workspaceController({ root, openRun, renderOrganization, cleanupChart }) {
  let stored;
  try { stored = localStorage.getItem("prism-workspace-page"); } catch { /* Private storage. */ }
  const state = { tab: WORKSPACE_PAGES[stored] && stored !== "prism" ? stored : "overview", prismId: null, prismTab: "overview", prismData: null, prismTools: [], runId: null, adoptionTried: false, data: null, loadedAt: 0, pending: null, request: 0, filters: {}, analytics: null, analyticsKey: "", prisms: [], managedApprovals: [], department: "", refreshing: false };
  const actions = document.querySelector("#workspace-page-actions");
  const visible = () => document.querySelector("#app")?.dataset.view === "operations";
  const filters = () => state.filters[state.tab] || (state.filters[state.tab] = {});

  function syncHeading() {
    window.prismRoutes?.workspace({ page: state.tab, id: state.prismId, prism: state.prismData || state.prisms.find((item) => item.id === state.prismId), section: state.prismTab, runId: state.runId });
    window.prism?.setPageHeading?.(...WORKSPACE_PAGES[state.tab]);
    if (state.tab === "overview") {
      const hour = new Date().getHours();
      const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
      const name = document.querySelector("#settings-account-name")?.textContent?.trim();
      document.querySelector("#page-title").textContent = name && name !== "Microsoft account" ? `${greeting}, ${name.split(" ")[0]}` : greeting;
    }
    document.querySelector(".operations-view").dataset.workspaceView = state.tab;
    document.querySelectorAll("[data-workspace-page]").forEach((item) => {
      const active = (item.dataset.workspacePage === state.tab || (item.dataset.workspacePage === "agents" && (state.tab === "positions" || state.tab === "prism"))) && visible();
      item.classList.toggle("active", active);
      if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
    });
  }
  async function ensureData(force = false) {
    if (state.pending) return state.pending;
    if (state.data && !force && Date.now() - state.loadedAt < 30000) return state.data;
    state.pending = Promise.all([
      agentApi("/api/v2/operations/overview").then((data) => ({ data, error: null })).catch((error) => ({ data: { agents: [], positions: [], tasks: [], runs: [], approvals: [], bugs: [] }, error })),
      agentApi("/api/v2/prisms/organization"),
      brainApi.list().catch(() => state.brain || []),
    ]).then(([engine, organization, brainEntries]) => {
      state.brain = brainEntries;
      const data = engine.data;
      state.engineError = engine.error;
      state.ownerName = organization.owner_name;
      state.prisms = organization.members;
      state.data = { ...data, organization: prismOrganization(state.prisms, [], [], state.ownerName), secrets: state.data?.secrets || [] };
      state.loadedAt = Date.now();
      updateNavigation();
      return state.data;
    }).then(async (data) => {
      // Every engine agent becomes a Prism, once, so a Prism is the only kind of agent.
      if (state.adoptionTried || !data.agents?.length || state.engineError) return data;
      state.adoptionTried = true;
      try {
        const adopted = await agentApi("/api/v2/prisms/adopt-engine-agents", { method: "POST" });
        if (adopted.length) { document.dispatchEvent(new CustomEvent("prism:prisms-changed")); state.pending = null; return await ensureData(true); }
      } catch { /* Adoption is retried on the next page load. */ }
      return data;
    }).finally(() => { state.pending = null; });
    return state.pending;
  }
  function updateNavigation() {
    if (!state.data) return;
    const counts = { brain: brainProposedCount(state.brain || []), agents: state.data.organization.filter((item) => item.kind === "prism").length, tasks: state.data.tasks.filter((item) => ["todo", "in_progress", "blocked"].includes(item.status)).length, approvals: state.data.approvals.filter((item) => item.status === "pending").length };
    for (const item of document.querySelectorAll("[data-workspace-count]")) {
      const value = counts[item.dataset.workspaceCount]; item.textContent = value ?? ""; item.hidden = value === undefined || value === 0;
    }
    const departments = [...new Set(state.data.organization.filter((item) => item.kind === "prism").map((item) => item.department).filter(Boolean))].sort((a, b) => a === "Leadership" ? -1 : b === "Leadership" ? 1 : a.localeCompare(b));
    if (state.department && !departments.includes(state.department)) state.department = "";
  }
  async function loadAnalytics() {
    const f = filters(); const days = f.days || "30"; const agent = f.agent || ""; const key = `${days}:${agent}`;
    if (state.analyticsKey === key && state.analytics) return;
    const params = new URLSearchParams({ days }); if (agent) params.set("agent_id", agent);
    const data = await agentApi(`/api/v2/operations/analytics?${params}`);
    if (state.tab === "usage" && key === `${filters().days || "30"}:${filters().agent || ""}`) { state.analytics = data; state.analyticsKey = key; }
  }
  async function load(force = false) {
    const serial = ++state.request;
    cleanupChart();
    actions.replaceChildren();
    const loading = el("p", "panel-note workspace-loading", "Loading workspace…");
    loading.setAttribute("role", "status");
    root.replaceChildren(loading);
    syncHeading();
    try {
      await ensureData(force);
      if (serial !== state.request || !visible()) return;
      if (state.engineError && !["positions", "prism", "brain", "skills"].includes(state.tab)) throw state.engineError;
      if (state.tab === "secrets") state.data.secrets = await agentApi("/api/v2/operations/secrets");
      if (state.tab === "prism") await loadPrismDetail();
      if (state.tab === "brain") { state.brain = await brainApi.list(); updateNavigation(); }
      if (state.tab === "approvals") state.managedApprovals = await agentApi("/api/v2/work/approvals?limit=200");
      if (state.tab === "usage") await loadAnalytics();
      if (serial !== state.request || !visible()) return;
      if (state.tab === "runs" && state.runId) { await openRun(state.runId); return; }
      render();
    } catch (error) {
      if (serial !== state.request || !visible()) return;
      const wrap = empty("Workspace could not load", error.message, "refresh-cw");
      wrap.append(button("Try again", () => load(true))); root.replaceChildren(wrap);
    }
  }
  function render() {
    cleanupChart(); syncHeading(); actions.replaceChildren();
    if (!state.data) return;
    const ctx = {
      root, actions, data: state.data, prisms: state.prisms, analytics: state.analytics, filters: filters(), managedApprovals: state.managedApprovals,
      navigate, openRun, openPrism, openAgent, editTask, editTarget, editSecret, remove, decide,
      createPrism: () => document.querySelector("#prism-create-button")?.click(),
      filter: (key, value, remote = false) => { filters()[key] = value; remote ? load() : render(); },
    };
    if (state.tab === "prism") return renderPrism(ctx);
    if (state.tab === "skills") { skillLibrary(root); return; }
    if (state.tab === "brain") { ctx.brain = { entries: state.brain || [], reload: () => load(true) }; brain(ctx); return; }
    if (state.tab === "positions") {
      renderOrganization(state.data.organization, { ctx, department: state.department, setDepartment: (department) => { state.department = department; render(); }, openPrism });
      actions.prepend(viewToggle());
      return;
    }
    (pages[state.tab === "overview" ? "dashboard" : state.tab] || pages.dashboard)(ctx);
    if (state.tab === "agents") actions.prepend(viewToggle());
    // Every page also exposes a refresh control without another navigation bar.
    actions.append(button("", () => { state.analyticsKey = ""; load(true); }, { glyph: "refresh-cw", className: "icon-button", title: "Refresh workspace" }));
  }
  // Prisms page views: the card grid or the org chart.
  function viewToggle() {
    const wrap = tabs([["agents", "Cards"], ["positions", "Org chart"]], state.tab, (view) => { if (view === "positions") state.department = ""; navigate(view); });
    wrap.setAttribute("aria-label", "Prisms view");
    wrap.classList.add("workspace-view-toggle");
    return wrap;
  }
  async function loadPrismDetail() {
    const [prism, tools] = await Promise.all([agentApi(`/api/v2/prisms/${state.prismId}`), agentApi(`/api/v2/prisms/${state.prismId}/tools`)]);
    state.prismData = prism; state.prismTools = tools.tools;
  }
  function renderPrism(ctx) {
    const prism = state.prismData;
    if (!prism) return root.replaceChildren(empty("That Prism is not available", "Go back to your Prisms and pick one.", "bot"));
    window.prism?.setPageHeading?.(prism.name, `${prism.job_role} · ${prism.department}`, "");
    actions.replaceChildren(
      button("All Prisms", () => navigate("agents"), { glyph: "arrow-left" }),
      button("Open chat", () => openPrism(prism.id), { glyph: "message-square", className: "button" }),
    );
    ctx.agentFor = (item) => state.data.agents.find((agent) => linkedPrism(agent)?.id === item.id);
    root.replaceChildren(prismDetail(ctx, { prism, tools: state.prismTools, tab: state.prismTab, setTab: (tab) => { state.prismTab = tab; render(); }, reload: async () => { await loadPrismDetail(); await ensureData(true); render(); } }));
  }
  function navigate(tab, id = null, section = "overview", runId = null) {
    if (!WORKSPACE_PAGES[tab]) return;
    if (tab === "prism") { state.prismId = id || state.prismId; state.prismTab = section; state.prismData = null; }
    state.runId = tab === "runs" ? runId : null;
    state.tab = tab;
    try { localStorage.setItem("prism-workspace-page", tab === "prism" ? "agents" : tab); } catch { /* Private storage. */ }
    window.prism?.setActiveTab?.("operations");
  }
  async function save(section, item, values) {
    await agentApi(`/api/v2/operations/${section}${item ? `/${item.id}` : ""}`, { method: item ? "PATCH" : "POST", body: JSON.stringify(values) });
    state.analyticsKey = "";
    await load(true);
  }
  function editTask(item = null, defaults = {}) {
    formDialog(item ? "Edit task" : "New task", [
      { name: "title", label: "Task", required: true, maxLength: 300, value: item?.title },
      { name: "goal", label: "Goal", type: "textarea", value: item?.goal },
      { name: "agent_id", label: "Prism", required: true, options: [["", "Choose a Prism"], ...state.data.agents.map((agent) => [agent.id, agent.name])], value: item?.agent_id ?? defaults.agent_id },
      { name: "target_app_id", label: "Target app", options: [["", "No target"], ...state.data.targets.map((target) => [target.id, target.name])], value: item?.target_app_id },
    ], (values) => save("tasks", item, { ...values, target_app_id: values.target_app_id || null }), { description: "Save the task here. Ask its Prism to prepare and start the work from your conversation." });
  }
  function editTarget(item = null) {
    formDialog(item ? "Edit target app" : "Add target app", [
      { name: "name", label: "App name", required: true, maxLength: 200, value: item?.name },
      { name: "base_url", label: "Website URL", type: "url", required: true, value: item?.base_url, placeholder: "https://example.com" },
      { name: "environment", label: "Environment", options: [["local", "Local"], ["dev", "Development"], ["staging", "Staging"], ["production", "Production"]], value: item?.environment || "staging" },
      { name: "notes", label: "Notes", type: "textarea", value: item?.notes },
    ], (values) => save("targets", item, values));
  }
  function editSecret() {
    formDialog("New secret", [
      { name: "name", label: "Name", required: true, maxLength: 200 },
      { name: "scope", label: "Scope", required: true, maxLength: 200, value: "general" },
      { name: "value", label: "Value", type: "password", required: true },
    ], (values) => save("secrets", null, values), { description: "The value is stored encrypted by the computer service and cannot be read back." });
  }
  async function remove(section, item) {
    const confirmed = await window.prism?.askDialog?.({ title: `Delete ${item.title || item.name}?`, message: section === "positions" ? "This removes the position. Its reporting positions will follow the computer service's organization rules." : "This removes this record from the connected computer service.", confirmLabel: "Delete", danger: true });
    if (!confirmed) return;
    try { await agentApi(`/api/v2/operations/${section}/${item.id}`, { method: "DELETE" }); await load(true); }
    catch (error) { window.prism?.setStatus?.(error.message, true); }
  }
  async function decide(item, decision) {
    if (state.refreshing) return;
    const confirmed = await window.prism?.askDialog?.({ title: `${decision === "approve" ? "Approve" : "Reject"} this action?`, message: item.payload?.summary || item.payload?.title || item.action, confirmLabel: decision === "approve" ? "Approve" : "Reject" });
    if (!confirmed) return;
    state.refreshing = true;
    root.querySelectorAll("button").forEach((item) => { item.disabled = true; });
    try { await agentApi(`/api/v2/qa/approvals/${item.id}/decision`, { method: "POST", body: JSON.stringify({ decision }) }); await load(true); }
    catch (error) { window.prism?.setStatus?.(error.message, true); render(); }
    finally { state.refreshing = false; }
  }
  async function openPrism(prismId, runId = null) {
    const prism = state.prisms.find((item) => item.id === prismId);
    if (!prism) return window.prism?.setStatus?.("That Prism is not available in the current list.", true);
    document.dispatchEvent(new CustomEvent("prism:search-result", { detail: { prismId } }));
    if (runId) document.dispatchEvent(new CustomEvent("prism:focus-computer-run", { detail: { runId } }));
  }
  function linkedPrism(agent) {
    return state.prisms.find((prism) => agent.key === `prism-${prism.id.slice(0, 8)}` || agent.name?.replace(/^Prism:\s*/i, "").toLowerCase() === prism.name.toLowerCase());
  }
  function openAgent(agent) {
    const prism = linkedPrism(agent);
    if (prism) return navigate("prism", prism.id);
    const dialog = el("dialog", "workspace-dialog"); const content = el("div", "workspace-form");
    content.append(panel(agent.name, agent.description), status(agent.status));
    for (const [title, value] of [["Role", agent.role], ["Model", agent.model || "Default model"], ["Runtime", agent.runtime], ["Run budget", money(agent.run_budget_usd)], ["Monthly budget", money(agent.monthly_budget_usd)], ["Created", time(agent.created_at)]]) content.append(el("p", "", `${title}: ${value}`));
    content.append(button("Close", () => dialog.close())); dialog.append(content); dialog.addEventListener("close", () => dialog.remove(), { once: true }); document.body.append(dialog); dialog.showModal();
  }
  function refresh() { state.analyticsKey = ""; return load(true); }
  document.querySelectorAll("[data-workspace-page]").forEach((item) => item.addEventListener("click", () => { navigate(item.dataset.workspacePage); }));
  document.addEventListener("prism:list", (event) => {
    state.prisms = event.detail?.prisms || [];
    if (!state.data) return;
    const organization = prismOrganization(state.prisms, [], [], state.ownerName);
    const changed = JSON.stringify(organization) !== JSON.stringify(state.data.organization);
    state.data.organization = organization;
    updateNavigation();
    if (changed && visible() && state.tab === "positions") render();
  });
  document.addEventListener("prism:sidebar", (event) => { if (event.detail?.section === "workspace" && window.prism?.isV24Enabled?.()) ensureData().catch(() => {}); });
  document.addEventListener("prism:workspace-navigate", (event) => { if (event.detail?.page === "positions") state.department = ""; navigate(event.detail?.page, event.detail?.id, event.detail?.section, event.detail?.runId); });
  document.addEventListener("prism:v24-mode", () => { if (window.prism?.isV24Enabled?.()) ensureData().catch(() => {}); });
  document.addEventListener("prism:tab", (event) => {
    if (event.detail?.tab === "operations") load();
    else { ++state.request; cleanupChart(); document.querySelectorAll("[data-workspace-page]").forEach((item) => { item.classList.remove("active"); item.removeAttribute("aria-current"); }); }
  });
  return { navigate, refresh, heading: syncHeading, state, openPrism, showRunHeading: (runId) => { state.tab = "runs"; state.runId = runId; actions.replaceChildren(); syncHeading(); } };
}

export function departmentColor(department) {
  return { Leadership: "#9065b0", Technology: "#529cca", Engineering: "#529cca", "Research & Development": "#339f94", "Quality Assurance": "#cb7b37", Sales: "#448361", Marketing: "#c14c8a", "Customer Success": "#d9730d", Operations: "#787774", Finance: "#339f94", People: "#cb7b37" }[department] || "#9b9a97";
}
