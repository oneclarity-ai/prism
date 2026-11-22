import { prismLogo } from "./prism-logo.js";
import { el, icon, button, words, money, count, time, age, duration, status, chip, empty, select, searchInput, tabs, table, titleCell, panel, metric, plainSummary } from "./workspace-ui.js";

const TASK_STATES = [["all", "All"], ["todo", "To do"], ["in_progress", "In progress"], ["blocked", "Blocked"], ["done", "Done"], ["failed", "Failed"]];
const RUN_STATES = [["all", "All"], ["queued", "Queued"], ["running", "Running"], ["waiting_children", "Prisms working"], ["waiting_approval", "Needs approval"], ["succeeded", "Succeeded"], ["failed", "Failed"], ["cancelled", "Cancelled"], ["timed_out", "Timed out"]];
const PERIODS = [["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 90 days"], ["365", "Last year"], ["0", "All available"]];

function current(ctx, key, fallback = "") { return ctx.filters[key] ?? fallback; }
function toolbar() { return el("div", "workspace-toolbar"); }
function dateFilter(ctx, fallback = "30", analytics = false) {
  return select("Date range", analytics ? PERIODS.filter(([key]) => key !== "0") : PERIODS, current(ctx, "days", fallback), (value) => ctx.filter("days", value, analytics));
}
function inPeriod(items, days) {
  if (Number(days) === 0) return items;
  const since = Date.now() - Number(days) * 86400000;
  return items.filter((item) => new Date(item.created_at).getTime() >= since);
}
function choices(items, title) { return [["", title], ...items.map((item) => [item.id, item.name])]; }
function agentName(ctx, id) { return ctx.data.agents?.find((item) => item.id === id)?.name || "Unassigned"; }
function targetName(ctx, id) { return ctx.data.targets?.find((item) => item.id === id)?.name || "—"; }
function body(root, item) { root.replaceChildren(item); }
function filteredStatus(ctx, items, states, key = "status") {
  return tabs(states.map(([value, title]) => [value, title, value === "all" ? items.length : items.filter((item) => item.status === value).length]), current(ctx, key, "all"), (value) => ctx.filter(key, value), true);
}
function rowGroup(label, columns) {
  const row = el("tr", "workspace-date-group");
  const cell = el("th", "", label);
  cell.colSpan = columns;
  cell.scope = "rowgroup";
  row.append(cell);
  return row;
}
function dayLabel(value) {
  const d = new Date(value);
  if (Number.isNaN(d.valueOf())) return "Unknown date";
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(d); day.setHours(0, 0, 0, 0);
  const gap = Math.round((today - day) / 86400000);
  return gap === 0 ? "Today" : gap === 1 ? "Yesterday" : d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "short", year: "numeric" });
}
function groupByDay(items) {
  const groups = new Map();
  [...items].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).forEach((item) => {
    const key = dayLabel(item.created_at);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });
  return groups;
}
function periodCaption(root, items, noun) {
  if (items.length >= 200) root.append(el("p", "panel-note", `Showing the latest 200 ${noun}; filters apply to these records.`));
}
function summaryRow(run, ctx) {
  const row = el("div", "workspace-summary-row");
  const glyph = el("span", "workspace-row-icon"); glyph.append(icon("bot"));
  row.append(glyph, titleCell(run.task_title || "Untitled run", `${run.agent_name || agentName(ctx, run.agent_id)} · ${time(run.created_at)} · ${money(run.total_cost_usd ?? run.cost_usd)}`, () => ctx.openRun(run.id)), status(run.status));
  return row;
}
function linkedPrism(agent, ctx) {
  return ctx.prisms?.find((item) => agent.key === `prism-${String(item.id).replaceAll("-", "").slice(0, 8)}` || agent.name?.replace(/^Prism:\s*/i, "").toLowerCase() === item.name.toLowerCase());
}
const isArchivedPrism = (prism) => String(prism.state).toLowerCase() === "archived";
const STATES = { active: ["Active", "green"], draft: ["Draft", "gray"], onboarding: ["Setting up", "blue"], awaiting_confirmation: ["Review needed", "orange"], paused: ["Paused", "gray"] };
function stateChip(prism) {
  const [text, tone] = STATES[String(prism.state).toLowerCase()] || [words(prism.state), "gray"];
  return chip(text, tone);
}
// Every Prism is listed, whether or not its computer exists yet; engine agents with no Prism still show.
function rosterItems(ctx) {
  const used = new Set();
  const items = (ctx.prisms || []).filter((prism) => !isArchivedPrism(prism)).map((prism) => {
    const agent = ctx.data.agents.find((item) => linkedPrism(item, ctx)?.id === prism.id);
    if (agent) used.add(agent.id);
    return { prism, agent };
  });
  for (const agent of ctx.data.agents) if (!used.has(agent.id)) items.push({ prism: null, agent });
  return items;
}
function rosterCard({ prism, agent }, ctx) {
  const name = prism?.name || String(agent.name || "").replace(/^Prism:\s*/i, "");
  const card = el("article", "pc-card");
  card.tabIndex = 0; card.setAttribute("role", "link"); card.setAttribute("aria-label", `${name}, open settings`);
  const head = el("div", "pc-head");
  const who = el("div", "pc-who");
  who.append(el("strong", "", name), el("span", "", prism ? `${prism.job_role} · ${prism.department}` : words(agent.role)));
  head.append(prismLogo(prism || agent, "prism-logo"), who, prism ? stateChip(prism) : status(agent.status));
  const openTasks = agent ? ctx.data.tasks.filter((task) => task.agent_id === agent.id && !["done", "cancelled", "failed"].includes(task.status)).length : 0;
  const tools = prism ? prism.tools_allowed ?? 0 : agent?.tool_count ?? 0;
  const askFirst = prism ? prism.tools_ask_first ?? 0 : agent?.ask_first_count ?? 0;
  const budget = prism?.monthly_budget_usd ?? agent?.monthly_budget_usd;
  const stats = el("div", "pc-stats");
  for (const [value, label] of [[tools, "tools"], [askFirst, "ask first"], [openTasks, "open tasks"], [budget == null ? "—" : `$${Number(budget).toFixed(0)}`, "per month"]]) {
    const item = el("span"); item.append(el("strong", "", value), el("small", "", label)); stats.append(item);
  }
  const foot = el("div", "pc-foot");
  if (prism) foot.append(button("Open chat", (event) => { event.stopPropagation(); ctx.openPrism(prism.id); }, { glyph: "message-square", className: "pc-link" }));
  foot.append(button("More settings", (event) => { event.stopPropagation(); open(); }, { glyph: "arrow-right", className: "pc-link pc-link-end" }));
  card.append(head, el("p", "pc-summary", plainSummary(prism?.description || agent?.description) || "No description yet."), stats, foot);
  function open() { prism ? ctx.navigate("prism", prism.id) : ctx.openAgent(agent); }
  card.addEventListener("click", open);
  card.addEventListener("keydown", (event) => { if (event.target === card && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); open(); } });
  return card;
}

