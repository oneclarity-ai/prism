// A Prism's settings: separate job skills from app permissions. Record text uses safe DOM nodes.
import { agentApi } from "./api.js";
import { renderMarkdown } from "./markdown.js";
import { prismSkillRows } from "./prism-skills.js";
import { el, icon, button, status, empty, panel, table, titleCell, age } from "./workspace-ui.js";

const GRANTS = [
  { value: "allowed", label: "Allowed", glyph: "circle-check", hint: "Uses it freely" },
  { value: "ask_first", label: "Ask first", glyph: "shield-check", hint: "Waits for your approval" },
  { value: "off", label: "Off", glyph: "ban", hint: "Never gets the tool" },
];
const DEFAULT_LIMITS = { max_turns: 150, run_budget_usd: 3, monthly_budget_usd: 100 };
const OPEN_TASK = (task) => !["done", "cancelled", "failed"].includes(task.status);

function field(label, input, hint = "") {
  const wrap = el("label", "pd-field");
  wrap.append(el("span", "pd-label", label), input);
  if (hint) wrap.append(el("small", "pd-hint", hint));
  return wrap;
}
function textInput(value, { type = "text", max, min, step, placeholder = "" } = {}) {
  const input = el("input");
  input.type = type; input.value = value ?? ""; input.placeholder = placeholder;
  if (max !== undefined) input.max = String(max);
  if (min !== undefined) input.min = String(min);
  if (step !== undefined) input.step = String(step);
  return input;
}
// A number with a unit on one side, so "turns" and "$" read as part of the field.
function unitInput(value, unit, options, side = "end") {
  const group = el("div", `pd-unit pd-unit-${side}`);
  const input = textInput(value, { type: "number", ...options });
  group.append(...(side === "start" ? [el("span", "", unit), input] : [input, el("span", "", unit)]));
  return { group, input };
}
function saveBar(onSave, onDiscard) {
  const bar = el("div", "pd-savebar");
  const note = el("span", "pd-dirty", "All changes saved");
  const discard = button("Discard", onDiscard, { className: "button secondary" });
  const save = button("Save changes", onSave, { className: "button" });
  discard.disabled = true; save.disabled = true; bar.hidden = true;
  bar.append(note, discard, save);
  bar.setDirty = (dirty) => { discard.disabled = !dirty; save.disabled = !dirty; bar.hidden = !dirty; bar.classList.toggle("dirty", dirty); note.textContent = "Unsaved changes"; };
  bar.setBusy = (busy) => { save.disabled = busy; discard.disabled = busy; if (busy) note.textContent = "Saving…"; };
  return bar;
}

// Long text (job description, instructions): shown rendered; the pencil switches to editing.
function richText({ value, placeholder = "", rows = 12, max = 8000, onChange }) {
  const box = el("div", "pd-rich");
  const view = el("div", "pd-rich-view");
  const input = el("textarea", "pd-rich-input");
  input.rows = rows; input.maxLength = max; input.value = value || ""; input.placeholder = placeholder; input.spellcheck = false;
  const pencil = button("", () => setEditing(input.hidden), { className: "icon-button pd-pencil", glyph: "pencil", title: "Edit" });
  function setEditing(on, focus = true) {
    input.hidden = !on; view.hidden = on;
    pencil.replaceChildren(icon(on ? "circle-check" : "pencil"));
    pencil.title = on ? "Done editing" : "Edit";
    pencil.setAttribute("aria-label", pencil.title);
    if (on) { if (focus) input.focus(); } else renderMarkdown(view, input.value);
  }
  input.addEventListener("input", () => onChange?.());
  box.append(view, input);
  setEditing(!input.value.trim(), false);
  return { box, input, pencil, setEditing, set(next) { input.value = next; onChange?.(); } };
}

export const PRISM_TABS = [["overview", "Overview"], ["instructions", "Instructions"], ["skills", "Skills"], ["tools", "Tools"], ["tasks", "Tasks"]];

