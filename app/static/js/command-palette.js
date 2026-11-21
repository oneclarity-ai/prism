// Universal search: Prisms, chat messages, pages, settings and quick actions in one dialog.
import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
const dialog = $("#search-dialog");
const input = $("#search-input");
const list = $("#search-list");
const status = $("#search-status");
const ui = () => window.prism || {};

const ICONS = {
  prism: '<path d="M6 3h12l4 6-10 12L2 9l4-6Z"/><path d="M2 9h20M9 3l3 6 3-6M12 21 9 9M12 21l3-12"/>',
  chat: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
  page: '<path d="M3 11 12 3l9 8M5 10v10h14V10"/>',
  setting: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
  action: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  play: '<circle cx="12" cy="12" r="10"/><path d="m10 8 6 4-6 4V8Z"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
  bug: '<path d="M8 2l1.9 1.9M16 2l-1.9 1.9M9 7.1V6a3 3 0 0 1 6 0v1.1M12 20a6 6 0 0 1-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3a6 6 0 0 1-6 6ZM12 20v-9M6.5 13H2M17.5 13H22"/>',
  bot: '<rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4M8 16h.01M16 16h.01"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/>',
  key: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.3-9.3M17 6l3 3"/>',
  network: '<rect x="9" y="2" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3M12 12V8"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  dash: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  theme: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};
const GROUPS = [["prism", "Prisms"], ["page", "Pages"], ["setting", "Settings"], ["action", "Actions"], ["message", "Chats"]];
const LIMIT = { prism: 6, message: 6, page: 6, setting: 8, action: 6 };

let prisms = [];
let messages = [];
let messageState = "idle"; // idle | loading | error | done
let shown = [];
let active = 0;
let token = 0;
let timer;
let opener = null;

document.addEventListener("prism:list", (event) => { prisms = event.detail.prisms || []; });

/* Sources ------------------------------------------------------------------------------- */

function pages() {
  const v22 = ui().isV22Enabled?.() === true;
  const v24 = ui().isV24Enabled?.() === true;
  const workspace = (page, label, keywords, icon) => ({ kind: "page", icon, label, sub: "Workspace", keywords, run: () => {
    document.dispatchEvent(new CustomEvent("prism:workspace-navigate", { detail: { page } }));
    ui().setSidebarSection?.("workspace");
  } });
  const rows = [{ kind: "page", label: "Chats", sub: "Prisms", keywords: "home start prisms conversations", run: () => ui().setActiveTab?.("prisms") }];
  if (v22) rows.push({ kind: "page", icon: "card", label: "Spending", sub: "Workspace", keywords: "cost costs money budget usage spend tokens billing inr usd currency", run: () => ui().setActiveTab?.("spending") });
  if (v24) {
    rows.push(workspace("overview", "Dashboard", "operations summary", "dash"), workspace("tasks", "Tasks", "todo board list work", "list"), workspace("runs", "Runs", "sessions history computer", "play"),
      workspace("approvals", "Approvals", "pending decisions actions review", "shield"), workspace("bugs", "Bugs", "issues defects", "bug"), workspace("agents", "Prisms", "agents setup engine", "bot"),
      workspace("targets", "Target apps", "websites urls setup", "globe"), workspace("secrets", "Secrets", "logins credentials keys", "key"), workspace("usage", "Run analytics", "results tokens models cost", "chart"),
      workspace("positions", "Org chart", "organization team departments reporting", "network"),
      workspace("skills", "Skills", "library role capabilities instructions training", "bot"));
  }
  return rows;
}

function settings() {
  const rows = [];
  const tabs = new Map([...document.querySelectorAll("#settings-dialog [data-subtab-target]")].map((tab) => [tab.dataset.subtabTarget, tab]));
  for (const [name, tab] of tabs) {
    if (tab.hidden) continue;
    const section = tab.textContent.trim();
    const panel = document.querySelector(`[data-subtab-group="settings"][data-subtab="${name}"]`);
    rows.push({ kind: "setting", label: section, sub: "Settings", keywords: "", run: () => ui().openSettings?.(name) });
    panel?.querySelectorAll(".setting-row strong, .settings-group, .settings-links strong").forEach((node) => {
      const label = node.firstChild?.textContent?.trim() || node.textContent.trim();
      if (!label || label === section) return;
      const note = node.closest(".setting-row")?.querySelector(".panel-note")?.textContent?.trim() || "";
      rows.push({ kind: "setting", label, sub: `Settings › ${section}`, keywords: note, run: () => ui().openSettings?.(name) });
    });
  }
  return rows;
}

function actions() {
  const v22 = ui().isV22Enabled?.() === true;
  const rows = [];
  if (v22) rows.push({ kind: "action", icon: "plus", label: "Create Prism", sub: "Action", keywords: "new add assistant agent", run: () => $("#prism-create-button")?.click() });
  rows.push({ kind: "action", label: "Open Settings", sub: "Action", keywords: "preferences account", run: () => ui().openSettings?.() });
  for (const [value, label] of [["system", "System"], ["light", "Light"], ["dark", "Dark"]]) {
    rows.push({ kind: "action", icon: "theme", label: `Theme: ${label}`, sub: "Action", keywords: "appearance color mode", run: () => window.prismTheme.set(value) });
  }
  for (const [value, label] of [["compact", "Compact"], ["default", "Default"], ["large", "Large"]]) {
    rows.push({ kind: "action", label: `Display size: ${label}`, sub: "Action", keywords: "zoom text density", run: () => { window.prismUi.set(value); const select = $("#size-select"); if (select) select.value = value; } });
  }
  rows.push({ kind: "action", label: "Refresh data", sub: "Action", keywords: "reload sync", run: () => $("#refresh-button")?.click() });
  return rows;
}

function prismRows() {
  return prisms.filter((prism) => !prism.archived).map((prism) => ({
    kind: "prism", label: prism.name, sub: [prism.job_role, prism.department].filter(Boolean).join(" · ") || "Prism",
    keywords: `${prism.description || ""} ${prism.job_role || ""} ${prism.department || ""}`,
    run: () => { ui().setSidebarSection?.("chat"); document.dispatchEvent(new CustomEvent("prism:open", { detail: { id: prism.id } })); },
  }));
}

/* Matching ------------------------------------------------------------------------------ */

function score(item, terms) {
  const label = item.label.toLowerCase();
  const rest = `${item.sub} ${item.keywords}`.toLowerCase();
  let total = 0;
  for (const term of terms) {
    if (label.startsWith(term)) total += 4;
    else if (label.split(/[\s:›·]+/).some((word) => word.startsWith(term))) total += 3;
    else if (label.includes(term)) total += 2;
    else if (rest.includes(term)) total += 1;
    else return -1;
  }
  return total;
}

function collect(query) {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const buckets = { prism: [], message: [], page: [], setting: [], action: [] };
  const sources = [...prismRows(), ...pages(), ...settings(), ...actions()];
  if (!terms.length) {
    buckets.prism = sources.filter((row) => row.kind === "prism");
    buckets.page = sources.filter((row) => row.kind === "page");
    buckets.action = sources.filter((row) => row.kind === "action" && /Create Prism|Open Settings|Theme: (Light|Dark)/.test(row.label));
  } else {
    for (const row of sources) {
      const points = score(row, terms);
      if (points >= 0) buckets[row.kind].push({ ...row, points });
    }
    for (const kind of Object.keys(buckets)) buckets[kind].sort((a, b) => b.points - a.points || a.label.localeCompare(b.label));
    buckets.message = messages;
  }
  return buckets;
}

/* Rendering ----------------------------------------------------------------------------- */

function svg(kind) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  node.setAttribute("viewBox", "0 0 24 24");
  node.setAttribute("aria-hidden", "true");
  node.innerHTML = ICONS[kind === "message" ? "chat" : kind] || ICONS.page;
  return node;
}
function highlight(text, terms) {
  const frag = document.createDocumentFragment();
  const lower = text.toLowerCase();
  const hit = terms.map((term) => ({ term, at: lower.indexOf(term) })).filter((entry) => entry.at >= 0).sort((a, b) => a.at - b.at)[0];
  if (!hit) { frag.append(text); return frag; }
  frag.append(text.slice(0, hit.at));
  const mark = document.createElement("mark");
  mark.textContent = text.slice(hit.at, hit.at + hit.term.length);
  frag.append(mark, text.slice(hit.at + hit.term.length));
  return frag;
}