export function dashboard(ctx) {
  const days = current(ctx, "days", "7");
  const runs = inPeriod(ctx.data.runs, days);
  const bugs = inPeriod(ctx.data.bugs, days);
  const tasks = ctx.data.tasks.filter((item) => !["done", "cancelled", "failed"].includes(item.status));
  const cost = runs.reduce((sum, run) => sum + Number(run.total_cost_usd ?? run.cost_usd ?? 0), 0);
  const tools = toolbar(); tools.append(dateFilter(ctx, "7"), button("New task", () => ctx.editTask(), { glyph: "plus", className: "button" }));
  ctx.actions.replaceChildren(tools);
  const wrap = el("div");
  const stats = el("div", "workspace-metrics four");
  stats.append(metric("Active Prisms", ctx.data.agents.filter((item) => item.status === "active").length, `${tasks.length} open tasks`, "bot"), metric(`Runs · ${days === "0" ? "All available" : `Last ${days} days`}`, runs.length, `${runs.filter((run) => run.status === "succeeded").length} succeeded · ${runs.filter((run) => run.status === "failed").length} failed`, "circle-play"), metric("Needs approval", (ctx.data.approvals || []).filter((item) => item.status === "pending").length, "Computer actions waiting on you", "shield-check"), metric("Cost", money(cost), `${money(runs.length ? cost / runs.length : 0)} per run`, "coins"));
  wrap.append(stats);
  const columns = el("div", "workspace-dashboard-columns");
  const recent = panel("Recent runs", `${days === "0" ? "All available" : `Last ${days} days`} · newest first`, button("View all", () => ctx.navigate("runs"), { glyph: "arrow-right", className: "workspace-text-link" }));
  if (runs.length) runs.slice(0, 6).forEach((run) => recent.append(summaryRow(run, ctx)));
  else recent.append(empty("No runs in this period", "Start a task from a Prism conversation.", "circle-play"));
  const issues = panel("Latest bugs", `Last ${days === "0" ? "available" : days} days`, button("View all", () => ctx.navigate("bugs"), { glyph: "arrow-right", className: "workspace-text-link" }));
  if (!bugs.length) issues.append(empty("No bugs in this period.", "", "bug"));
  else bugs.slice(0, 4).forEach((bug) => { const row = el("div", "workspace-summary-row"); row.append(titleCell(bug.title, bug.target_name || "Task", () => ctx.openRun(bug.run_id)), chip(words(bug.severity), ["critical", "high"].includes(bug.severity) ? "red" : "orange")); issues.append(row); });
  columns.append(recent, issues); wrap.append(columns);
  const roster = panel("Your Prisms", "", button("Manage", () => ctx.navigate("agents"), { glyph: "arrow-right", className: "workspace-text-link" }));
  const agents = el("div", "pc-grid"); rosterItems(ctx).slice(0, 6).forEach((item) => agents.append(rosterCard(item, ctx)));
  roster.append(agents.children.length ? agents : empty("No Prisms yet", "Create a Prism to get started.", "bot")); wrap.append(roster);
  body(ctx.root, wrap);
}