export function prismDetail(ctx, { prism, tools, tab, setTab, reload }) {
  const wrap = el("div", "prism-detail");
  const agent = ctx.agentFor?.(prism);
  const openTasks = agent ? ctx.data.tasks.filter((task) => task.agent_id === agent.id && OPEN_TASK(task)).length : 0;
  const counts = { tools: tools.filter((tool) => tool.grant !== "off").length, tasks: openTasks };

  const nav = el("div", "pd-nav");
  nav.setAttribute("role", "tablist"); nav.setAttribute("aria-label", "Prism sections");
  for (const [key, text] of PRISM_TABS) {
    const item = el("button", `pd-tab${key === tab ? " active" : ""}`);
    item.type = "button"; item.setAttribute("role", "tab"); item.setAttribute("aria-selected", String(key === tab));
    item.append(el("span", "", text));
    if (counts[key]) item.append(el("em", "pd-tab-count", counts[key]));
    if (key === "skills") { const count = el("em", "pd-tab-count"); count.dataset.skillCount = ""; count.hidden = true; item.append(count); }
    item.addEventListener("click", () => setTab(key));
    nav.append(item);
  }
  const body = el("div", "pd-body");
  wrap.append(nav, body);
  ({ overview: overviewTab, instructions: instructionsTab, skills: skillsTab, tools: toolsTab, tasks: tasksTab }[tab] || overviewTab)(body, ctx, prism, tools, reload, { openTasks });
  return wrap;
}

async function patchPrism(prism, body) {
  const updated = await agentApi(`/api/v2/prisms/${prism.id}`, { method: "PATCH", body: JSON.stringify({ expected_lifecycle_version: prism.lifecycle_version, ...body }) });
  document.dispatchEvent(new CustomEvent("prism:prisms-changed"));
  return updated;
}
const patchProfile = (prism, body) => agentApi(`/api/v2/prisms/${prism.id}/profile`, { method: "PATCH", body: JSON.stringify(body) });
const fail = (error) => window.prism?.setStatus?.(error.message, true);

/* ---------------- Overview ---------------- */