function note(text) {
  const p = document.createElement("p");
  p.className = "search-note";
  p.textContent = text;
  return p;
}

function render() {
  const query = input.value.trim();
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const buckets = collect(query);
  list.replaceChildren();
  shown = [];
  for (const [kind, heading] of GROUPS) {
    const rows = (buckets[kind] || []).slice(0, LIMIT[kind]);
    const pending = kind === "message" && terms.length && messageState !== "idle" && !rows.length;
    if (!rows.length && !pending) continue;
    const group = document.createElement("div");
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", heading);
    const title = document.createElement("div");
    title.className = "search-group";
    title.setAttribute("aria-hidden", "true");
    title.textContent = terms.length || kind === "action" ? heading : kind === "prism" ? "Prisms" : kind === "page" ? "Go to" : heading;
    group.append(title);
    if (pending) {
      group.append(note(messageState === "loading" ? "Searching conversations…" : messageState === "error" ? "Conversations could not be searched." : "No conversation matches."));
    }
    for (const row of rows) {
      const option = document.createElement("div");
      option.className = "search-item";
      option.id = `search-option-${shown.length}`;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", "false");
      const icon = document.createElement("span");
      icon.className = "search-icon";
      icon.append(svg(row.icon || row.kind));
      const text = document.createElement("span");
      text.className = "search-text";
      const label = document.createElement("span");
      label.className = "search-label";
      label.append(highlight(row.label, terms));
      const sub = document.createElement("span");
      sub.className = "search-sub";
      sub.append(row.kind === "message" ? row.sub : highlight(row.sub, terms));
      text.append(label, sub);
      if (row.snippet) {
        const snippet = document.createElement("span");
        snippet.className = "search-snippet";
        snippet.append(highlight(row.snippet, terms));
        text.append(snippet);
      }
      const hint = document.createElement("span");
      hint.className = "search-enter";
      hint.setAttribute("aria-hidden", "true");
      hint.textContent = "↵";
      option.append(icon, text, hint);
      const index = shown.length;
      option.addEventListener("pointermove", () => { if (active !== index) setActive(index, false); });
      option.addEventListener("click", () => activate(index));
      shown.push(row);
      group.append(option);
    }
    list.append(group);
  }
  if (!shown.length && !list.children.length) list.append(note(query ? `No results for “${query}”.` : "Start typing to search."));
  active = Math.min(active, Math.max(shown.length - 1, 0));
  setActive(shown.length ? 0 : -1, true);
  status.textContent = shown.length ? `${shown.length} results` : "No results";
}