export function tasks(ctx) {
  ctx.actions.replaceChildren(button("New task", () => ctx.editTask(), { glyph: "plus", className: "button" }));
  const tools = toolbar();
  const content = el("div");
  const input = searchInput("Search tasks…", current(ctx, "query"), (value) => { ctx.filters.query = value; renderContent(); });
  tools.append(input, select("Prism", choices(ctx.data.agents, "All Prisms"), current(ctx, "agent"), (value) => ctx.filter("agent", value)), select("Target app", choices(ctx.data.targets, "All targets"), current(ctx, "target"), (value) => ctx.filter("target", value)));
  const modes = el("div", "workspace-view-modes");
  for (const [mode, glyph] of [["list", "list"], ["board", "columns-3"]]) {
    const control = button("", () => ctx.filter("view", mode), { glyph, className: `mini-button${current(ctx, "view", "list") === mode ? " active" : ""}`, title: mode === "list" ? "List view" : "Board view" }); control.setAttribute("aria-pressed", String(current(ctx, "view", "list") === mode)); modes.append(control);
  }
  tools.append(modes);
  ctx.root.replaceChildren(tools, content);
  function renderContent() {
    content.replaceChildren();
    const filtered = ctx.data.tasks.filter((item) => (!current(ctx, "agent") || item.agent_id === current(ctx, "agent")) && (!current(ctx, "target") || item.target_app_id === current(ctx, "target")) && `${item.title} ${item.goal}`.toLowerCase().includes(current(ctx, "query").toLowerCase()));
    content.append(filteredStatus(ctx, filtered, TASK_STATES));
    const shown = filtered.filter((item) => current(ctx, "status", "all") === "all" || item.status === current(ctx, "status"));
    if (!shown.length) { content.append(empty("No tasks match", "Try another filter, or create your first task.")); return; }
    if (current(ctx, "view", "list") === "board") {
      const board = el("div", "workspace-task-board");
      for (const [key, title] of TASK_STATES.slice(1)) {
        const col = el("section", "workspace-board-column"); const entries = shown.filter((item) => item.status === key);
        col.append(el("h3", "", `${title} · ${entries.length}`));
        entries.forEach((task) => { const item = button("", () => ctx.editTask(task), { className: "workspace-board-task" }); item.append(el("strong", "", task.title), el("span", "panel-note", agentName(ctx, task.agent_id))); col.append(item); });
        board.append(col);
      }
      content.append(board);
    } else content.append(table(["Task", "Prism", "Target", "Status", "Created"], shown.map((item) => [titleCell(item.title, item.goal, () => ctx.editTask(item)), agentName(ctx, item.agent_id), targetName(ctx, item.target_app_id), status(item.status), age(item.created_at)])));
    periodCaption(content, ctx.data.tasks, "tasks");
  }
  renderContent();
}