function overviewTab(root, ctx, prism, tools, reload, { openTasks }) {
  const stats = el("div", "pd-stats");
  const allowed = tools.filter((tool) => tool.grant === "allowed").length;
  const ask = tools.filter((tool) => tool.grant === "ask_first").length;
  for (const [value, label, glyph] of [
    [allowed, "tools allowed", "circle-check"], [ask, "ask first", "shield-check"],
    [openTasks, "open tasks", "list-checks"], [`$${Number(prism.monthly_budget_usd ?? DEFAULT_LIMITS.monthly_budget_usd).toFixed(0)}`, "monthly budget", "coins"],
  ]) {
    const tile = el("div", "pd-stat");
    tile.append(icon(glyph), el("strong", "", value), el("span", "", label));
    stats.append(tile);
  }

  const grid = el("div", "pd-grid");
  const profile = panel("Profile", "Who this Prism is and what it is for");
  profile.classList.add("pd-card");
  const name = textInput(prism.name); name.maxLength = 120;
  const role = textInput(prism.job_role); role.maxLength = 120; role.disabled = prism.is_chief_of_staff;
  const department = textInput(prism.department); department.maxLength = 100;
  const reports = el("select");
  reports.append(new Option("Choose a Prism", ""));
  const blocked = new Set([prism.id]);
  for (let changed = true; changed;) { changed = false; for (const row of ctx.prisms) if (blocked.has(row.reports_to_prism_id) && !blocked.has(row.id)) { blocked.add(row.id); changed = true; } }
  for (const row of ctx.prisms.filter((item) => !blocked.has(item.id) && String(item.state).toLowerCase() !== "archived")) reports.add(new Option(row.name, row.id));
  reports.value = prism.reports_to_prism_id || ""; reports.disabled = prism.is_chief_of_staff;
  let refreshDirty = () => {};
  const rich = richText({ value: prism.description, placeholder: "What does this Prism do? Write it, or press Generate with AI.", rows: 12, onChange: () => refreshDirty() });
  const description = rich.input;

  const limits = panel("Limits", "Guardrails enforced on every run");
  limits.classList.add("pd-card");
  const turns = unitInput(prism.max_turns ?? DEFAULT_LIMITS.max_turns, "turns", { min: 5, max: 300, step: 1 });
  const runBudget = unitInput(prism.run_budget_usd ?? DEFAULT_LIMITS.run_budget_usd, "$", { min: 0.5, max: 50, step: 0.5 }, "start");
  const monthly = unitInput(prism.monthly_budget_usd ?? DEFAULT_LIMITS.monthly_budget_usd, "$", { min: 1, max: 100000, step: 1 }, "start");
  limits.append(field("Steps per run", turns.group, "A run stops after this many steps."), field("Budget per run", runBudget.group, "A run stops when it reaches this."), field("Monthly budget", monthly.group, "Across all of this Prism's runs."));

  // Job description: draft with AI, or use the pencil to write it yourself.
  const generate = button("Generate with AI", async () => {
    if (!name.value.trim() || !role.value.trim()) return;
    generate.disabled = true; generate.lastChild.textContent = "Writing a job description…";
    try {
      const result = await agentApi("/api/v2/prisms/generate-description", { method: "POST", body: JSON.stringify({ name: name.value.trim(), role: role.value.trim(), department: department.value.trim(), notes: description.value.slice(0, 4000) }) });
      rich.set(result.description); rich.setEditing(false);
      window.prism?.setStatus?.("Job description drafted. Review it, then save.");
    } catch (error) { fail(error); } finally { generate.disabled = false; syncGenerate(); }
  }, { className: "button ghost ai", glyph: "sparkles" });
  function syncGenerate() {
    generate.disabled = !(name.value.trim() && role.value.trim());
    generate.title = generate.disabled ? "Fill in name and role first" : "";
    generate.lastChild.textContent = description.value.trim() ? "Regenerate with AI" : "Generate with AI";
  }
  const descHead = el("div", "pd-desc-head");
  descHead.append(el("span", "pd-label", "Job description"), generate, rich.pencil);
  const descField = el("div", "pd-field");
  descField.append(descHead, rich.box);
  const identity = el("div", "pd-row");
  identity.append(field("Name", name), field("Role", role), field("Department", department), field("Reports to", reports));
  profile.append(identity, descField);
  syncGenerate();

  const snapshot = () => JSON.stringify([name.value.trim(), role.value.trim(), department.value.trim(), reports.value, description.value, turns.input.value, runBudget.input.value, monthly.input.value]);
  const start = snapshot();
  const savebar = saveBar(save, () => reload());
  refreshDirty = () => { syncGenerate(); savebar.setDirty(snapshot() !== start); };
  [name, role, department, reports, description, turns.input, runBudget.input, monthly.input].forEach((node) => node.addEventListener("input", refreshDirty));
  async function save() {
    savebar.setBusy(true);
    try {
      const body = { name: name.value.trim(), description: description.value.trim(), job_role: role.value.trim(), department: department.value.trim() };
      if ((reports.value || null) !== (prism.reports_to_prism_id || null)) body.reports_to_prism_id = reports.value || null;
      const current = await patchPrism(prism, body);
      await patchProfile(current, { max_turns: Number(turns.input.value), run_budget_usd: Number(runBudget.input.value), monthly_budget_usd: Number(monthly.input.value) });
      window.prism?.setStatus?.(`${current.name} saved.`);
      await reload();
    } catch (error) { fail(error); savebar.setBusy(false); refreshDirty(); }
  }
  grid.append(profile, limits);
  root.append(stats, grid, savebar);
}

/* ---------------- Instructions ---------------- */

function instructionsTab(root, _ctx, prism, _tools, reload) {
  const card = panel("Instructions", "The playbook this Prism follows. It is sent to the model at the start of every run, after its job description and your house rules.");
  card.classList.add("pd-card");
  const meta = el("small", "pd-hint");
  let update = () => {};
  const rich = richText({ value: prism.role_instructions, placeholder: "You are …\n- Always cite where you found something\n- Ask before sending anything\n- Keep replies short", rows: 20, max: 20000, onChange: () => update() });
  card.querySelector(".workspace-panel-heading").append(rich.pencil);
  const text = rich.input;
  const savebar = saveBar(save, () => { rich.set(prism.role_instructions || ""); rich.setEditing(!text.value.trim(), false); });
  update = () => {
    meta.textContent = `${text.value.length.toLocaleString()} characters`;
    savebar.setDirty(text.value !== (prism.role_instructions || ""));
  };
  async function save() {
    savebar.setBusy(true);
    try { await patchProfile(prism, { role_instructions: text.value }); window.prism?.setStatus?.("Instructions saved. The Prism follows them on its next run."); await reload(); }
    catch (error) { fail(error); savebar.setBusy(false); update(); }
  }
  card.append(rich.box, meta);
  root.append(card, savebar);
  update();
}

