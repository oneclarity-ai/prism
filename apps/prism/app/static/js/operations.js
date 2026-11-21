import { agentApi } from "./api.js";
import { workspaceController, departmentColor } from "./workspace-controller.js";
import { el, icon, button, metric as workspaceMetric } from "./workspace-ui.js";

const root = document.querySelector("#operations-content");
const state = { detailRun: null, request: 0, timer: null };
const ACTIVE = new Set(["queued", "running", "waiting_children", "waiting_approval"]);
let chartCleanup = () => {};
let organizationOptions = null;
let organizationItems = [];
const collapsedPositions = new Set();
let workspace;
function node(tag, className = "", text = null) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== null) item.textContent = String(text);
  return item;
}

function control(label, action, className = "mini-button") {
  const item = node("button", className, label);
  item.type = "button";
  item.addEventListener("click", action);
  return item;
}

function date(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? "—" : parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function dollars(value) { return `$${Number(value || 0).toFixed(4)}`; }
function label(value) { return String(value || "unknown").replaceAll("_", " "); }
function clearTimer() { clearTimeout(state.timer); state.timer = null; }

function badge(value) {
  const text = String(value || "unknown");
  const tone = ["succeeded", "pass", "active", "approved"].includes(text) ? "green"
    : ["failed", "error", "rejected", "critical"].includes(text) ? "red"
      : ["running", "queued"].includes(text) ? "blue" : "gray";
  return node("span", `qa-chip tag-${tone}`, label(text));
}

function field(parent, title, value) {
  if (value === null || value === undefined || value === "") return;
  const row = node("p", "operations-field");
  row.append(node("strong", "", `${title}: `), document.createTextNode(String(value)));
  parent.append(row);
}

function card(title, subtitle = "") {
  const item = node("article", "operations-card");
  item.append(node("h3", "", title));
  if (subtitle) item.append(node("p", "panel-note", subtitle));
  return item;
}

function empty(message) { root.replaceChildren(node("p", "operations-empty", message)); }
function renderCollection(items, make, message) {
  root.replaceChildren();
  if (!items?.length) return empty(message);
  const list = node("div", "operations-list");
  items.forEach((item) => list.append(make(item)));
  root.append(list);
}

function metric(title, value) {
  const item = node("article", "stat-card operations-metric");
  item.append(node("span", "", title), node("strong", "", value));
  return item;
}

function renderOrganization(items, options) {
  chartCleanup();
  organizationItems = items;
  organizationOptions = options;
  renderPositions(items);
  const stats = el("div", "workspace-metrics four");
  const prisms = items.filter((item) => item.kind === "prism");
  stats.append(workspaceMetric("Prisms", prisms.length, "", "network"), workspaceMetric("Active", prisms.filter((item) => item.state === "active").length, "", "bot"), workspaceMetric("Setting up", prisms.filter((item) => !["active", "paused"].includes(item.state)).length, "", "clock"), workspaceMetric("Paused", prisms.filter((item) => item.state === "paused").length, "", "circle-dashed"));
  const tools = el("div", "workspace-toolbar org-department-filters");
  tools.append(button("All departments", () => options.setDepartment(""), { glyph: "users", className: `mini-button${options.department ? "" : " active"}` }));
  for (const department of [...new Set(prisms.map((item) => item.department).filter(Boolean))]) {
    const control = button(`${department} ${prisms.filter((item) => item.department === department).length}`, () => options.setDepartment(options.department === department ? "" : department), { className: `mini-button${options.department === department ? " active" : ""}` });
    control.setAttribute("aria-pressed", String(options.department === department));
    const dot = el("span", "workspace-department-dot"); dot.style.background = departmentColor(department); control.prepend(dot); tools.append(control);
  }
  const expand = button("Expand all", () => { collapsedPositions.clear(); renderOrganization(items, options); });
  const collapse = button("Collapse", () => { items.filter((item) => item.parent_id && items.some((child) => child.parent_id === item.id)).forEach((item) => collapsedPositions.add(item.id)); renderOrganization(items, options); });
  tools.append(expand, collapse);
  root.prepend(stats, tools);
  options.ctx.actions.replaceChildren(button("Create Prism", () => options.ctx.createPrism(), { glyph: "plus", className: "button" }), button("", () => workspace.refresh(), { glyph: "refresh-cw", className: "icon-button", title: "Refresh workspace" }));
}

function selectTab(tab) { clearTimer(); state.detailRun = null; ++state.request; workspace.navigate(tab); }
function renderPositions(items) {
  root.replaceChildren();
  if (!items.length) return empty("No Prisms yet. Create a Prism to see it here.");
  const hidden = new Set();
  const queue = items.filter((item) => collapsedPositions.has(item.parent_id)).map((item) => item.id);
  for (let i = 0; i < queue.length; i++) {
    if (hidden.has(queue[i])) continue;
    hidden.add(queue[i]);
    for (const child of items) if (child.parent_id === queue[i]) queue.push(child.id);
  }
  const visibleItems = items.filter((item) => !hidden.has(item.id));
  // Invalid cyclic data must remain inspectable, even if every node was collapsed.
  if (visibleItems.length) items = visibleItems;
  const nodeWidth = 250;
  const nodeHeight = 112;
  const horizontalGap = 36;
  const verticalGap = 78;
  const ids = new Set(items.map((item) => item.id));
  const children = new Map();
  for (const item of items) {
    const parent = ids.has(item.parent_id) ? item.parent_id : null;
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(item);
  }
  for (const list of children.values()) {
    list.sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0));
  }

  const roots = [...(children.get(null) || [])];
  const visited = new Set();
  const positions = new Map();
  let cursor = 40;
  const place = (item, depth) => {
    if (visited.has(item.id)) return null;
    visited.add(item.id);
    const childCenters = (children.get(item.id) || [])
      .map((child) => place(child, depth + 1))
      .filter((center) => center !== null);
    let x;
    if (childCenters.length) {
      x = (childCenters[0] + childCenters[childCenters.length - 1]) / 2 - nodeWidth / 2;
    } else {
      x = cursor;
      cursor += nodeWidth + horizontalGap;
    }
    const center = x + nodeWidth / 2;
    positions.set(item.id, { item, x, y: 40 + depth * (nodeHeight + verticalGap) });
    return center;
  };
  roots.forEach((item) => {
    place(item, 0);
    cursor += horizontalGap;
  });
  // A cycle can leave every position without a root. Keep those records visible.
  items.forEach((item) => {
    if (!visited.has(item.id)) {
      const center = place(item, 0);
      if (center !== null) cursor += horizontalGap;
    }
  });

  const maxDepth = Math.max(...[...positions.values()].map(({ y }) => (y - 40) / (nodeHeight + verticalGap)));
  const graphWidth = Math.max(cursor, nodeWidth + 80);
  const graphHeight = 80 + maxDepth * (nodeHeight + verticalGap) + nodeHeight;
  const viewport = node("div", "org-chart-viewport");
  viewport.setAttribute("role", "region");
  viewport.setAttribute("aria-label", "Organization chart. Drag to pan and scroll to zoom.");
  const stage = node("div", "org-chart-stage");
  stage.style.width = `${graphWidth}px`;
  stage.style.height = `${graphHeight}px`;
  const edges = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  edges.classList.add("org-chart-edges");
  edges.setAttribute("width", String(graphWidth));
  edges.setAttribute("height", String(graphHeight));
  edges.setAttribute("viewBox", `0 0 ${graphWidth} ${graphHeight}`);
  for (const { item, x, y } of positions.values()) {
    const parent = positions.get(item.parent_id);
    if (!parent) continue;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const startX = parent.x + nodeWidth / 2;
    const startY = parent.y + nodeHeight;
    const endX = x + nodeWidth / 2;
    const endY = y;
    const midY = (startY + endY) / 2;
    path.setAttribute("d", `M ${startX} ${startY} V ${midY} H ${endX} V ${endY}`);
    path.setAttribute("stroke", departmentColor(item.department));
    path.setAttribute("fill", "none");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("opacity", "0.7");
    edges.append(path);
  }
  stage.append(edges);
  for (const { item, x, y } of positions.values()) {
    const entry = node("article", `org-position-card${item.holder_type === "vacant" ? " vacant" : ""}`);
    entry.style.left = `${x}px`;
    entry.style.top = `${y}px`;
    entry.style.setProperty("--org-dept", departmentColor(item.department));
    entry.title = item.description || item.title || "";
    if (item.prism_id) {
      entry.tabIndex = 0;
      entry.setAttribute("role", "button");
      entry.setAttribute("aria-label", `Open ${item.title}`);
      entry.addEventListener("click", () => { if (viewport.dataset.dragged !== "true") organizationOptions.openPrism(item.prism_id); });
      entry.addEventListener("keydown", (event) => { if (event.target === entry && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); organizationOptions.openPrism(item.prism_id); } });
    } else entry.classList.add("org-owner-card");
    if (item.prism_id && organizationOptions.department && item.department !== organizationOptions.department) entry.classList.add("dimmed");
    const heading = node("strong", "org-position-title", item.title || "Untitled position");
    const holder = node("span", `org-position-holder${item.holder_type === "vacant" ? " vacant" : ""}`,
      label(item.state).replace(/^./, (letter) => letter.toUpperCase()));
    const tags = node("span", "org-position-tags");
    tags.append(node("span", "org-position-department", item.department || "Organization"), node("span", "org-position-level", label(item.level)));
    entry.append(heading, holder, tags);
    const nodeActions = el("div", "org-node-actions");
    const reports = organizationItems.filter((child) => child.parent_id === item.id).length;
    if (reports) {
      const toggle = button(String(reports), (event) => { event.stopPropagation(); if (collapsedPositions.has(item.id)) collapsedPositions.delete(item.id); else collapsedPositions.add(item.id); renderOrganization(organizationItems, organizationOptions); }, { glyph: collapsedPositions.has(item.id) ? "chevron-down" : "chevron-up", className: "org-node-action", title: collapsedPositions.has(item.id) ? "Show reports" : "Hide reports" });
      toggle.setAttribute("aria-expanded", String(!collapsedPositions.has(item.id))); nodeActions.append(toggle);
    }
    entry.append(nodeActions);
    stage.append(entry);
  }
  viewport.append(stage);
  const controls = node("div", "org-chart-controls");
  const zoomIn = button("", () => zoomAt(viewport, 1.15), { glyph: "zoom-in", className: "org-chart-control" });
  zoomIn.setAttribute("aria-label", "Zoom in");
  const zoomOut = button("", () => zoomAt(viewport, 1 / 1.15), { glyph: "zoom-out", className: "org-chart-control" });
  zoomOut.setAttribute("aria-label", "Zoom out");
  const fit = button("", () => fitOrgChart(viewport, stage, graphWidth, graphHeight), { glyph: "maximize", className: "org-chart-control" });
  fit.setAttribute("aria-label", "Fit chart to view");
  controls.append(zoomIn, zoomOut, fit);
  viewport.append(controls);
  const hint = node("div", "org-chart-hint", "Drag to pan · scroll to zoom");
  viewport.append(hint);
  root.append(viewport);
  installOrgChartGestures(viewport, stage, graphWidth, graphHeight);
}

