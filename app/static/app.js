const savedTab = localStorage.getItem("manager-agent-tab");
const state = { employees: [], projects: [], tasks: [], blockers: [], commitments: [], escalations: [], journeys: [], knowledge: [], memoryFacts: [], memoryEpisodes: [], attention: [], brief: null, microsoft: null, provider: null, foundation: null, activeTab: window.prismRoutes?.initialTab || (savedTab === "records" ? "knowledge" : (savedTab && savedTab !== "settings" ? savedTab : "prisms")) };
let selectedCommitmentId = null;
let editingKnowledgeId = null;
const operatorTokenKey = "manager-agent-operator-token";
const legacyV21Tabs = new Set(["ask", "management", "journey", "knowledge", "memory", "records"]);
const workspaceTabs = new Set(["work", "approvals", "operations", "spending"]);
let v21Mode = null; // null until /api/v2/agent/foundation answers
let v22Mode = null; // null until /api/v2/prisms/foundation answers
let v24Mode = null; // null until the computer capability check answers
let singleExecutiveMode = false;
const sectionFor = (tab) => (workspaceTabs.has(tab) ? "workspace" : "chat");
let sidebarSection = sectionFor(state.activeTab);
const subtabKey = (group) => `manager-agent-subtab-${group}`;

const $ = (selector) => document.querySelector(selector);
const today = () => new Date().toISOString().slice(0, 10);

let statusTimer;
function setStatus(message, isError = false) {
  const element = $("#status-message");
  clearTimeout(statusTimer);
  if (!message) {
    element.classList.remove("show");
    return;
  }
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.add("show");
  statusTimer = setTimeout(() => element.classList.remove("show"), isError ? 8000 : 4500);
}

// Resolves to true (confirm), the typed text (when `field` is set), or null when dismissed.
function askDialog({ title, message = "", confirmLabel = "Confirm", danger = false, field = null }) {
  const dialog = $("#confirm-dialog");
  const input = $("#confirm-input");
  const ok = $("#confirm-ok");
  $("#confirm-title").textContent = title;
  $("#confirm-message").textContent = message;
  $("#confirm-message").hidden = !message;
  $("#confirm-field").hidden = !field;
  $("#confirm-field-label").textContent = field ? field.label : "";
  input.type = field?.type || "text";
  input.placeholder = field?.placeholder || "";
  input.value = field?.value || "";
  ok.textContent = confirmLabel;
  ok.classList.toggle("danger", danger);
  return new Promise((resolve) => {
    dialog.returnValue = "";
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok" ? (field ? input.value : true) : null), { once: true });
    dialog.showModal();
    (field ? input : ok).focus();
  });
}

const pageTitles = {
  overview: ["Home", "Your Prisms and what needs you.", ""],
  spending: ["Spending", "What Prisms and the agentic swarm cost, in one place.", "💳"],
  prisms: ["Prisms", "Create private specialist assistants for the work you want covered.", "✦"],
  work: ["Work", "One place to follow every Prism task and computer run.", "💼"],
  approvals: ["Approvals", "Review computer actions before a Prism proceeds.", "✅"],
  operations: ["Operations", "See the connected Prisms, tasks, runs, and setup in one workspace.", "⚙️"],
  ask: ["Ask", "Ask about team state. Answers cite their evidence.", "💡"],
  management: ["Work", "Escalations, blockers, commitments, and today's updates.", "✅"],
  journey: ["Journeys", "How Prism followed each blocker between people.", "🧭"],
  agent: ["Assistant Prism", "Ask what matters across your team, then approve each exact message.", "✦"],
  knowledge: ["My knowledge", "Context and preferences Prism should keep in mind.", "📚"],
  memory: ["Memory", "Evidence-backed facts and history Prism relies on.", "🧠"],
  settings: ["Settings", "Account, preferences, connections, and access.", "⚙️"],
};

function setPageHeading(title, subtitle, icon) {
  $("#page-title").textContent = title;
  $("#page-subtitle").textContent = subtitle;
  $("#page-icon").textContent = icon;
  $("#page-icon").hidden = !icon;
  $("#page-logo").hidden = Boolean(icon);
  $("#crumb-title").textContent = title;
  $("#crumb-icon").textContent = icon;
  $("#crumb-icon").hidden = !icon;
  $("#crumb-logo").hidden = Boolean(icon);
  document.title = `${title} · Prism`;
}