/* ---------------- Tools ---------------- */

function skillsTab(root, _ctx, prism) {
  const card = panel("Skills", "How this Prism does its job. Created from your chat onboarding answers and editable here.");
  const skills = el("div", "prism-skill-rows"); card.append(skills); root.append(card);
  prismSkillRows(skills, prism, (value) => { const count = root.closest(".prism-detail")?.querySelector("[data-skill-count]"); if (count) { count.textContent = value; count.hidden = !value; } });
}

function toolsTab(root, _ctx, prism, tools, reload) {
  const card = panel("Tool access", "Which apps and actions this Prism may use. Skills never change these permissions. Messages and external changes still require approval.");
  const initial = Object.fromEntries(tools.map((tool) => [tool.name, tool.grant]));
  const grants = { ...initial };
  const summary = el("div", "pd-counts");
  const list = el("div", "pd-tools");
  const savebar = saveBar(save, () => { Object.assign(grants, initial); draw(); });
  function draw() {
    summary.replaceChildren();
    for (const grant of GRANTS) {
      const chipNode = el("div", "pd-count");
      chipNode.append(el("strong", "", Object.values(grants).filter((value) => value === grant.value).length), el("span", "", grant.label), el("small", "panel-note", grant.hint.toLowerCase()));
      summary.append(chipNode);
    }
    list.replaceChildren();
    let group = "";
    for (const tool of tools) {
      if (tool.group !== group) { group = tool.group; list.append(el("div", "pd-group", group)); }
      const row = el("div", "pd-tool-row");
      const info = el("div", "pd-tool-info");
      info.append(el("strong", "", tool.label), el("span", "badge", "Tool access"), el("code", "", tool.name), el("p", "panel-note", tool.description));
      const toggle = el("div", "segmented pd-grant");
      toggle.setAttribute("role", "group"); toggle.setAttribute("aria-label", `${tool.label} permission`);
      for (const grant of GRANTS) {
        const option = button(grant.label, () => { grants[tool.name] = grant.value; draw(); }, { className: `${grants[tool.name] === grant.value ? "active " : ""}grant-${grant.value}` });
        option.setAttribute("aria-pressed", String(grants[tool.name] === grant.value));
        option.disabled = prism.state === "archived";
        toggle.append(option);
      }
      row.append(info, toggle);
      list.append(row);
    }
    savebar.setDirty(JSON.stringify(grants) !== JSON.stringify(initial));
  }
  async function save() {
    savebar.setBusy(true);
    try { await patchProfile(prism, { tool_grants: grants }); window.prism?.setStatus?.("Tools saved. The Prism uses them on its next run."); await reload(); }
    catch (error) { fail(error); savebar.setBusy(false); draw(); }
  }
  card.append(summary, list);
  root.append(card, savebar);
  draw();
}

/* ---------------- Tasks ---------------- */

function tasksTab(root, ctx, prism) {
  const agent = ctx.agentFor?.(prism);
  const mine = agent ? ctx.data.tasks.filter((task) => task.agent_id === agent.id) : [];
  const card = panel("Assigned tasks", mine.length ? `${mine.filter(OPEN_TASK).length} open of ${mine.length}` : `Everything ${prism.name} is responsible for`, button("New task", () => ctx.editTask(null, { agent_id: agent?.id }), { className: "button", glyph: "plus" }));
  card.classList.add("pd-card");
  if (!agent) card.append(empty("Its computer is not set up yet", "Tasks appear here once this Prism has been given work.", "circle-play"));
  else if (!mine.length) card.append(empty("No tasks yet", "Create a task, or ask this Prism in its chat.", "list-checks"));
  else card.append(table(["Task", "Status", "Created"], mine.map((task) => [titleCell(task.title, task.goal, () => ctx.editTask(task)), status(task.status), age(task.created_at)])));
  root.append(card);
}