export function runs(ctx) {
  const tools = toolbar(); tools.append(dateFilter(ctx));
  const items = inPeriod(ctx.data.runs, current(ctx, "days", "30"));
  const shown = items.filter((item) => current(ctx, "status", "all") === "all" || item.status === current(ctx, "status"));
  ctx.root.replaceChildren(tools, filteredStatus(ctx, items, RUN_STATES));
  if (!shown.length) return ctx.root.append(empty("No runs in this view", "Choose another status or date range.", "circle-play"));
  const rows = [];
  for (const [day, group] of groupByDay(shown)) {
    rows.push(rowGroup(`${day} · ${group.length} runs`, 7));
    group.forEach((item) => rows.push([titleCell(item.task_title || "Untitled run", `${String(item.id).slice(0, 8)}${item.kind === "orchestrator" ? " · parallel" : ""}`, () => ctx.openRun(item.id)), item.agent_name || agentName(ctx, item.agent_id), status(item.status), duration(item), count(item.total_tokens ?? Number(item.input_tokens || 0) + Number(item.output_tokens || 0)), money(item.total_cost_usd ?? item.cost_usd), item.started_at ? new Date(item.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"]));
  }
  ctx.root.append(table(["Task", "Prism", "Status", "Duration", "Tokens", "Cost", "Started"], rows));
  periodCaption(ctx.root, ctx.data.runs, "runs");
}

export function approvals(ctx) {
  const combined = ctx.data.approvals.map((item) => ({ ...item, managed: ctx.managedApprovals.find((managed) => managed.engine_approval_id === item.id) }));
  ctx.managedApprovals.filter((item) => !combined.some((entry) => entry.managed?.id === item.id)).forEach((item) => combined.push({ ...item, managed: item, task_title: item.run_title, payload: { arguments: item.payload } }));
  const filtered = inPeriod(combined, current(ctx, "days", "30"));
  const tools = toolbar();
  tools.append(tabs(["pending", "approved", "rejected"].map((key) => [key, words(key).replace(/^./, (letter) => letter.toUpperCase()), filtered.filter((item) => item.status === key).length]), current(ctx, "status", "pending"), (value) => ctx.filter("status", value)), dateFilter(ctx));
  ctx.root.replaceChildren(tools);
  const shown = filtered.filter((item) => item.status === current(ctx, "status", "pending"));
  if (!shown.length) return ctx.root.append(empty(current(ctx, "status", "pending") === "pending" ? "Nothing waiting for you" : "No decisions in this period", "Actions that need your approval appear here. Sign-ins and questions continue in the Prism conversation.", "shield-check"));
  shown.forEach((item) => {
    const args = item.payload?.arguments || {};
    const entry = panel(args.title || args.summary || args.question || item.task_title || words(item.action), `${item.managed?.prism_name || item.task_title || "Prism"} · ${time(item.created_at)}`);
    entry.append(status(item.status));
    for (const key of ["site", "reason", "summary", "question"]) if (args[key]) entry.append(el("p", "workspace-prewrap", `${words(key)}: ${args[key]}`));
    const actions = toolbar();
    if (item.status === "pending" && item.managed?.can_decide_here) {
      actions.append(button("Reject", () => ctx.decide(item.managed, "reject")), button("Approve", () => ctx.decide(item.managed, "approve"), { className: "button" }));
    }
    if (item.managed) actions.append(button("Open in Prism", () => ctx.openPrism(item.managed.prism_id, item.managed.run_id)));
    else if (item.run_id) actions.append(button("Open run", () => ctx.openRun(item.run_id)));
    entry.append(actions); ctx.root.append(entry);
  });
}

export function bugs(ctx) {
  const tools = toolbar();
  tools.append(dateFilter(ctx), select("Severity", [["", "All severities"], ...["critical", "high", "medium", "low"].map((key) => [key, words(key)])], current(ctx, "severity"), (value) => ctx.filter("severity", value)), select("Bug status", [["", "All statuses"], ...[...new Set(ctx.data.bugs.map((item) => item.status))].map((key) => [key, words(key)])], current(ctx, "status"), (value) => ctx.filter("status", value)));
  const items = inPeriod(ctx.data.bugs, current(ctx, "days", "30")).filter((item) => (!current(ctx, "severity") || item.severity === current(ctx, "severity")) && (!current(ctx, "status") || item.status === current(ctx, "status")));
  tools.append(el("span", "workspace-result-count", `${items.length} bugs`)); ctx.root.replaceChildren(tools);
  if (!items.length) return ctx.root.append(empty("No bugs in this view", "Any issues found by your Prisms will appear here.", "bug"));
  for (const [day, group] of groupByDay(items)) {
    const heading = el("h3", "workspace-day-heading"); heading.append(icon("calendar-days"), document.createTextNode(`${day} · ${group.length} ${group.length === 1 ? "bug" : "bugs"}`)); ctx.root.append(heading);
    group.forEach((item) => {
      const entry = el("article", "workspace-panel workspace-bug");
      const head = el("div", "workspace-bug-heading"); head.append(icon("bug"), el("strong", "", item.title), chip(words(item.severity), ["critical", "high"].includes(item.severity) ? "red" : "orange"), chip(words(item.status)), el("span", "workspace-bug-meta", `${item.target_name || "Task"} · ${item.model || "Model"} · ${time(item.created_at)}`));
      entry.append(head);
      const columns = el("div", "workspace-bug-columns");
      for (const [key, title] of [["steps", "Steps"], ["expected", "Expected"], ["actual", "Actual"]]) { const column = el("div"); column.append(el("small", "", title), el("p", "workspace-prewrap", item[key] || "—")); columns.append(column); }
      entry.append(columns);
      const footer = el("div", "workspace-bug-footer");
      for (const [text, glyph] of [["Email developer", "mail"], ["Raise Jira ticket", "ticket"], ["Send to manager", "send"]]) {
        const action = button(text, () => {}, { glyph });
        action.disabled = true;
        action.title = "This integration is not available yet.";
        footer.append(action);
      }
      footer.append(button("Open run", () => ctx.openRun(item.run_id), { glyph: "circle-play" }), el("span", "panel-note", item.task_title));
      if (item.external_url) { try { const url = new URL(item.external_url); if (["http:", "https:"].includes(url.protocol)) { const link = el("a", "workspace-text-link", "Open ticket"); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; footer.append(link); } } catch { /* An invalid engine URL is rendered only as text. */ } }
      entry.append(footer); ctx.root.append(entry);
    });
  }
}

export function agents(ctx) {
  ctx.actions.replaceChildren(button("New Prism", () => ctx.createPrism(), { glyph: "plus", className: "button" }));
  const items = rosterItems(ctx);
  if (!items.length) return body(ctx.root, empty("No Prisms yet", "Create a Prism to add it to your team.", "bot"));
  const page = el("div", "pc-page");
  const toolbarRow = el("div", "pc-toolbar");
  const grid = el("div", "pc-grid");
  const SETUP = ["draft", "onboarding", "awaiting_confirmation"];
  const stateOf = (item) => String(item.prism?.state || (item.agent?.status === "active" ? "active" : item.agent?.status) || "").toLowerCase();
  const departments = [...new Set(items.map((item) => item.prism?.department).filter(Boolean))].sort();
  const matches = (item) => {
    const query = current(ctx, "q").trim().toLowerCase();
    const text = `${item.prism?.name || item.agent?.name} ${item.prism?.job_role || ""} ${item.prism?.department || ""} ${plainSummary(item.prism?.description || item.agent?.description)}`.toLowerCase();
    const filter = current(ctx, "state", "all");
    const group = filter === "all" || (filter === "setup" ? SETUP.includes(stateOf(item)) : stateOf(item) === filter);
    return (!query || text.includes(query)) && group && (!current(ctx, "dept") || item.prism?.department === current(ctx, "dept"));
  };
  function drawGrid() {
    const shown = items.filter(matches);
    grid.replaceChildren(...(shown.length ? shown.map((item) => rosterCard(item, ctx)) : [empty("No Prisms match", "Try a different search or filter.", "search")]));
  }
  function drawToolbar() {
    const states = [["all", "All", items.length], ["active", "Active", items.filter((i) => stateOf(i) === "active").length], ["setup", "Setting up", items.filter((i) => SETUP.includes(stateOf(i))).length], ["paused", "Paused", items.filter((i) => stateOf(i) === "paused").length]];
    const search = searchInput("Search Prisms", current(ctx, "q"), (value) => { ctx.filters.q = value; drawGrid(); });
    const bar = [search, tabs(states, current(ctx, "state", "all"), (value) => { ctx.filters.state = value; drawToolbar(); drawGrid(); })];
    if (departments.length > 1) bar.splice(1, 0, select("Department", [["", "All departments"], ...departments.map((d) => [d, d])], current(ctx, "dept"), (value) => { ctx.filters.dept = value; drawGrid(); }));
    toolbarRow.replaceChildren(...bar);
  }
  drawToolbar(); drawGrid();
  page.append(toolbarRow, grid);
  body(ctx.root, page);
}

export function targets(ctx) {
  ctx.actions.replaceChildren(button("Add target", () => ctx.editTarget(), { glyph: "plus", className: "button" }));
  if (!ctx.data.targets.length) return body(ctx.root, empty("No target apps yet", "Add a web app for your Prisms to work with.", "globe"));
  const rows = ctx.data.targets.map((item) => {
    const actions = el("div", "workspace-row-actions"); actions.append(button("", () => ctx.editTarget(item), { glyph: "ellipsis", className: "icon-button", title: `Edit ${item.name}` }), button("", () => ctx.remove("targets", item), { glyph: "trash-2", className: "icon-button danger", title: `Delete ${item.name}` }));
    const login = el("span", item.has_test_login ? "workspace-positive" : "subtle", item.has_test_login ? "Stored" : "None");
    return [titleCell(item.name, item.base_url, () => ctx.editTarget(item)), chip(words(item.environment), item.environment === "production" ? "red" : "gray"), login, ctx.data.tasks.filter((task) => task.target_app_id === item.id).length, age(item.created_at), actions];
  });
  body(ctx.root, table(["App", "Environment", "Login", "Tasks", "Added", ""], rows));
}

export function secrets(ctx) {
  ctx.actions.replaceChildren(button("New secret", () => ctx.editSecret(), { glyph: "plus", className: "button" }));
  const vault = el("div", "workspace-vault"); const text = el("div"); text.append(el("strong", "", "Write-only vault"), el("p", "panel-note", "Values are encrypted by the computer service and never shown here. Saved target logins appear under their target_login scope.")); vault.append(icon("shield-check"), text);
  ctx.root.replaceChildren(vault);
  if (!ctx.data.secrets.length) return ctx.root.append(empty("No secrets yet", "Store credentials that your Prisms need.", "key-round"));
  ctx.root.append(table(["Name", "Scope", "Value", "Created", ""], ctx.data.secrets.map((item) => [titleCell(item.name), chip(item.scope || "general"), el("span", "workspace-secret-mask", "••••••••"), age(item.created_at), button("", () => ctx.remove("secrets", item), { glyph: "trash-2", className: "icon-button danger", title: `Delete ${item.name}` })])));
}

function chart(analytics) {
  const days = analytics.by_day || [];
  const wrap = el("div", "workspace-usage-chart");
  if (!days.length) return empty("No usage in this period", "Your first run will appear here.", "trending-up");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 1100 260"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Daily runs as bars and cost as a line. Exact amounts are in the data table below.");
  const maxRuns = Math.max(4, Math.ceil(Math.max(...days.map((day) => Number(day.runs || 0))) / 4) * 4);
  const maxCost = Math.max(0.01, ...days.map((day) => Number(day.cost_usd || 0)));
  const append = (tag, attrs, text = null) => { const item = document.createElementNS(svg.namespaceURI, tag); for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, String(value)); if (text !== null) item.textContent = text; svg.append(item); return item; };
  const width = 1000 / days.length;
  for (let i = 0; i <= 4; i++) {
    const y = 220 - i * 50;
    append("line", { x1: 50, x2: 1050, y1: y, y2: y, class: "workspace-chart-grid" });
    append("text", { x: 36, y: y + 4, "text-anchor": "end", class: "workspace-chart-label" }, String(Math.round(maxRuns * i / 4)));
    append("text", { x: 1060, y: y + 4, class: "workspace-chart-label" }, `$${(maxCost * i / 4).toFixed(maxCost < 0.04 ? 3 : 2)}`);
  }
  const points = [];
  days.forEach((day, i) => {
    const x = 50 + width * i;
    const height = 200 * Number(day.runs || 0) / maxRuns;
    const rect = append("rect", { x: x + width * 0.17, y: 220 - height, width: Math.max(1, width * 0.66), height, rx: 3, class: "workspace-chart-bar" });
    const title = document.createElementNS(svg.namespaceURI, "title"); title.textContent = `${day.date}: ${day.runs || 0} runs, ${money(day.cost_usd)}`; rect.append(title);
    points.push(`${x + width / 2},${220 - 200 * Number(day.cost_usd || 0) / maxCost}`);
    if (i % Math.max(1, Math.ceil(days.length / 10)) === 0) append("text", { x: x + width / 2, y: 246, "text-anchor": "middle", class: "workspace-chart-label" }, new Date(`${day.date}T12:00:00`).toLocaleDateString([], { day: "numeric", month: "short" }));
  });
  append("polyline", { points: points.join(" "), fill: "none", class: "workspace-chart-cost", "stroke-width": 2 });
  wrap.append(svg);
  const legend = el("div", "workspace-chart-legend"); legend.append(chip("Cost ($)", "red"), chip("Runs", "blue")); wrap.append(legend);
  return wrap;
}
export function usage(ctx) {
  const analytics = ctx.analytics || ctx.data.analytics || {};
  const totals = analytics.totals || {};
  const tools = toolbar(); tools.append(select("Prism", choices(ctx.data.agents, "All Prisms"), current(ctx, "agent"), (value) => ctx.filter("agent", value, true)), dateFilter(ctx, "30", true)); ctx.actions.replaceChildren(tools);
  const statusBox = el("div", "workspace-vault workspace-runtime"); statusBox.append(icon("circle-check"), el("div", "", `${ctx.data.status?.workers_online || 0} workers online · ${ctx.data.status?.azure_configured ? "Azure OpenAI connected" : "Computer service connected"}`));
  ctx.root.replaceChildren(statusBox);
  const stats = el("div", "workspace-metrics six");
  stats.append(metric("Total cost", money(totals.cost_usd), `${money(totals.avg_cost_per_run)} per run`, "coins"), metric("Runs", totals.runs || 0, `${totals.succeeded || 0} succeeded · ${totals.failed || 0} failed`, "circle-play"), metric("Success rate", `${Math.round(Number(totals.success_rate || 0) * 100)}%`, "of finished runs", "trending-up"), metric("Tokens", count(Number(totals.input_tokens || 0) + Number(totals.output_tokens || 0)), `${count(totals.input_tokens)} in · ${count(totals.output_tokens)} out`, "cpu"), metric("Avg duration", duration(totals), "per finished run", "timer"), metric("Bugs found", totals.bugs || 0, `${totals.tests_pass || 0} tests passed`, "bug")); ctx.root.append(stats);
  const daily = panel("Cost and runs per day", `Last ${current(ctx, "days", "30")} days`); daily.append(chart(analytics)); ctx.root.append(daily);
  const breakdowns = el("div", "workspace-breakdowns");
  for (const [title, rows, key] of [["Runs by outcome", analytics.by_status || [], "status"], ["Test results", analytics.tests_by_status || [], "status"], ["Bugs by severity", analytics.bugs_by_severity || [], "severity"]]) {
    const block = panel(title);
    rows.forEach((item) => { const row = el("div", "workspace-breakdown-row"); row.append(el("span", "", words(item[key])), el("strong", "", item.count || 0)); block.append(row); });
    if (!rows.length) block.append(el("p", "panel-note", "No data yet.")); breakdowns.append(block);
  }
  ctx.root.append(breakdowns);
  for (const [title, rows, name] of [["By Prism", analytics.by_agent || [], "agent_name"], ["By model", analytics.by_model || [], "model"]]) {
    const block = panel(title);
    block.append(table(["Name", "Runs", "Tokens", "Cost", "Success rate"], rows.map((item) => [item[name] || "Unknown", item.runs || 0, count(Number(item.input_tokens || 0) + Number(item.output_tokens || 0)), money(item.cost_usd), `${Math.round(Number(item.success_rate || 0) * 100)}%`]))); ctx.root.append(block);
  }
  const exact = el("details", "workspace-exact-usage"); exact.append(el("summary", "", "Daily usage data"), table(["Date", "Runs", "Cost", "Input tokens", "Output tokens"], (analytics.by_day || []).map((day) => [day.date, day.runs || 0, `$${Number(day.cost_usd || 0).toFixed(4)}`, day.input_tokens || 0, day.output_tokens || 0]))); ctx.root.append(exact);
}
