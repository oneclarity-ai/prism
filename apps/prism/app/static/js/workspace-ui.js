// Shared presentation for the Workspace pages. All record content stays in text nodes.
export function el(tag, className = "", text = null) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== null && text !== undefined) item.textContent = String(text);
  return item;
}

export function icon(name, className = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", `workspace-icon ${className}`.trim());
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(svg.namespaceURI, "use");
  use.setAttribute("href", `/dashboard/assets/workspace-icons.svg#${name}`);
  svg.append(use);
  return svg;
}

export function button(text, action, { className = "mini-button", glyph, title } = {}) {
  const item = el("button", className);
  item.type = "button";
  if (glyph) item.append(icon(glyph));
  if (text) item.append(el("span", "", text));
  if (title) { item.title = title; item.setAttribute("aria-label", title); }
  item.addEventListener("click", action);
  return item;
}

export const words = (value) => String(value || "unknown").replaceAll("_", " ");
export const money = (value) => `$${Number(value || 0).toFixed(2)}`;
export const count = (value) => new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
export function time(value) {
  const d = new Date(value);
  return value && !Number.isNaN(d.valueOf()) ? d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—";
}
export function age(value) {
  if (!value) return "—";
  const days = Math.floor((Date.now() - new Date(value).getTime()) / 86400000);
  if (!Number.isFinite(days)) return "—";
  return days < 1 ? "Today" : days === 1 ? "1 day ago" : `${days} days ago`;
}
export function duration(item) {
  let seconds = item.avg_duration_s;
  if (seconds === undefined) seconds = item.started_at ? ((new Date(item.ended_at || Date.now()) - new Date(item.started_at)) / 1000) : 0;
  seconds = Math.max(0, Math.round(Number(seconds) || 0));
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`;
}
const statuses = {
  todo: ["To do", "circle-dashed", "gray"], in_progress: ["In progress", "circle-play", "blue"],
  blocked: ["Blocked", "ban", "orange"], done: ["Done", "circle-check", "green"],
  queued: ["Queued", "clock", "gray"], running: ["Running", "loader-circle", "blue"],
  waiting_children: ["Sub-agents working", "network", "purple"], waiting_approval: ["Needs approval", "shield-check", "orange"],
  succeeded: ["Succeeded", "circle-check", "green"], failed: ["Failed", "circle-x", "red"],
  cancelled: ["Cancelled", "ban", "gray"], timed_out: ["Timed out", "timer", "red"],
  pending: ["Pending", "clock", "orange"], approved: ["Approved", "circle-check", "green"],
  rejected: ["Rejected", "circle-x", "red"], active: ["Active", "circle-check", "green"],
};
export function status(value) {
  const [title, glyph, tone] = statuses[value] || [words(value), "circle-dashed", "gray"];
  const item = el("span", `workspace-status tone-${tone}`);
  item.append(icon(glyph), document.createTextNode(title));
  return item;
}
export function chip(text, tone = "gray") { return el("span", `workspace-chip tone-${tone}`, text); }
export function empty(title, description = "", glyph = "list-checks") {
  const box = el("div", "workspace-empty");
  box.append(icon(glyph), el("strong", "", title));
  if (description) box.append(el("p", "", description));
  return box;
}
export function select(label, options, value, change) {
  const field = el("select", "workspace-select");
  field.setAttribute("aria-label", label);
  options.forEach(([v, title]) => field.add(new Option(title, v)));
  field.value = value;
  field.addEventListener("change", () => change(field.value));
  return field;
}
export function searchInput(label, value, change) {
  const wrap = el("label", "workspace-search");
  const input = el("input");
  input.type = "search";
  input.placeholder = label;
  input.setAttribute("aria-label", label);
  input.value = value;
  input.addEventListener("input", () => change(input.value));
  wrap.append(icon("search"), input);
  return wrap;
}
export function tabs(options, value, change, showIcons = false) {
  const wrap = el("div", "workspace-status-tabs");
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-label", "Filter by status");
  for (const [key, text, n] of options) {
    const item = button(text, () => change(key), { className: `workspace-status-tab${key === value ? " active" : ""}` });
    if (showIcons && statuses[key]) item.prepend(icon(statuses[key][1]));
    item.setAttribute("aria-pressed", String(key === value));
    item.append(el("span", "workspace-tab-count", n));
    wrap.append(item);
  }
  return wrap;
}
export function table(headers, rows, className = "") {
  const wrap = el("div", `workspace-table-wrap ${className}`);
  const grid = el("table", "workspace-table");
  const head = el("thead");
  const tr = el("tr");
  const numeric = headers.map((text) => /^(runs|tokens|cost|duration|tasks|success rate|input tokens|output tokens)$/i.test(text));
  headers.forEach((text, index) => { const th = el("th", numeric[index] ? "numeric" : "", text); th.scope = "col"; tr.append(th); });
  head.append(tr);
  const body = el("tbody");
  rows.forEach((cells) => {
    if (cells instanceof HTMLElement) {
      [...cells.children].forEach((cell, index) => cell.classList.toggle("numeric", Boolean(numeric[index])));
      body.append(cells); return;
    }
    const row = el("tr");
    cells.forEach((content, index) => { const td = el("td", numeric[index] ? "numeric" : ""); td.append(content instanceof Node ? content : document.createTextNode(String(content ?? "—"))); row.append(td); });
    body.append(row);
  });
  grid.append(head, body);
  wrap.append(grid);
  return wrap;
}
export function titleCell(title, subtitle = "", action = null) {
  const wrap = el("div", "workspace-title-cell");
  wrap.append(action ? button(title, action, { className: "workspace-text-link" }) : el("strong", "", title));
  if (subtitle) wrap.append(el("span", "", subtitle));
  return wrap;
}
export function panel(title, subtitle = "", action = null) {
  const wrap = el("section", "workspace-panel");
  const head = el("div", "workspace-panel-heading");
  const titleWrap = el("div");
  titleWrap.append(el("h3", "", title));
  if (subtitle) titleWrap.append(el("p", "panel-note", subtitle));
  head.append(titleWrap);
  if (action) head.append(action);
  wrap.append(head);
  return wrap;
}
export function metric(title, value, detail, glyph = "hash") {
  const card = el("article", "workspace-metric");
  card.append(el("span", "workspace-metric-label", title), icon(glyph), el("strong", "", value));
  if (detail) card.append(el("small", "", detail));
  return card;
}

// Native dialog keeps focus trapped and restores it to the originating control.
export function formDialog(title, fields, onSave, { submit = "Save", description = "" } = {}) {
  const dialog = el("dialog", "workspace-dialog");
  const form = el("form", "workspace-form");
  const head = el("div", "workspace-dialog-heading");
  head.append(el("h2", "", title), button("", () => dialog.close(), { glyph: "x", className: "icon-button", title: "Close" }));
  form.append(head);
  if (description) form.append(el("p", "panel-note", description));
  const controls = new Map();
  for (const spec of fields) {
    const label = el("label", "workspace-form-field");
    label.append(el("span", "", spec.label));
    const input = el(spec.options ? "select" : spec.type === "textarea" ? "textarea" : "input");
    if (spec.options) spec.options.forEach(([value, text]) => input.add(new Option(text, value)));
    else if (spec.type !== "textarea") input.type = spec.type || "text";
    input.name = spec.name;
    input.value = spec.value ?? "";
    input.required = Boolean(spec.required);
    if (spec.maxLength) input.maxLength = spec.maxLength;
    if (spec.min !== undefined) input.min = spec.min;
    if (spec.type === "number") input.step = spec.step || "any";
    if (spec.type === "password") input.autocomplete = "new-password";
    if (spec.placeholder) input.placeholder = spec.placeholder;
    controls.set(spec.name, input);
    label.append(input);
    if (spec.hint) label.append(el("small", "panel-note", spec.hint));
    form.append(label);
  }
  const error = el("p", "inline-error");
  error.setAttribute("role", "alert");
  const footer = el("div", "workspace-form-footer");
  const cancel = button("Cancel", () => dialog.close());
  const save = el("button", "button", submit);
  save.type = "submit";
  footer.append(cancel, save);
  form.append(error, footer);
  let busy = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    busy = true;
    save.disabled = true;
    cancel.disabled = true;
    error.textContent = "";
    const values = Object.fromEntries([...controls].map(([key, input]) => [key, input.value]));
    try { await onSave(values); dialog.close(); }
    catch (err) { error.textContent = err.message; }
    finally { busy = false; save.disabled = false; cancel.disabled = false; }
  });
  dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
  dialog.addEventListener("close", () => { for (const input of controls.values()) if (input.type === "password") input.value = ""; dialog.remove(); }, { once: true });
  dialog.append(form);
  document.body.append(dialog);
  dialog.showModal();
  return dialog;
}

// One plain sentence or two from a Markdown job description, for cards and lists.
export function plainSummary(text, limit = 170) {
  const plain = String(text || "")
    .replace(/^#{1,6}\s*(Mission|Overview|Summary)\s*$/gim, "")
    .replace(/^#{1,6}\s+.*$/gm, " ")
    .replace(/^\s*[-*•]\s+/gm, "")
    .replace(/[*_`]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return plain.length > limit ? `${plain.slice(0, limit).replace(/\s+\S*$/, "")}…` : plain;
}