function fitOrgChart(viewport, stage, graphWidth, graphHeight) {
  const scale = Math.max(0.2, Math.min(1.1, (viewport.clientWidth - 64) / graphWidth, (viewport.clientHeight - 64) / graphHeight));
  stage.dataset.scale = String(scale);
  stage.dataset.x = String((viewport.clientWidth - graphWidth * scale) / 2);
  stage.dataset.y = String((viewport.clientHeight - graphHeight * scale) / 2);
  stage.style.transform = `translate(${stage.dataset.x}px, ${stage.dataset.y}px) scale(${scale})`;
}

function zoomAt(viewport, factor, clientX = null, clientY = null) {
  const stage = viewport.querySelector(".org-chart-stage");
  if (!stage) return;
  const oldScale = Number(stage.dataset.scale || 1);
  const scale = Math.min(1.8, Math.max(0.2, oldScale * factor));
  const rect = viewport.getBoundingClientRect();
  const z = window.prismUi.zoom();
  const px = ((clientX ?? rect.left + rect.width / 2) - rect.left) / z;
  const py = ((clientY ?? rect.top + rect.height / 2) - rect.top) / z;
  const oldX = Number(stage.dataset.x || 0);
  const oldY = Number(stage.dataset.y || 0);
  const x = px - (px - oldX) * scale / oldScale;
  const y = py - (py - oldY) * scale / oldScale;
  stage.dataset.scale = String(scale);
  stage.dataset.x = String(x);
  stage.dataset.y = String(y);
  stage.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
}