function setActive(index, scroll) {
  active = index;
  list.querySelectorAll(".search-item").forEach((option, position) => option.setAttribute("aria-selected", String(position === index)));
  const option = index >= 0 ? $(`#search-option-${index}`) : null;
  if (option) { input.setAttribute("aria-activedescendant", option.id); if (scroll) option.scrollIntoView({ block: "nearest" }); }
  else input.removeAttribute("aria-activedescendant");
}

function activate(index) {
  const row = shown[index];
  if (!row) return;
  dialog.close();
  // Let the dialog release focus before the destination moves it.
  setTimeout(() => row.run(), 0);
}

/* Chat search ----------------------------------------------------------------------------- */

async function searchMessages(query) {
  const current = ++token;
  if (query.length < 2) { messages = []; messageState = "idle"; return; }
  messageState = "loading";
  try {
    const rows = await agentApi(`/api/v2/prisms/search?${new URLSearchParams({ q: query })}`);
    if (current !== token) return;
    messages = rows.filter((row) => row.kind === "message").map((row) => {
      const by = row.role === "manager" ? "You" : "Prism";
      const when = row.created_at ? new Date(row.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
      return { kind: "message", label: row.prism_name, sub: `${by} · ${when}`, snippet: row.snippet, run: () => {
        ui().setSidebarSection?.("chat");
        document.dispatchEvent(new CustomEvent("prism:search-result", { detail: { prismId: row.prism_id, message: row.message_id ? { id: row.message_id, created_at: row.created_at } : null } }));
      } };
    });
    messageState = "done";
  } catch {
    if (current !== token) return;
    messages = [];
    messageState = "error";
  }
  render();
}

input.addEventListener("input", () => {
  const query = input.value.trim();
  ++token; // A newer query invalidates an earlier response.
  clearTimeout(timer);
  messages = [];
  messageState = query.length >= 2 ? "loading" : "idle";
  render();
  timer = setTimeout(() => searchMessages(query), 220);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    if (!shown.length) return;
    setActive((active + (event.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length, true);
  } else if (event.key === "Home" && event.ctrlKey) { event.preventDefault(); setActive(0, true); }
  else if (event.key === "End" && event.ctrlKey) { event.preventDefault(); setActive(shown.length - 1, true); }
  else if (event.key === "Enter") { event.preventDefault(); activate(active); }
});

/* Opening ---------------------------------------------------------------------------------- */

async function open() {
  if (dialog.open) return;
  opener = document.activeElement;
  input.value = "";
  messages = [];
  messageState = "idle";
  render();
  dialog.showModal();
  input.focus();
  if (!prisms.length && ui().isV22Enabled?.()) {
    try { prisms = await agentApi("/api/v2/prisms?include_archived=false"); if (dialog.open) render(); } catch { /* The list loads with the sidebar. */ }
  }
}
dialog.addEventListener("close", () => {
  clearTimeout(timer);
  ++token;
  // Return focus to the trigger unless the chosen destination already took it.
  setTimeout(() => { if ((!document.activeElement || document.activeElement === document.body) && opener?.isConnected) opener.focus(); }, 60);
});
dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
$("#sidebar-search-tab").addEventListener("click", open);
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); if (dialog.open) dialog.close(); else open(); }
});
window.prism = window.prism || {};
window.prism.openSearch = open;