function setActiveTab(tab) {
  closeProfileMenu();
  if (tab === "settings") { openSettings(); return; }
  if (!pageTitles[tab]) tab = "overview";
  if (v21Mode === false && tab === "agent") tab = "overview";
  if (v22Mode === false && (tab === "prisms" || tab === "spending" || workspaceTabs.has(tab))) tab = "overview";
  if (v24Mode === false && tab === "operations") tab = "overview";
  if (v22Mode === true && tab === "overview") tab = "prisms"; // Home is retired once Prisms are on.
  if (v21Mode === true && legacyV21Tabs.has(tab)) tab = "overview";
  const previousTab = state.activeTab;
  const commit = () => {
    if (previousTab !== tab) {
      if (workspaceTabs.has(tab)) setSidebarSection(sectionFor(tab));
      else if (tab === "agent" || tab === "prisms") setSidebarSection("chat");
    }
    state.activeTab = tab;
    const [title, subtitle, icon] = pageTitles[tab];
    setPageHeading(title, subtitle, icon);
    $("#app").dataset.view = tab;
    window.prismRoutes?.tab(tab);
    document.dispatchEvent(new CustomEvent("prism:tab", { detail: { tab } }));
    $(".workspace").scrollTo({ top: 0, behavior: "instant" });
    localStorage.setItem("manager-agent-tab", tab);
    document.querySelectorAll("[data-tab]").forEach((panel) => {
      panel.hidden = panel.dataset.tab !== tab
        || (v21Mode === true && panel.hasAttribute("data-v21-legacy"))
        || (v22Mode !== true && panel.hasAttribute("data-v22-only"));
      if (panel.hasAttribute("data-v24-only") && v24Mode !== true) panel.hidden = true;
    });
    document.querySelectorAll("[data-tab-target]").forEach((button) => {
      if (button.hasAttribute("data-v21-legacy")) button.hidden = v21Mode === true;
      if (button.hasAttribute("data-v21-only")) button.hidden = v21Mode !== true;
      if (button.hasAttribute("data-hide-v22") && v22Mode === true) button.hidden = true;
      if (button.hasAttribute("data-v22-only")) button.hidden = v22Mode !== true;
      if (button.hasAttribute("data-v24-only")) button.hidden = v24Mode !== true || (button.hasAttribute("data-v22-only") && v22Mode !== true);
      // A sidebar entry can also own pages opened from it (Settings -> Teams).
      const active = button.dataset.tabTarget === tab || (button.dataset.tabGroup || "").split(" ").includes(tab);
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
  };
  if (previousTab !== tab && !window.prismRoutes?.restoring && typeof document.startViewTransition === "function" && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const transition = document.startViewTransition(commit);
    window.prism.transition = transition.updateCallbackDone;
    return transition.updateCallbackDone;
  } else {
    commit();
  }
}

function setSidebarSection(section) {
  if (!["chat", "workspace", "notifications"].includes(section)) section = "chat";
  sidebarSection = section;
  document.querySelectorAll("[data-sidebar-target]").forEach((button) => {
    const active = button.dataset.sidebarTarget === section;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  const visiblePanel = `sidebar-${section}-panel`;
  document.querySelectorAll(".sidebar-section").forEach((panel) => {
    panel.hidden = panel.id !== visiblePanel;
  });
  document.dispatchEvent(new CustomEvent("prism:sidebar", { detail: { section } }));
}

function applyV21Mode(enabled) {
  v21Mode = enabled;
  document.querySelectorAll("[data-v21-legacy]").forEach((element) => {
    if (!element.hasAttribute("data-tab")) element.hidden = enabled;
  });
  document.querySelectorAll("[data-v21-only]").forEach((element) => {
    if (!element.hasAttribute("data-tab")) element.hidden = !enabled;
  });
  setActiveTab(enabled && legacyV21Tabs.has(state.activeTab) ? "overview" : state.activeTab);
  renderSetup();
  document.dispatchEvent(new CustomEvent("prism:v21-mode", { detail: { enabled } }));
}

function applyV22Mode(enabled, executiveOnly = false) {
  v22Mode = enabled;
  singleExecutiveMode = enabled && executiveOnly;
  if (!enabled) setSidebarSection("chat");
  document.querySelectorAll("[data-v22-only]").forEach((element) => {
    if (!element.hasAttribute("data-tab")) element.hidden = !enabled || (element.hasAttribute("data-v24-only") && v24Mode !== true);
  });
  document.querySelectorAll("[data-hide-v22]").forEach((element) => {
    element.hidden = enabled;
  });
  document.querySelectorAll("[data-hide-v22-single]").forEach((element) => {
    element.hidden = singleExecutiveMode || (element.hasAttribute("data-v22-only") && !enabled);
  });
  setActiveTab(enabled ? state.activeTab : (state.activeTab === "prisms" ? "overview" : state.activeTab));
  $("#legacy-today").hidden = enabled;
  document.dispatchEvent(new CustomEvent("prism:v22-mode", { detail: { enabled, singleExecutiveMode } }));
}

function applyV24Mode(enabled) {
  v24Mode = enabled;
  document.querySelectorAll(".workspace-navigation[data-v24-only], .workspace-navigation [data-workspace-page][data-v24-only]").forEach((node) => { node.hidden = !enabled; });
  document.querySelector("#workspace-legacy-links").hidden = enabled;
  updateProfileStatus();
  setActiveTab(state.activeTab);
  document.dispatchEvent(new CustomEvent("prism:v24-mode", { detail: { enabled } }));
}

// Switchable views inside a page (Teams tabs, Settings sections). The last choice is remembered.
function setSubtab(group, name) {
  const root = document.querySelector(`[data-subtabs="${group}"]`);
  const targets = [...root.querySelectorAll("[data-subtab-target]")];
  if (!targets.some((button) => button.dataset.subtabTarget === name)) name = targets[0].dataset.subtabTarget;
  targets.forEach((button) => {
    const active = button.dataset.subtabTarget === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll(`[data-subtab-group="${group}"]`).forEach((panel) => {
    panel.hidden = panel.dataset.subtab !== name;
  });
  try { localStorage.setItem(subtabKey(group), name); } catch (_) { /* private mode */ }
  if (group === "settings" && name === "skills") {
    import("./js/prism-skills.js").then(({ skillLibrary }) => skillLibrary($("#settings-skills-library"))).catch((error) => setStatus(error.message, true));
  }
  if (group === "settings" && $("#settings-dialog").open) window.prismRoutes?.settings(name);
}

// Lets the Agent module (agent-chat.js) reuse the shared toast, dialog, and tab helpers.
window.prism = { setPageHeading, setActiveTab, setSubtab, setStatus, askDialog, isV22Enabled: () => v22Mode, isV24Enabled: () => v24Mode, applyV24Mode, setSidebarSection };

async function api(path, options = {}) {
  const operatorToken = localStorage.getItem(operatorTokenKey);
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Manager-Operator-Token": operatorToken } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Request failed (" + response.status + ")");
  }
  return response.status === 204 ? null : response.json();
}

async function setOperatorToken() {
  const current = localStorage.getItem(operatorTokenKey);
  const value = await askDialog({
    title: "Operator access key",
    message: current
      ? "Replace the operator access key. Leave blank to remove it from this browser."
      : "Enter the operator access key from your local .env file.",
    confirmLabel: "Save",
    field: { label: "Access key", type: "password" },
  });
  if (value === null) return;
  if (value.trim()) {
    localStorage.setItem(operatorTokenKey, value.trim());
    setStatus("Operator access key saved in this browser.");
  } else {
    localStorage.removeItem(operatorTokenKey);
    setStatus("Operator access key removed from this browser.");
  }
  loadDashboard();
}

function setNavCount(selector, count) {
  const element = $(selector);
  if (!element) return;
  element.textContent = count;
  element.hidden = !count;
}

function nameFor(id) {
  const employee = state.employees.find((item) => item.id === id);
  return employee ? employee.name : "Unassigned";
}

function dateTime(value) {
  return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "No deadline";
}

function renderList(selector, items, render, emptyText) {
  const container = $(selector);
  if (!items.length) {
    container.className = "list empty-state";
    container.textContent = emptyText;
    return;
  }
  container.className = "list";
  container.innerHTML = items.map(render).join("");
}

function item(title, meta) {
  return `<div class="list-item"><strong>${escapeHtml(title)}</strong><div class="meta">${escapeHtml(meta)}</div></div>`;
}

function itemWithActions(title, meta, actions) {
  return `<div class="list-item"><strong>${escapeHtml(title)}</strong><div class="meta">${escapeHtml(meta)}</div>${actions ? `<div class="item-actions">${actions}</div>` : ""}</div>`;
}

function humanize(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderAttention(entries) {
  const container = $("#intelligence-attention-list");
  $("#intelligence-attention-count").textContent = entries.length;
  if (!entries.length) {
    container.className = "attention-list empty-state";
    container.textContent = "Nothing currently needs your intervention.";
    return;
  }
  container.className = "attention-list";
  container.innerHTML = entries.map((entry) => {
    const risk = entry.risk;
    const people = entry.people.length ? entry.people.join(", ") : "No person linked";
    const actions = entry.agent_actions.length ? entry.agent_actions.join(" · ") : "No Prism action recorded yet";
    return `<article class="attention-card ${escapeHtml(risk.severity)}">
      <div class="attention-card-heading"><span class="risk-level">${escapeHtml(humanize(risk.severity))}</span><span>${escapeHtml(people)}</span></div>
      <h3>${escapeHtml(risk.summary)}</h3>
      <p>${escapeHtml(entry.impact)}</p>
      <dl><div><dt>Prism action</dt><dd>${escapeHtml(actions)}</dd></div><div><dt>Expected now</dt><dd>${escapeHtml(entry.current_expectation)}</dd></div><div><dt>Why you see this</dt><dd>${escapeHtml(entry.why_visible)}</dd></div></dl>
      ${entry.manager_options.length ? `<div class="manager-options">${entry.manager_options.map((option) => `<span>${escapeHtml(option)}</span>`).join("")}</div>` : ""}
    </article>`;
  }).join("");
}

function renderBrief(brief) {
  state.brief = brief;
  $("#intelligence-brief-date").textContent = new Date(`${brief.date}T00:00:00`).toLocaleDateString([], { dateStyle: "medium" });
  const sections = [
    ["Needs attention", brief.needs_attention],
    ["Important changes", brief.important_changes],
    ["Completed", brief.completed],
    ["In progress", brief.in_progress],
    ["New blockers", brief.new_blockers],
    ["Resolved blockers", brief.resolved_blockers],
    ["Missed commitments", brief.missed_commitments],
    ["Changed ETAs", brief.changed_etas],
    ["Dependencies at risk", brief.dependencies_at_risk],
    ["People waiting", brief.people_waiting],
    ["No action required", brief.no_action_required],
  ].filter(([, values]) => values && values.length);
  const container = $("#intelligence-brief");
  if (!sections.length) {
    container.className = "brief-grid empty-state";
    container.textContent = "No material management changes recorded today.";
    return;
  }
  container.className = "brief-grid";
  container.innerHTML = sections.map(([title, values]) => `<section class="brief-section"><h3>${escapeHtml(title)}</h3><ul>${values.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul></section>`).join("");
}

function renderManagementAnswer(result) {
  const container = $("#management-query-results");
  container.hidden = false;
  const evidence = result.evidence?.length
    ? `<details><summary>Evidence (${result.evidence.length})</summary><ul>${result.evidence.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul></details>`
    : "";
  container.innerHTML = `<span class="answer-type">${escapeHtml(humanize(result.answer_type))}</span><p>${escapeHtml(result.answer)}</p>${result.uncertainty ? `<p class="query-uncertainty">${escapeHtml(result.uncertainty)}</p>` : ""}${evidence}`;
}

function categoryLabel(category) {
  return {
    team: "Team context",
    work: "Current work",
    people: "Person or role",
    communication: "Communication preference",
    escalation: "Escalation guidance",
    other: "Other",
  }[category] || "Other";
}

function renderKnowledge(entries) {
  const container = $("#knowledge-list");
  $("#knowledge-count").textContent = entries.length;
  if (!entries.length) {
    container.className = "knowledge-list empty-state";
    container.textContent = "No context saved yet. Add something Prism should remember.";
    return;
  }
  container.className = "knowledge-list";
  container.innerHTML = entries.map((entry) => `
    <article class="knowledge-entry">
      <div class="knowledge-entry-heading">
        <span class="knowledge-category ${escapeHtml(entry.category)}">${escapeHtml(categoryLabel(entry.category))}</span>
        <time>${escapeHtml(dateTime(entry.updated_at))}</time>
      </div>
      <h3>${escapeHtml(entry.title)}</h3>
      <p>${escapeHtml(entry.content).replace(/\n/g, "<br>")}</p>
      <div class="knowledge-entry-actions">
        ${entry.title.toLowerCase().startsWith("deployment list") ? `<button class="mini-button" type="button" data-knowledge-action="distribute" data-id="${entry.id}">Distribute list</button>` : ""}
        <button class="mini-button" type="button" data-knowledge-action="edit" data-id="${entry.id}">Edit</button>
        <button class="mini-button danger-button" type="button" data-knowledge-action="delete" data-id="${entry.id}">Delete</button>
      </div>
    </article>
  `).join("");
}

function firstName(name) {
  return String(name || "").trim().split(/\s+/)[0] || "Team member";
}

function initials(name) {
  return String(name || "M").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "M";
}

const avatarTones = ["gray", "blue", "green", "orange", "purple", "yellow", "red"];
function avatar(name, extra = "") {
  let hash = 0;
  for (const character of String(name || "")) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return `<span class="avatar ${avatarTones[hash % avatarTones.length]}${extra ? ` ${extra}` : ""}" aria-hidden="true">${escapeHtml(initials(name))}</span>`;
}

function dayLabel(value) {
  const date = new Date(value);
  const midnight = (day) => new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
  const diff = Math.round((midnight(new Date()) - midnight(date)) / 864e5);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

function renderJourneys(journeys) {
  const container = $("#journeys-list");
  $("#journeys-count").textContent = journeys.length;
  if (!journeys.length) {
    container.className = "journeys empty-state";
    container.textContent = "No blocker journeys recorded yet.";
    return;
  }
  container.className = "journeys";
  container.innerHTML = journeys.map((journey) => {
    const owner = journey.dependency_owner_name || "owner not identified yet";
    const status = journey.status === "resolved" ? "Resolved" : "Open";
    const events = journey.events.map((event, index) => `
      <li class="journey-event ${escapeHtml(event.event_type)}">
        <span class="journey-number">${index + 1}</span>
        <div class="journey-event-body">
          <div class="journey-event-heading"><span class="journey-tag">${escapeHtml(event.event_type.replaceAll("_", " "))}</span><strong>${escapeHtml(event.title)}</strong><time>${escapeHtml(dateTime(event.occurred_at))}</time></div>
          <p>${escapeHtml(event.detail)}</p>
        </div>
      </li>`).join("");
    const commitments = journey.commitments.length ? `<div class="journey-commitments">${journey.commitments.map((commitment) => `<span><strong>${escapeHtml(commitment.owner_name)}</strong> committed: ${escapeHtml(commitment.description)} · due ${escapeHtml(dateTime(commitment.deadline))} · ${escapeHtml(commitment.status)}</span>`).join("")}</div>` : "";
    return `<details class="journey-card">
      <summary class="journey-summary"><div><span class="journey-status ${journey.status === "resolved" ? "resolved" : "open"}">${status}</span><h3>${escapeHtml(journey.title)}</h3><p>${escapeHtml(journey.description)}</p></div><div class="journey-people"><span>Blocked: ${escapeHtml(firstName(journey.blocked_employee_name))}</span><span>Dependency: ${escapeHtml(firstName(owner))}</span></div></summary>
      <div class="journey-history"><ol class="journey-events">${events}</ol>${commitments}</div>
    </details>`;
  }).join("");
}

function renderMemory(facts, episodes) {
  state.memoryFacts = facts;
  state.memoryEpisodes = episodes;
  renderList("#memory-facts-list", facts, (fact) => item(
    `${fact.subject_text || fact.subject_type} ${String(fact.predicate || "").replaceAll("_", " ")} ${fact.object_text || fact.object_type || ""}`,
    `${fact.status} · observed ${dateTime(fact.observed_at)}`,
  ), "No derived facts yet. Use Update memory after management activity is recorded.");
  renderList("#memory-episodes-list", episodes, (episode) => item(
    episode.title,
    `${episode.summary} · ${dateTime(episode.started_at)}`,
  ), "No memory episodes yet.");
  const select = $("#memory-employee-select");
  const selected = select.value;
  select.innerHTML = `<option value="">Choose a team member</option>${state.employees.map((employee) => `<option value="${employee.id}">${escapeHtml(employee.name)}</option>`).join("")}`;
  select.value = selected;
}

function renderMemorySearch(results) {
  const container = $("#memory-search-results");
  container.hidden = false;
  const facts = results.facts || [];
  const episodes = results.episodes || [];
  if (!facts.length && !episodes.length) {
    container.innerHTML = `<p class="memory-search-empty">Nothing matched that search yet.</p>`;
    return;
  }
  container.innerHTML = `${facts.length ? `<div><strong>Facts</strong>${facts.map((fact) => `<p>${escapeHtml(`${fact.subject_text || fact.subject_type} ${String(fact.predicate || "").replaceAll("_", " ")} ${fact.object_text || fact.object_type || ""}`)}</p>`).join("")}</div>` : ""}${episodes.length ? `<div><strong>Past situations</strong>${episodes.map((episode) => `<p>${escapeHtml(episode.title)}<span>${escapeHtml(episode.summary)}</span></p>`).join("")}</div>` : ""}`;
}

function actionButton(label, action, id) {
  const help = {
    "daily-reminder": "Send this person a simple Teams reminder for today's update.",
    "resolve-blocker": "Mark this blocker as fixed.",
    "blocker-follow-up": "Send the dependency owner a Teams follow-up.",
    "mark-missed": "Mark this commitment as missed.",
    "revise-commitment": "Keep the old promise and enter a new deadline.",
    "acknowledge-escalation": "Mark that you have seen this escalation.",
    "resolve-escalation": "Close this escalation as resolved.",
  }[action] || "Perform this action.";
  return `<button class="mini-button" type="button" data-action="${action}" data-id="${id}" data-tooltip="${escapeHtml(help)}">${escapeHtml(label)}</button>`;
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function renderTeamsConnection() {
  const microsoft = state.microsoft;
  if (!microsoft) return;
  const connected = microsoft.is_connected && microsoft.connection;
  const name = connected ? microsoft.connection.display_name : "Microsoft account";
  const letters = connected ? initials(name) : "M";

  $("#account-menu-name").textContent = name;
  $("#account-avatar").textContent = letters;
  $("#settings-account-name").textContent = name;
  $("#settings-account-avatar").textContent = letters;
  $("#account-menu-email").textContent = connected ? microsoft.connection.user_principal_name : "No Microsoft account connected";
  updateProfileStatus();

  document.querySelectorAll("[data-connect-microsoft]").forEach((button) => {
    button.disabled = !microsoft.is_auth_configured;
    button.textContent = microsoft.is_connected ? "Switch Microsoft account" : "Connect Microsoft account";
    button.classList.toggle("secondary", Boolean(microsoft.is_connected));
  });
  renderSetup();
}

// A short checklist on Today and Agent until Teams and the AI provider are ready.
function renderSetup() {
  const steps = [];
  const microsoft = state.microsoft;
  if (microsoft && !microsoft.is_connected) {
    steps.push(microsoft.is_auth_configured
      ? { text: "Connect your Microsoft account so Prism can read your Teams chats and send replies you approve.", action: "connect", label: "Connect Microsoft account" }
      : { text: "Add the Microsoft settings to .env and restart the API to connect Teams." });
  }
  const provider = state.provider;
  if (v21Mode === true && provider && !provider.ready && provider.state !== "unavailable") {
    steps.push({ text: `AI provider: ${provider.detail}`, action: "provider", label: "Open settings" });
  }
  document.querySelectorAll("[data-setup]").forEach((container) => {
    container.hidden = steps.length === 0;
    container.innerHTML = steps.length
      ? `<span class="callout-icon" aria-hidden="true">👋</span><div class="callout-body"><strong>Finish setting up Prism</strong><ul class="setup-steps">${steps.map((step) => `<li><span>${escapeHtml(step.text)}</span>${step.action ? `<button class="mini-button" type="button" data-setup-action="${step.action}">${escapeHtml(step.label)}</button>` : ""}</li>`).join("")}</ul></div>`
      : "";
  });
}

function renderProviderStatus(provider) {
  state.provider = provider;
  updateProfileStatus();
  const label = provider.provider === "azure_openai" ? "Azure OpenAI" : provider.provider === "openai" ? "OpenAI" : provider.provider === "codex_local" ? "Local Codex" : humanize(provider.provider);
  $("#provider-status-name").textContent = provider.model ? `${label} · ${provider.model}` : label;
  $("#provider-status-detail").textContent = provider.detail;
  const badge = $("#provider-status-badge");
  badge.textContent = provider.ready ? "Ready" : humanize(provider.state);
  badge.className = `badge ${provider.ready ? "green" : provider.state === "disabled" ? "blue" : "orange"}`;
  $("#provider-nav-dot").hidden = provider.ready || provider.state === "unavailable";
  renderSetup();
  const savedKey = provider.credential_source === "database";
  $("#provider-key-help").textContent = savedKey
    ? `${provider.masked_key} is stored encrypted on this Prism server. Enter a new key to replace it.`
    : provider.can_manage
      ? "Stored encrypted on this Prism server. The key is never shown again."
      : "Configure a provider credential encryption key before saving a key.";
  $("#openai-model-input").value = savedKey && provider.model ? provider.model : ($("#openai-model-input").value || "gpt-4o-mini");
  $("#save-openai-key-button").disabled = !provider.can_manage;
  $("#remove-openai-key-button").hidden = !savedKey;
}

async function saveOpenAIKey(event) {
  event.preventDefault();
  const keyInput = $("#openai-key-input");
  const modelInput = $("#openai-model-input");
  const button = $("#save-openai-key-button");
  button.disabled = true;
  try {
    const provider = await api("/api/v1/provider/openai", {
      method: "PUT",
      body: JSON.stringify({ api_key: keyInput.value, model: modelInput.value }),
    });
    keyInput.value = "";
    renderProviderStatus(provider);
    setStatus("OpenAI key saved securely. Prism is now using OpenAI.");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = !state.provider?.can_manage;
  }
}

async function removeOpenAIKey() {
  const confirmed = await askDialog({
    title: "Remove saved OpenAI key?",
    message: "Prism will return to the provider configured on this server.",
    confirmLabel: "Remove key",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await api("/api/v1/provider/openai", { method: "DELETE" });
    const provider = await api("/api/v1/provider/status");
    renderProviderStatus(provider);
    setStatus("Saved OpenAI key removed.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

function renderAgentFoundation(foundation) {
  state.foundation = foundation;
  $("#agent-foundation-panel").hidden = false;
  $("#foundation-thread-count").textContent = foundation.threads;
  $("#foundation-job-count").textContent = foundation.jobs;
  $("#foundation-approval-count").textContent = foundation.pending_approvals;
  $("#foundation-execution-count").textContent = foundation.executions;
  const pending = foundation.pending_approvals;
  setNavCount("#nav-agent-count", pending);
  $("#approval-banner-title").textContent = pending ? `${pending} draft${pending === 1 ? "" : "s"} waiting for your approval` : "No drafts waiting";
  $("#approval-banner-text").textContent = pending
    ? "Open Prism to review each draft, edit it if needed, then approve to send."
    : "Choose a Teams chat and ask Prism what needs your attention.";
  $("#approval-banner-button").textContent = pending ? "Review drafts" : "Start a review";
  $("#approval-banner-button").classList.toggle("secondary", !pending);
}

function refreshFoundation() {
  return api("/api/v2/agent/foundation").then(renderAgentFoundation).catch(() => {});
}

async function loadDashboard() {
  $("#refresh-button").classList.add("spinning");
  api("/api/v1/provider/status")
    .then(renderProviderStatus)
    .catch(() => renderProviderStatus({ provider: "unknown", model: null, state: "unavailable", ready: false, detail: "Provider status is unavailable" }));
  api("/api/v2/agent/foundation")
    .then((foundation) => {
      applyV21Mode(true);
      renderAgentFoundation(foundation);
    })
    .catch(() => {
      applyV21Mode(false);
      $("#agent-foundation-panel").hidden = true;
    });
  api("/api/v2/prisms/foundation")
    .then((foundation) => applyV22Mode(true, foundation.single_executive_mode))
    .catch(() => applyV22Mode(false));
  api("/api/v2/qa/status")
    .then((status) => applyV24Mode(Boolean(status.computers)))
    .catch(() => applyV24Mode(false));
  try {
    const [employees, projects, tasks, updates, blockers, commitments, escalations, findings, journeys, knowledge, microsoft, memoryFacts, memoryEpisodes, attention, brief] = await Promise.all([
      api("/api/v1/employees?limit=100&is_active=true"),
      api("/api/v1/projects?limit=100"),
      api("/api/v1/tasks?limit=100"),
      api("/api/v1/daily-updates?limit=100&update_date=" + today()),
      api("/api/v1/blockers?limit=100&status=open"),
      api("/api/v1/commitments?limit=100&status=open"),
      api("/api/v1/escalations?limit=100&status=open"),
      api("/api/v1/management/rule-findings"),
      api("/api/v1/management/journeys"),
      api("/api/v1/management-context?limit=100"),
      api("/api/v1/microsoft/status"),
      api("/api/v1/memory/facts?limit=12&status=current"),
      api("/api/v1/memory/episodes?limit=8"),
      api("/api/v2/management/attention"),
      api("/api/v2/management/brief/daily"),
    ]);
    Object.assign(state, {
      employees: employees.items,
      projects: projects.items,
      tasks: tasks.items,
      blockers: blockers.items,
      commitments: commitments.items,
      escalations: escalations.items,
      journeys,
      knowledge: knowledge.items,
      attention,
      brief,
      microsoft,
    });
    $("#stat-employees").textContent = employees.total;
    $("#stat-updates").textContent = updates.total;
    $("#stat-blockers").textContent = blockers.total;
    $("#stat-commitments").textContent = commitments.total;
    $("#stat-escalations").textContent = escalations.total;
    $("#findings-count").textContent = findings.length;
    $("#updates-count").textContent = updates.total;
    $("#blockers-count").textContent = blockers.total;
    $("#commitments-count").textContent = commitments.total;
    $("#escalations-count").textContent = escalations.total;
    setNavCount("#nav-today-count", attention.length);
    setNavCount("#nav-work-count", blockers.total + commitments.total + escalations.total);

    renderTeamsConnection();
    renderJourneys(journeys);
    renderKnowledge(knowledge.items);
    renderMemory(memoryFacts.items, memoryEpisodes);
    renderAttention(attention);
    renderBrief(brief);

    const missingUpdates = employees.items.filter((employee) => !updates.items.some((update) => update.employee_id === employee.id));
    $("#missing-updates-count").textContent = missingUpdates.length;
    renderList("#missing-updates-list", missingUpdates, (employee) => itemWithActions(
      employee.name,
      `${employee.role} has not sent an update today.`,
      actionButton("Record Teams reminder", "daily-reminder", employee.id),
    ), "Everyone has submitted an update today.");
    renderList("#findings-list", findings, (finding) => item(finding.reason, finding.severity.replace("_", " ")), "No active rule findings.");
    renderList("#blockers-list", blockers.items, (blocker) => {
      const actions = [actionButton("Mark resolved", "resolve-blocker", blocker.id)];
      if (blocker.dependency_owner_id) actions.push(actionButton("Record Teams follow-up", "blocker-follow-up", blocker.id));
      const blockedPerson = nameFor(blocker.blocked_employee_id);
      const dependencyOwner = (blocker.dependency_owner_ids || []).map(nameFor).join(", ") || "Not assigned";
      return itemWithActions(blocker.description, `Blocked: ${blockedPerson} · Dependency owner: ${dependencyOwner} · Severity: ${blocker.severity}`, actions.join(""));
    }, "No open blockers.");
    renderList("#commitments-list", commitments.items, (commitment) => itemWithActions(
      commitment.description,
      `Responsible: ${nameFor(commitment.employee_id)} · Deadline: ${dateTime(commitment.deadline)} · Status: ${commitment.status}`,
      `${actionButton("Mark missed", "mark-missed", commitment.id)}${actionButton("Missed + revised ETA", "revise-commitment", commitment.id)}`,
    ), "No open commitments.");
    renderList("#updates-list", updates.items, (update) => item(nameFor(update.employee_id), update.today_summary), "No updates received today.");
    renderList("#escalations-list", escalations.items, (escalation) => itemWithActions(
      escalation.reason,
      `${escalation.escalation_type.replaceAll("_", " ")} · ${escalation.severity}`,
      `${actionButton("Acknowledge", "acknowledge-escalation", escalation.id)}${actionButton("Resolve", "resolve-escalation", escalation.id)}`,
    ), "No open escalations.");
    renderSelectedForm();
  } catch (error) {
    setStatus(error.message + ". Check that the API and database are running.", true);
  } finally {
    $("#refresh-button").classList.remove("spinning");
  }
}

function optionMarkup(type) {
  const records = state[type] || [];
  if (type === "employees") return records.map((employee) => `<option value="${employee.id}">${escapeHtml(employee.name)} — ${escapeHtml(employee.role)}</option>`).join("");
  if (type === "projects") return records.map((project) => `<option value="${project.id}">${escapeHtml(project.name)}</option>`).join("");
  if (type === "tasks") return records.map((task) => `<option value="${task.id}">${escapeHtml(task.title)}</option>`).join("");
  if (type === "blockers") return records.map((blocker) => `<option value="${blocker.id}">${escapeHtml(blocker.description.slice(0, 70))}</option>`).join("");
  return "";
}

function renderSelectedForm() {
  const kind = $("#form-selector").value;
  const template = $("#" + kind + "-form");
  const container = $("#form-container");
  container.innerHTML = "";
  container.append(template.content.cloneNode(true));
  container.querySelectorAll("[data-options]").forEach((select) => {
    select.insertAdjacentHTML("beforeend", optionMarkup(select.dataset.options));
  });
  container.querySelectorAll("[data-today]").forEach((input) => { input.value = today(); });
  container.querySelector("form").addEventListener("submit", submitForm);
}

function payloadFor(form) {
  const payload = {};
  new FormData(form).forEach((value, key) => {
    const normalized = String(value).trim();
    if (!normalized) return;
    payload[key] = normalized;
  });
  if (payload.deadline) payload.deadline = new Date(payload.deadline).toISOString();
  return payload;
}

async function submitForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    await api(form.dataset.endpoint, { method: "POST", body: JSON.stringify(payloadFor(form)) });
    form.reset();
    $("#record-dialog").close();
    setStatus("Saved successfully.");
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function submitKnowledgeContext(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const data = new FormData(form);
  const payload = {
    category: String(data.get("category") || "").trim(),
    title: String(data.get("title") || "").trim(),
    content: String(data.get("content") || "").trim(),
  };
  button.disabled = true;
  try {
    const isEditing = Boolean(editingKnowledgeId);
    await api(
      isEditing ? `/api/v1/management-context/${editingKnowledgeId}` : "/api/v1/management-context",
      { method: isEditing ? "PATCH" : "POST", body: JSON.stringify(payload) },
    );
    resetKnowledgeForm();
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function resetKnowledgeForm() {
  editingKnowledgeId = null;
  const form = $("#knowledge-context-form");
  form.reset();
  $("#knowledge-submit-button").textContent = "Save context";
  $("#cancel-knowledge-edit").hidden = true;
}

function editKnowledge(entryId) {
  const entry = state.knowledge.find((item) => item.id === entryId);
  if (!entry) return;
  editingKnowledgeId = entry.id;
  const form = $("#knowledge-context-form");
  form.elements.category.value = entry.category;
  form.elements.title.value = entry.title;
  form.elements.content.value = entry.content;
  $("#knowledge-submit-button").textContent = "Update context";
  $("#cancel-knowledge-edit").hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  form.elements.title.focus();
}

async function deleteKnowledge(entryId) {
  const entry = state.knowledge.find((item) => item.id === entryId);
  if (!entry || !await askDialog({ title: `Delete “${entry.title}”?`, message: "It will be removed from Prism's saved knowledge.", confirmLabel: "Delete", danger: true })) return;
  try {
    await api(`/api/v1/management-context/${entryId}`, { method: "DELETE" });
    if (editingKnowledgeId === entryId) resetKnowledgeForm();
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function distributeDeploymentList(entryId) {
  const entry = state.knowledge.find((item) => item.id === entryId);
  if (!entry || !await askDialog({ title: `Distribute “${entry.title}”?`, message: "It will be sent to its owners in the active automation run.", confirmLabel: "Distribute" })) return;
  try {
    const result = await api(
      `/api/v1/management-context/${entryId}/distribute-deployment-list`,
      { method: "POST" },
    );
    const failureText = result.failures.length ? ` ${result.failures.length} delivery failure(s); task state was not changed.` : "";
    setStatus(`Deployment list: ${result.delivered.length} delivered, ${result.skipped.length} already delivered, ${result.task_changes} task change(s).${failureText}`, Boolean(result.failures.length));
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function recordMessageIntent(employeeId, content) {
  await api("/api/v1/message-intents", {
    method: "POST",
    body: JSON.stringify({ employee_id: employeeId, channel: "teams", content }),
  });
  setStatus("Teams follow-up recorded locally. It has not been sent.");
}

async function handleAction(button) {
  const { action, id } = button.dataset;
  button.disabled = true;
  try {
    if (action === "daily-reminder") {
      const employee = state.employees.find((item) => item.id === id);
      await recordMessageIntent(id, `Hi ${employee.name}, please share your daily update for today: what you completed, what you will deliver today, and any blockers.`);
    }
    if (action === "blocker-follow-up") {
      const blocker = state.blockers.find((item) => item.id === id);
      const owner = state.employees.find((item) => item.id === blocker.dependency_owner_id);
      await recordMessageIntent(owner.id, `Hi ${owner.name}, ${nameFor(blocker.blocked_employee_id)} is blocked: ${blocker.description} Please share a specific ETA.`);
    }
    if (action === "resolve-blocker") {
      if (!await askDialog({ title: "Mark blocker as resolved?", confirmLabel: "Resolve" })) return;
      await api(`/api/v1/blockers/${id}`, { method: "PATCH", body: JSON.stringify({ status: "resolved" }) });
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
      await api(`/api/v1/commitments/${id}/mark-missed`, { method: "POST", body: JSON.stringify(reason.trim() ? { reason: reason.trim() } : {}) });
      setStatus("Commitment marked as missed. It remains in its history.");
    }
    if (action === "revise-commitment") {
      selectedCommitmentId = id;
      $("#revision-form").reset();
      $("#revision-dialog").showModal();
      return;
    }
    if (action === "acknowledge-escalation") {
      await api(`/api/v1/escalations/${id}/acknowledge`, { method: "POST" });
      setStatus("Escalation acknowledged.");
    }
    if (action === "resolve-escalation") {
      if (!await askDialog({ title: "Resolve this escalation?", confirmLabel: "Resolve" })) return;
      await api(`/api/v1/escalations/${id}/resolve`, { method: "POST" });
      setStatus("Escalation resolved.");
    }
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
    renderTeamsConnection();
  } finally {
    button.disabled = false;
  }
}

async function connectMicrosoft() {
  if (!state.microsoft || !state.microsoft.is_auth_configured) {
    setStatus("Add the Microsoft values and encryption key to .env, then restart the API.", true);
    return;
  }
  if (state.microsoft.is_connected && !await askDialog({
    title: "Switch Microsoft account?",
    message: `Switch from ${state.microsoft.connection.display_name} to a different account.`,
    confirmLabel: "Switch",
  })) return;
  window.location.assign("/api/v1/microsoft/auth/start");
}

async function createDummyJourney() {
  const button = $("#create-dummy-journey-button");
  button.disabled = true;
  try {
    const result = await api("/api/v1/management/dummy-journey", { method: "POST" });
    state.journeys = [result.journey, ...state.journeys.filter((item) => item.blocker_id !== result.blocker_id)];
    renderJourneys(state.journeys);
    button.textContent = "Preview created";
    setStatus(result.message);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function consolidateMemory() {
  const button = $("#consolidate-memory-button");
  button.disabled = true;
  try {
    const backfill = await api("/api/v1/memory/backfill", { method: "POST" });
    const result = await api("/api/v1/memory/consolidate", { method: "POST" });
    const queued = Object.values(backfill).reduce((total, count) => total + count, 0);
    setStatus(`Memory updated: ${queued} existing record(s) queued; ${result.processed} event(s) processed, ${result.facts} fact(s), ${result.episodes} situation(s), and ${result.relations} relationship(s) added.`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function runIntelligence() {
  const button = $("#run-intelligence-button");
  button.disabled = true;
  try {
    const result = await api("/api/v2/management/intelligence/run", { method: "POST" });
    setStatus(`Intelligence refreshed: ${result.active_risks} active risk(s), ${result.decisions_created} new decision(s), ${result.no_action} no-action decision(s). No Teams messages were sent.`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function askManagementQuestion(event) {
  event.preventDefault();
  const input = $("#management-query-input");
  const button = event.currentTarget.querySelector("button[type=submit]");
  const question = input.value.trim();
  if (!question) return;
  button.disabled = true;
  try {
    renderManagementAnswer(await api("/api/v2/management/query", { method: "POST", body: JSON.stringify({ question }) }));
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function searchMemory(event) {
  event.preventDefault();
  const query = $("#memory-search-input").value.trim();
  if (!query) return;
  try {
    renderMemorySearch(await api(`/api/v1/memory/search?q=${encodeURIComponent(query)}&include_history=true`));
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadMemoryContext() {
  const employeeId = $("#memory-employee-select").value;
  if (!employeeId) return;
  const output = $("#memory-context-output");
  output.textContent = "Loading context…";
  try {
    const context = await api(`/api/v1/memory/context/${employeeId}`);
    const sections = [
      ["Current work", context.current_work],
      ["Current blockers", context.current_blockers],
      ["Open commitments", context.open_commitments],
      ["Relevant memory", context.relevant_facts],
      ["Past situations", context.relevant_episodes],
      ["Relationships", context.relevant_relations],
    ].filter(([, values]) => values && values.length);
    output.textContent = sections.length ? sections.map(([title, values]) => `${title}\n${values.map((value) => `- ${value}`).join("\n")}`).join("\n\n") : "No relevant context is available yet.";
  } catch (error) {
    output.textContent = "Could not load context.";
    setStatus(error.message, true);
  }
}

async function submitRevision(event) {
  event.preventDefault();
  const reason = $("#revision-reason").value.trim();
  const description = $("#revision-description").value.trim();
  const deadline = $("#revision-deadline").value;
  if (!selectedCommitmentId || !reason || !description || !deadline) return;
  try {
    await api(`/api/v1/commitments/${selectedCommitmentId}/mark-missed`, {
      method: "POST", body: JSON.stringify({ reason }),
    });
    await api(`/api/v1/commitments/${selectedCommitmentId}/revisions`, {
      method: "POST",
      body: JSON.stringify({ description, missed_reason: reason, deadline: new Date(deadline).toISOString() }),
    });
    $("#revision-dialog").close();
    selectedCommitmentId = null;
    setStatus("Missed commitment and revised ETA saved with full history.");
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
}

function setTheme(choice) {
  window.prismTheme.set(choice);
}

function syncThemeControls() {
  const choice = window.prismTheme.choice;
  document.querySelectorAll("[data-profile-theme]").forEach((button) => {
    button.setAttribute("aria-checked", String(button.dataset.profileTheme === choice));
  });
}
document.addEventListener("prism:theme", syncThemeControls);

function closeProfileMenu() {
  const menu = $("#profile-menu");
  if (!menu) return;
  menu.hidden = true;
  $("#profile-menu-trigger").setAttribute("aria-expanded", "false");
  $("#profile-status-details").hidden = true;
}

function positionProfileMenu() {
  const menu = $("#profile-menu");
  if (menu.hidden) return;
  // Layout pixels: getBoundingClientRect and innerWidth are visual, style values are zoomed.
  const z = window.prismUi.zoom();
  const rect = (element) => { const box = element.getBoundingClientRect(); return { left: box.left / z, right: box.right / z, top: box.top / z, bottom: box.bottom / z, width: box.width / z }; };
  const viewW = innerWidth / z, viewH = innerHeight / z;
  const row = rect($(".profile-row") || $("#profile-menu-trigger"));
  const gap = 8, edge = 12;
  menu.style.width = `${Math.min(row.width, viewW - edge * 2)}px`;
  const above = row.top - menu.offsetHeight - gap;
  menu.style.left = `${Math.max(edge, Math.min(row.left, viewW - menu.offsetWidth - edge))}px`;
  menu.style.top = `${above >= edge ? above : Math.max(edge, Math.min(row.bottom + gap, viewH - menu.offsetHeight - edge))}px`;
}

function openProfileMenu(last = false) {
  $("#profile-menu").hidden = false;
  $("#profile-menu-trigger").setAttribute("aria-expanded", "true");
  positionProfileMenu();
  const items = $("#profile-menu").querySelectorAll(".profile-menu-group > [role='menuitem']");
  items[last ? items.length - 1 : 0]?.focus();
}

function updateProfileStatus() {
  const detail = $("#profile-status-details");
  if (!detail) return;
  const provider = state.provider?.ready ? "AI provider ready" : "AI provider needs attention";
  const microsoft = state.microsoft?.is_connected ? "Microsoft Teams connected" : "Microsoft Teams not connected";
  const computer = v24Mode === true ? "Computer features available" : "Computer features unavailable";
  detail.textContent = `${provider} · ${microsoft} · ${computer}`;
  $("#profile-status-dot").classList.toggle("warn", !state.provider?.ready || !state.microsoft?.is_connected);
  window.prismStatus = { provider: state.provider, microsoft: state.microsoft, computers: v24Mode };
  document.dispatchEvent(new CustomEvent("prism:status", { detail: window.prismStatus }));
}

$("#profile-menu-trigger").addEventListener("click", () => {
  if ($("#profile-menu").hidden) openProfileMenu();
  else closeProfileMenu();
});
$("#profile-menu-trigger").addEventListener("keydown", (event) => {
  if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
  event.preventDefault();
  openProfileMenu(event.key === "ArrowUp");
});
window.addEventListener("resize", positionProfileMenu);
document.querySelector(".workspace").addEventListener("scroll", positionProfileMenu, { passive: true });
document.addEventListener("click", (event) => {
  const theme = event.target.closest("[data-profile-theme]");
  if (theme) { setTheme(theme.dataset.profileTheme); return; }
  const action = event.target.closest("[data-profile-action]")?.dataset.profileAction;
  if (action === "settings" || action === "account" || action === "workspace") {
    openSettings(action === "account" ? "account" : action === "workspace" ? "general" : undefined);
  } else if (action === "status") {
    updateProfileStatus();
    $("#profile-status-details").hidden = !$("#profile-status-details").hidden;
    positionProfileMenu();
  } else if (action === "signout") {
    closeProfileMenu();
    const key = localStorage.getItem(operatorTokenKey);
    if (!key) { setStatus("Local mode has no sign-in session to end."); return; }
    askDialog({ title: "Sign out of this browser?", message: "This removes the operator access key stored in this browser. It will not disconnect Microsoft Teams.", confirmLabel: "Sign out" }).then((confirmed) => {
      if (!confirmed) return;
      localStorage.removeItem(operatorTokenKey);
      window.location.reload();
    });
  } else if (event.target.closest("#profile-menu [data-connect-microsoft]") || !event.target.closest("#profile-menu, #profile-menu-trigger")) closeProfileMenu();
});
document.addEventListener("keydown", (event) => {
  if ($("#profile-menu").hidden) return;
  if (event.key === "Tab") { closeProfileMenu(); $("#profile-menu-trigger").focus(); return; }
  if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeProfileMenu(); $("#profile-menu-trigger").focus(); return; }
  const inTheme = event.target.closest(".profile-theme-options");
  if (inTheme && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
    event.preventDefault();
    const radios = [...inTheme.querySelectorAll("[role='radio']")];
    radios[(radios.indexOf(event.target) + (event.key === "ArrowLeft" ? -1 : 1) + radios.length) % radios.length]?.focus();
    return;
  }
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || !event.target.closest("#profile-menu")) return;
  event.preventDefault();
  const items = [...$("#profile-menu").querySelectorAll(".profile-menu-group > [role='menuitem'], .profile-theme-options [aria-checked='true']")];
  const index = items.indexOf(document.activeElement);
  const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length;
  items[next]?.focus();
});
document.querySelectorAll("[data-settings-link]").forEach((button) => button.addEventListener("click", () => {
  if (button.dataset.settingsLink === "spending") { closeSettings(); setActiveTab("spending"); return; }
  document.querySelector(`[data-subtab-target="${button.dataset.settingsLink}"]`)?.click();
}));

// Settings is a Notion-style modal over whatever page is open; Escape and the backdrop close it.
const settingsDialog = $("#settings-dialog");
function openSettings(subtab) {
  closeProfileMenu();
  if (!settingsDialog.open) settingsDialog.showModal();
  if (subtab) setSubtab("settings", subtab);
  window.prismRoutes?.settings(settingsDialog.querySelector("[data-subtab-target].active")?.dataset.subtabTarget || "general");
  document.dispatchEvent(new CustomEvent("prism:tab", { detail: { tab: "settings" } }));
  (subtab ? $(`[data-subtab-target="${subtab}"]`) : settingsDialog.querySelector("[data-subtab-target].active"))?.focus();
}
function closeSettings() { if (settingsDialog.open) settingsDialog.close(); }
$("#settings-close").addEventListener("click", closeSettings);
settingsDialog.addEventListener("click", (event) => { if (event.target === settingsDialog) closeSettings(); });
settingsDialog.addEventListener("close", () => { if (!settingsDialog.open) window.prismRoutes?.settingsClosed(); });
window.prism.openSettings = openSettings;
window.prism.closeSettings = closeSettings;

const appShell = $("#app");
const narrowQuery = window.matchMedia("(max-width: 820px)");

function toggleSidebar(open) {
  if (narrowQuery.matches) {
    appShell.classList.toggle("sidebar-open", open);
    return;
  }
  appShell.classList.toggle("sidebar-collapsed", !open);
  localStorage.setItem("manager-agent-sidebar", open ? "open" : "closed");
}

$("#sidebar-close").addEventListener("click", () => toggleSidebar(false));
$("#sidebar-open").addEventListener("click", () => toggleSidebar(true));
document.querySelectorAll(".chat-sidebar-open").forEach((button) => button.addEventListener("click", () => toggleSidebar(true)));
$("#scrim").addEventListener("click", () => toggleSidebar(false));
$("#confirm-cancel").addEventListener("click", () => $("#confirm-dialog").close("cancel"));
$("#refresh-button").addEventListener("click", loadDashboard);
$("#operator-token-button").addEventListener("click", setOperatorToken);
$("#openai-key-form").addEventListener("submit", saveOpenAIKey);
$("#remove-openai-key-button").addEventListener("click", removeOpenAIKey);
document.querySelectorAll("[data-connect-microsoft]").forEach((button) => button.addEventListener("click", connectMicrosoft));
$("#new-record-button").addEventListener("click", () => $("#record-dialog").showModal());
$("#record-close").addEventListener("click", () => $("#record-dialog").close());
$("#approval-banner-button").addEventListener("click", () => {
  if (state.foundation?.pending_approvals) setActiveTab("agent");
  else document.dispatchEvent(new CustomEvent("prism:new-chat"));
});
document.addEventListener("prism:agent-changed", refreshFoundation);
$("#create-dummy-journey-button").addEventListener("click", createDummyJourney);
$("#consolidate-memory-button").addEventListener("click", consolidateMemory);
$("#run-intelligence-button").addEventListener("click", runIntelligence);
$("#management-query-form").addEventListener("submit", askManagementQuestion);
$("#memory-search-form").addEventListener("submit", searchMemory);
$("#load-memory-context-button").addEventListener("click", loadMemoryContext);
$("#knowledge-context-form").addEventListener("submit", submitKnowledgeContext);
$("#cancel-knowledge-edit").addEventListener("click", resetKnowledgeForm);
$("#form-selector").addEventListener("change", renderSelectedForm);
document.addEventListener("click", (event) => {
  const suggestion = event.target.closest("[data-query]");
  if (suggestion) {
    $("#management-query-input").value = suggestion.dataset.query;
    $("#management-query-form").requestSubmit();
  }
  const setupAction = event.target.closest("[data-setup-action]");
  if (setupAction?.dataset.setupAction === "connect") connectMicrosoft();
  if (setupAction?.dataset.setupAction === "provider") {
    setActiveTab("settings");
    setSubtab("settings", "provider");
  }
  const button = event.target.closest("[data-action]");
  if (button) handleAction(button);
  const knowledgeButton = event.target.closest("[data-knowledge-action]");
  if (knowledgeButton?.dataset.knowledgeAction === "edit") editKnowledge(knowledgeButton.dataset.id);
  if (knowledgeButton?.dataset.knowledgeAction === "delete") deleteKnowledge(knowledgeButton.dataset.id);
  if (knowledgeButton?.dataset.knowledgeAction === "distribute") distributeDeploymentList(knowledgeButton.dataset.id);
});
$("#revision-form").addEventListener("submit", submitRevision);
$("#revision-cancel").addEventListener("click", () => $("#revision-dialog").close());
syncThemeControls();
if (!narrowQuery.matches && localStorage.getItem("manager-agent-sidebar") === "closed") appShell.classList.add("sidebar-collapsed");
document.querySelectorAll("[data-tab-target]").forEach((button) => button.addEventListener("click", () => {
  setActiveTab(button.dataset.tabTarget);
  if (narrowQuery.matches) toggleSidebar(false);
}));
document.querySelectorAll("[data-sidebar-target]").forEach((button) => button.addEventListener("click", () => setSidebarSection(button.dataset.sidebarTarget)));
$("#sidebar-notify-settings")?.addEventListener("click", () => {
  setActiveTab("settings");
  setSubtab("settings", "notifications");
  if (narrowQuery.matches) toggleSidebar(false);
});
$(".sidebar-tabs")?.addEventListener("keydown", (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const buttons = [...document.querySelectorAll("[data-sidebar-target]")].filter((button) => !button.hidden);
  const index = buttons.indexOf(document.activeElement);
  if (index < 0) return;
  event.preventDefault();
  const next = buttons[(index + (event.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length];
  next.focus();
  setSidebarSection(next.dataset.sidebarTarget);
});
document.querySelectorAll("[data-subtabs]").forEach((root) => {
  const group = root.dataset.subtabs;
  root.querySelectorAll("[data-subtab-target]").forEach((button) => button.addEventListener("click", () => setSubtab(group, button.dataset.subtabTarget)));
  root.addEventListener("keydown", (event) => {
    if (!event.target.matches("[data-subtab-target]") || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    const buttons = [...root.querySelectorAll("[data-subtab-target]")].filter((button) => !button.hidden && !button.disabled && button.getClientRects().length);
    const index = buttons.indexOf(event.target);
    if (index < 0) return;
    event.preventDefault();
    const previous = event.key === "ArrowLeft" || event.key === "ArrowUp";
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (previous ? -1 : 1) + buttons.length) % buttons.length;
    buttons[next].focus();
    buttons[next].click();
  });
  let saved = null;
  try { saved = localStorage.getItem(subtabKey(group)); } catch (_) { /* private mode */ }
  setSubtab(group, saved || (group === "settings" ? "preferences" : root.querySelector("[data-subtab-target]").dataset.subtabTarget));
});
setSidebarSection(sidebarSection);
setActiveTab(state.activeTab);
const microsoftResult = new URLSearchParams(window.location.search);
if (microsoftResult.get("microsoft") === "connected") setStatus("Microsoft account connected. Import your organization directory next.");
if (microsoftResult.get("microsoft_error")) setStatus(microsoftResult.get("microsoft_error"), true);
loadDashboard();