function installOrgChartGestures(viewport, stage, graphWidth, graphHeight) {
  const fit = () => fitOrgChart(viewport, stage, graphWidth, graphHeight);
  const frame = requestAnimationFrame(fit);
  const observer = "ResizeObserver" in window ? new ResizeObserver(() => { if (viewport.isConnected && viewport.clientWidth) fit(); }) : null;
  observer?.observe(viewport);
  chartCleanup = () => { cancelAnimationFrame(frame); observer?.disconnect(); };
  viewport.tabIndex = 0;
  viewport.addEventListener("keydown", (event) => {
    if (event.target !== viewport) return;
    if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomAt(viewport, 1.15); }
    if (event.key === "-") { event.preventDefault(); zoomAt(viewport, 1 / 1.15); }
    if (event.key === "0") { event.preventDefault(); fit(); }
    const delta = { ArrowLeft: [35, 0], ArrowRight: [-35, 0], ArrowUp: [0, 35], ArrowDown: [0, -35] }[event.key];
    if (delta) { event.preventDefault(); const x = Number(stage.dataset.x || 0) + delta[0]; const y = Number(stage.dataset.y || 0) + delta[1]; stage.dataset.x = x; stage.dataset.y = y; stage.style.transform = `translate(${x}px, ${y}px) scale(${stage.dataset.scale || 1})`; }
  });
  let drag = null;
  viewport.addEventListener("pointerdown", (event) => {
    if (drag || event.button !== 0 || event.target.closest(".org-chart-controls, .org-node-actions")) return;
    viewport.dataset.dragged = "false";
    drag = { x: event.clientX, y: event.clientY, stageX: Number(stage.dataset.x || 0), stageY: Number(stage.dataset.y || 0), pointerId: event.pointerId };
    viewport.classList.add("dragging");

  });
  viewport.addEventListener("pointermove", (event) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.pointerType === "mouse" && !event.buttons) { drag = null; viewport.classList.remove("dragging"); return; }
    if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) { viewport.dataset.dragged = "true"; if (!viewport.hasPointerCapture(event.pointerId)) viewport.setPointerCapture(event.pointerId); }
    const z = window.prismUi.zoom();
    const x = drag.stageX + (event.clientX - drag.x) / z;
    const y = drag.stageY + (event.clientY - drag.y) / z;
    stage.dataset.x = String(x);
    stage.dataset.y = String(y);
    stage.style.transform = `translate(${x}px, ${y}px) scale(${stage.dataset.scale || 1})`;
  });
  const stopDrag = (event) => {
    if (!drag || (event && drag.pointerId !== event.pointerId)) return;
    drag = null;
    viewport.classList.remove("dragging");
  };
  viewport.addEventListener("pointerup", stopDrag);
  viewport.addEventListener("pointercancel", stopDrag);
  viewport.addEventListener("lostpointercapture", stopDrag);
  viewport.addEventListener("wheel", (event) => {
    if (!event.deltaY) return;
    event.preventDefault();
    zoomAt(viewport, event.deltaY < 0 ? 1.08 : 1 / 1.08, event.clientX, event.clientY);
  }, { passive: false });
}

async function downloadArtifact(id) {
  const token = localStorage.getItem("manager-agent-operator-token");
  const response = await fetch(`/api/v2/operations/artifacts/${id}/file`, {
    headers: token ? { "X-Manager-Operator-Token": token } : {},
  });
  if (!response.ok) throw new Error("File unavailable");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `prism-artifact-${id.slice(0, 8)}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

function renderRunDetail(data) {
  root.replaceChildren();
  const run = data.run || {};
  root.append(control("← Back to runs", () => selectTab("runs")));
  const main = card(run.task_title || "Run", `${run.agent_name || "Prism"} · ${date(run.created_at)}`);
  main.append(badge(run.status));
  field(main, "Model", run.model);
  field(main, "Cost", dollars(run.total_cost_usd ?? run.cost_usd));
  field(main, "Tokens", run.total_tokens ?? Number(run.input_tokens || 0) + Number(run.output_tokens || 0));
  field(main, "Started", date(run.started_at));
  field(main, "Ended", run.ended_at && date(run.ended_at));
  field(main, "Current tool", run.active_tool);
  field(main, "Summary", run.summary);
  if (run.error) field(main, "Error", run.error);
  root.append(main);
  for (const [title, items, make] of [
    ["Parallel Prisms", data.subagents, (item) => `${item.label || "Prism"}: ${label(item.status)}${item.activity ? ` · ${item.activity}` : ""}`],
    ["Test cases", data.test_cases, (item) => `${item.title}: ${label(item.status)}`],
    ["Bugs", data.bugs, (item) => `${item.title}: ${label(item.severity)} · ${label(item.status)}`],
    ["Timeline", data.events, (item) => `${date(item.created_at)} · ${item.tool || item.status || label(item.type)}`],
  ]) {
    if (!items?.length) continue;
    const block = node("section", "operations-detail-section");
    block.append(node("h3", "operations-section-title", `${title} · ${items.length}`));
    items.forEach((item) => block.append(node("p", "operations-event", make(item))));
    root.append(block);
  }
  if (data.artifacts?.length) {
    const files = node("section", "operations-detail-section");
    files.append(node("h3", "operations-section-title", `Files · ${data.artifacts.length}`));
    data.artifacts.forEach((item) => files.append(control(`${label(item.kind)} · ${date(item.created_at)}`, async () => {
      try { await downloadArtifact(item.id); }
      catch (error) { window.prism?.setStatus?.(error.message, true); }
    })));
    root.append(files);
  }
  if (ACTIVE.has(run.status) && state.detailRun === run.id && document.querySelector("#app")?.dataset.view === "operations") {
    state.timer = setTimeout(() => openRun(run.id, true), 3000);
  }
}

async function openRun(runId, refresh = false) {
  clearTimer();
  if (!refresh) workspace?.showRunHeading(runId);
  state.detailRun = runId;
  const serial = ++state.request;
  if (!refresh) root.replaceChildren(node("p", "panel-note", "Loading run detail…"));
  try {
    const data = await agentApi(`/api/v2/operations/runs/${runId}`);
    if (serial !== state.request || state.detailRun !== runId) return;
    renderRunDetail(data);
  } catch (error) {
    if (serial === state.request) empty(`Run detail could not load: ${error.message}`);
  }
}


workspace = workspaceController({ root, openRun, renderOrganization, cleanupChart: () => { chartCleanup(); chartCleanup = () => {}; clearTimer(); ++state.request; state.detailRun = null; } });
document.addEventListener("prism:tab", (event) => { if (event.detail?.tab !== "operations") { clearTimer(); ++state.request; state.detailRun = null; } });
if (document.querySelector("#app")?.dataset.view === "operations") workspace.refresh();
