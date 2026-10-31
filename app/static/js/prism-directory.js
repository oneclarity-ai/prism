import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
const ui = () => window.prism || {};
const selectedKey = "prism-v22-selected-id";
const state = { enabled: false, includeArchived: false, prisms: [], loading: false, selectedId: localStorage.getItem(selectedKey), onboarding: null, answering: null, agreement: null, conversation: null, editingQuestionId: null, renderedId: null, pending: null, sourceCatalog: [], selectedSources: [], pendingSources: null, sourcePolicy: null, activity: null, observations: null, updates: new Map(), pendingPolicy: null, triggerPolicy: null, runs: null };

function textElement(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined) element.textContent = value;
  return element;
}
function formatTime(value) { return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : ""; }
function stateLabel(prism) {
  const value = String(prism.state || "unknown").toLowerCase();
  if (value === "draft") return "Draft";
  if (value === "onboarding") return "Onboarding";
  if (value === "awaiting_confirmation") return "Review needed";
  return value.replaceAll("_", " ");
}
function clock(value) { return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
function dayLabel(value) {
  const date = new Date(value);
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(value).setHours(0, 0, 0, 0)) / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return date.toLocaleDateString([], { month: "long", day: "numeric", year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
}
function initial(name) { return (String(name || "").trim()[0] || "P").toUpperCase(); }
function isArchived(prism) { return String(prism.state).toLowerCase() === "archived"; }
// An active Prism is worked in the full Assistant Prism chat; Prisms that are
// still being set up (draft, onboarding, review) use the onboarding chat.
function isWorking(prism) { return String(prism?.state).toLowerCase() === "active"; }
function currentView() { return document.getElementById("app")?.dataset.view; }
function syncView() {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  const view = currentView();
  if (!prism || (view !== "prisms" && view !== "agent")) return;
  if (isWorking(prism)) {
    if (view !== "agent") ui().setActiveTab?.("agent");
    document.dispatchEvent(new CustomEvent("prism:open-agent", { detail: { prism } }));
  } else if (view === "agent") ui().setActiveTab?.("prisms");
}
function selectPrism(prismId) {
  state.selectedId = prismId;
  state.editingQuestionId = null;
  state.onboarding = null;
  state.agreement = null;
  state.conversation = null;
  state.sourcePolicy = null;
  state.activity = null;
  state.observations = null;
  state.triggerPolicy = null;
  state.runs = null;
  state.selectedSources = [];
  state.pendingSources = null;
  localStorage.setItem(selectedKey, prismId);
  render();
  loadOnboarding();
}

function render() {
  const list = $("#prism-directory-list");
  if (!list) return;
  list.replaceChildren();
  if (state.loading && !state.prisms.length) list.append(textElement("p", "prism-nav-empty", "Loading…"));
  else if (!state.prisms.length) list.append(textElement("p", "prism-nav-empty", "No Prisms yet."));
  else state.prisms.forEach((prism) => list.append(renderNavItem(prism)));
  if (
    !state.loading &&
    state.prisms.length &&
    state.selectedId &&
    !state.prisms.some((prism) => prism.id === state.selectedId)
  ) {
    state.selectedId = null;
    state.onboarding = null;
    state.agreement = null;
    state.conversation = null;
    localStorage.removeItem(selectedKey);
  }
  renderWorkspace();
  syncView();
}

// Switching from another tab changes the view after selectPrism's render, so tell the chat explicitly.
function openPrismView(prism) {
  selectPrism(prism.id);
  ui().setActiveTab?.(isWorking(prism) ? "agent" : "prisms");
  if (isWorking(prism)) document.dispatchEvent(new CustomEvent("prism:open-agent", { detail: { prism } }));
}
function renderNavItem(prism) {
  const item = textElement("button", "nav-item prism-nav-item");
  item.type = "button";
  item.title = prism.description;
  if (prism.id === state.selectedId) item.classList.add("selected");
  item.setAttribute("aria-current", prism.id === state.selectedId ? "page" : "false");
  item.append(textElement("span", "prism-icon", initial(prism.name)), textElement("span", "nav-text", prism.name));
  if (prism.state === "draft" || isArchived(prism)) item.append(textElement("span", "nav-count", stateLabel(prism)));
  const unread = state.updates.get(prism.id);
  if (unread?.unread) {
    const badge = textElement("span", `nav-count ${unread.urgent_unread ? "urgent" : "approval"}`, String(unread.unread));
    badge.title = `${unread.unread} unread update${unread.unread === 1 ? "" : "s"}${unread.urgent_unread ? `, ${unread.urgent_unread} urgent` : ""}`;
    item.setAttribute("aria-label", `${prism.name}, ${badge.title}`);
    item.append(badge);
  }
  item.addEventListener("click", () => {
    openPrismView(prism);
    if (window.matchMedia("(max-width: 820px)").matches) document.getElementById("scrim")?.click();
  });
  return item;
}

function bubble(speaker, message, kind = "assistant", time = null, meta = null) {
  if (kind === "user") {
    const row = textElement("div", "turn user");
    const box = textElement("div", "bubble");
    box.append(textElement("p", "", message));
    row.append(box);
    return row;
  }
  const row = textElement("div", "turn assistant");
  const body = textElement("div", "turn-body");
  const head = textElement("div", "turn-head");
  head.append(textElement("strong", "", speaker));
  if (meta) head.append(textElement("span", "turn-meta", meta));
  if (time) {
    const stamp = textElement("time", "", clock(time));
    stamp.dateTime = time;
    stamp.title = formatTime(time);
    head.append(stamp);
  }
  body.append(head, textElement("p", "turn-text", message));
  row.append(textElement("span", "avatar prism", initial(speaker)), body);
  return row;
}
function typingIndicator(name, stage) {
  const row = textElement("div", "turn assistant turn-typing");
  row.setAttribute("role", "status");
  const body = textElement("div", "turn-body");
  const dots = textElement("span", "typing-dots");
  dots.setAttribute("aria-hidden", "true");
  dots.append(textElement("i"), textElement("i"), textElement("i"));
  body.append(dots, textElement("span", "typing-label", stage || `${name} is thinking…`));
  row.append(textElement("span", "avatar prism", initial(name)), body);
  return row;
}
function setPending(stage) {
  if (!state.pending) return;
  state.pending.stage = stage;
  state.forceScroll = true;
  renderWorkspace();
}
function setSendLabel(label) {
  $("#prism-onboarding-next").textContent = label;
}
function autoGrow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
}
function clearWorkspace() {
  $("#prism-onboarding-stream").replaceChildren();
  $("#prism-onboarding-form").hidden = true;
  $("#prism-source-control").hidden = true;
  $("#prism-onboarding-error").hidden = true;
  $("#prism-policy-button").hidden = true;
  $("#prism-trigger-button").hidden = true;
  $("#prism-sync-button").hidden = true;
  $("#prism-notify-button").hidden = true;
  $("#prism-health-button").hidden = true;
  $("#prism-pinned").hidden = true;
  setMenuOpen(false);
}
function renderWorkspace() {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  const empty = $("#prism-workspace-empty");
  const workspace = $("#prism-onboarding-workspace");
  if (!prism) {
    empty.hidden = false;
    workspace.hidden = true;
    clearWorkspace();
    return;
  }
  empty.hidden = true;
  workspace.hidden = false;
  const scroller = $("#prism-scroll");
  const switched = state.renderedId !== prism.id;
  const nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
  state.renderedId = prism.id;
  const force = state.forceScroll;
  state.forceScroll = false;
  $("#prism-conversation-title").textContent = prism.name;
  $("#prism-conversation-subtitle").textContent = "Private conversation";
  const badge = $("#prism-conversation-state");
  badge.className = `prism-state ${prism.state}`;
  badge.textContent = stateLabel(prism);
  $("#prism-edit-label").textContent = isArchived(prism) ? "View details" : "Edit Prism";
  $("#prism-archive-button").hidden = isArchived(prism);
  const active = String(prism.state).toLowerCase() === "active";
  $("#prism-policy-button").hidden = !active;
  $("#prism-trigger-button").hidden = !active;
  $("#prism-sync-button").hidden = !active;
  $("#prism-notify-button").hidden = !active;
  $("#prism-health-button").hidden = !active;
  renderPinned(prism, active);
  const stream = $("#prism-onboarding-stream");
  // Answer chips live in the stream during onboarding; park them before it is cleared.
  $("#prism-onboarding-form").prepend($("#prism-onboarding-choices"));
  stream.replaceChildren();
  $("#prism-onboarding-form").hidden = true;
  if (isArchived(prism)) {
    stream.append(bubble("Prism", "This Prism is archived and its onboarding record is read-only."));
  } else if (active) {
    renderConversation(stream, prism);
  } else if (state.onboarding === "missing") {
    stream.append(bubble(prism.name, `Hi, I’m ${prism.name}. Before I start helping, I’d like to learn how you work. It takes a few quick questions, and everything stays private to me.`));
    const start = textElement("button", "button", "Let’s get started");
    start.type = "button";
    start.addEventListener("click", startOnboarding);
    const actions = textElement("div", "chat-actions");
    actions.append(start);
    stream.append(actions);
  } else if (state.onboarding === "loading" || !state.onboarding) {
    stream.append(textElement("div", "chat-note", "Loading this Prism’s conversation…"));
  } else if (state.onboarding === "error") {
    stream.append(textElement("div", "chat-note inline-error", "Onboarding could not be loaded. Try selecting this Prism again."));
  } else {
    renderOnboardingConversation(stream, state.onboarding);
  }
  if (switched || nearBottom || force) scroller.scrollTop = scroller.scrollHeight;
}
function renderConversation(stream, prism) {
  if (state.conversation === "loading" || !state.conversation) {
    stream.append(textElement("div", "chat-note", "Loading this Prism’s private conversation…"));
    return;
  }
  if (state.conversation === "error") {
    stream.append(textElement("div", "chat-note inline-error", "This Prism’s conversation could not be loaded. Select it again to retry."));
    return;
  }
  const conversation = state.conversation;
  if (!conversation.messages.length) {
    stream.append(bubble(prism.name, "I’m ready. Ask me about your team’s work, or tell me what you want me to remember for this Prism."));
  } else {
    let lastDay = null;
    conversation.messages.forEach((message) => {
      const day = message.created_at ? new Date(message.created_at).toDateString() : null;
      if (day && day !== lastDay) {
        stream.append(textElement("div", "chat-day", dayLabel(message.created_at)));
        lastDay = day;
      }
      stream.append(bubble(message.role === "manager" ? "You" : prism.name, message.content, message.role === "manager" ? "user" : "assistant", message.created_at));
    });
  }
  if (state.pending && state.pending.prismId === prism.id) {
    stream.append(bubble("You", state.pending.content, "user"));
    stream.append(typingIndicator(prism.name, state.pending.stage));
  }
  if (conversation.preferences?.length) {
    const memory = textElement("details", "chat-card");
    memory.append(textElement("summary", "", `What ${prism.name} remembers · ${conversation.preferences.length}`));
    const list = document.createElement("ul");
    conversation.preferences.slice(0, 8).forEach((preference) => list.append(textElement("li", "", preference.instruction)));
    memory.append(list);
    stream.append(memory);
  }
  const form = $("#prism-onboarding-form");
  form.hidden = false;
  $("#prism-source-control").hidden = false;
  $("#prism-composer-hint").textContent = "Enter to send · Shift+Enter for a new line";
  updateSourceSummary();
  $("#prism-onboarding-choices").hidden = true;
  $("#prism-onboarding-custom-wrap").hidden = false;
  $("#prism-choice-hint").hidden = true;
  const input = $("#prism-onboarding-custom");
  input.placeholder = `Message ${prism.name}`;
  $("#prism-onboarding-back").hidden = true;
  $("#prism-onboarding-skip").hidden = true;
  setSendLabel("Ask Prism");
}
function teamsScopeCopy(policy) {
  if (!policy || policy === "loading") return "Loading the durable Teams monitoring boundary…";
  if (policy === "error") return "Teams monitoring scope could not be loaded.";
  const count = policy.rules?.length || 0;
  if (policy.mode === "include_only") return count ? `Only ${count} selected Teams ${count === 1 ? "chat is" : "chats are"} eligible to be read.` : "No Teams chats are eligible until you select one.";
  if (policy.mode === "all_except") return count ? `All accessible Teams chats except ${count} excluded ${count === 1 ? "chat" : "chats"} are eligible.` : "All accessible Teams chats are eligible; no exclusions are set.";
  return "All accessible Teams chats are eligible by default.";
}
// Teams monitoring status lives in a pinned bar under the chat header, so it
// never interrupts the conversation. Its actions live in the header menu.
function renderPinned(prism, active) {
  const pinned = $("#prism-pinned");
  pinned.hidden = !active;
  if (!active) return;
  const policy = state.sourcePolicy;
  const loaded = policy && typeof policy === "object";
  const summary = pinned.querySelector("summary");
  summary.replaceChildren(
    textElement("span", `pinned-dot${loaded && policy.last_discovery_error ? " warn" : ""}`),
    textElement("strong", "", "Teams monitoring"),
    textElement("span", "pinned-text", teamsScopeCopy(policy)),
  );
  const body = pinned.querySelector(".chat-pinned-body");
  body.replaceChildren();
  if (loaded && policy.last_discovery_at) body.append(textElement("p", "", `Last checked ${formatTime(policy.last_discovery_at)}.${policy.last_discovery_error ? ` ${policy.last_discovery_error}` : ""}`));
  else if (policy !== "loading" && policy !== "error") body.append(textElement("p", "", "No Teams activity has been checked yet. Use Refresh Teams activity in the menu for one bounded local read; nothing is sent."));
  if (state.activity && state.activity !== "loading" && state.activity.items?.length) {
    const events = textElement("ul", "prism-event-list");
    state.activity.items.slice(0, 3).forEach((event) => {
      const action = event.event_kind === "deleted" ? "deleted a message" : event.event_kind === "updated" ? "updated a message" : "posted";
      const text = event.body_text ? `: ${event.body_text.replace(/\s+/g, " ")}` : ".";
      events.append(textElement("li", "", `${event.sender_display_name} ${action} in ${event.source_label || "Teams chat"}${text}`));
    });
    body.append(events);
  }
  if (state.observations && state.observations !== "loading") {
    const open = (state.observations.items || []).filter((item) => item.state === "open").slice(0, 3);
    if (open.length) {
      const heading = textElement("p", "", `Proactive recommendations (${open.length})`);
      body.append(heading);
      const list = textElement("ul", "prism-event-list");
      open.forEach((item) => {
        list.append(textElement("li", "", `${item.urgency.toUpperCase()} · ${item.summary}: ${item.suggested_next_step}`));
      });
      body.append(list);
    }
  }
  const trigger = state.triggerPolicy;
  if (trigger && typeof trigger === "object") {
    const mode = { manual: "Manual only", scheduled: "Daily schedule", continuous: "Continuous checks", event_driven: "Coalesced event checks" }[trigger.mode] || trigger.mode;
    let schedule = `Monitoring mode: ${mode}.`;
    if (trigger.mode === "scheduled" && trigger.next_scheduled_for) schedule += ` Next run ${formatTime(trigger.next_scheduled_for)}.`;
    if (trigger.mode !== "manual" && !trigger.local_scheduler_enabled) schedule += " Local scheduler is off; run it manually until enabled.";
    body.append(textElement("p", "", schedule));
    const latest = state.runs?.items?.[0];
    if (latest) {
      const detail = latest.safe_error ? ` ${latest.safe_error}` : "";
      body.append(textElement("p", "", `Last monitoring run: ${latest.state}${latest.completed_at ? ` · ${formatTime(latest.completed_at)}` : ""}.${detail}`));
    }
  }
}
function setMenuOpen(open) {
  const menu = $("#prism-menu");
  if (!menu || menu.hidden === !open) return;
  menu.hidden = !open;
  $("#prism-menu-button").setAttribute("aria-expanded", String(open));
  if (open) menu.querySelector(".menu-item:not([hidden])")?.focus();
}
function updateSourceSummary() {
  const summary = $("#prism-source-summary");
  if (!summary) return;
  const sources = state.selectedSources;
  summary.textContent = sources.length ? `${sources.length} ${sources.length === 1 ? "chat" : "chats"}` : "Auto";
  const button = $("#prism-source-button");
  const label = sources.length
    ? `Reading only: ${sources.map((source) => source.label).join(", ")}. Click to change.`
    : "Auto: Prism picks the relevant Teams chats. Click to choose up to five.";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.classList.toggle("selected", sources.length > 0);
}
function sourceDetail(source) {
  const kind = { private: "1:1 chat", oneonone: "1:1 chat", group: "Group chat", meeting: "Meeting chat" }[String(source.chat_type || "").toLowerCase()] || "Teams chat";
  return [kind, ...(source.participants || [])].filter(Boolean).join(" · ");
}
function sourceDialogError(message = "") {
  const error = $("#prism-source-error");
  error.hidden = !message;
  error.textContent = message;
}
function policyAllowsSource(source) {
  const policy = state.sourcePolicy;
  if (!policy || typeof policy !== "object") return true;
  const ids = new Set((policy.rules || []).map((rule) => rule.external_id));
  if (policy.mode === "include_only") return ids.has(source.external_id);
  if (policy.mode === "all_except") return !ids.has(source.external_id);
  return true;
}
function renderSourceOptions(query = "") {
  const list = $("#prism-source-list");
  const needle = query.trim().toLowerCase();
  const sources = state.sourceCatalog.filter((source) => policyAllowsSource(source) && (!needle || `${source.label} ${(source.participants || []).join(" ")}`.toLowerCase().includes(needle)));
  list.replaceChildren();
  if (!sources.length) { list.className = "agent-source-list empty-state"; list.textContent = "No Teams chats are allowed by this Prism’s monitoring scope."; return; }
  list.className = "agent-source-list";
  const selected = new Set((state.pendingSources || state.selectedSources).map((source) => source.external_id));
  sources.forEach((source) => {
    const label = textElement("label", "source-option prism-source-option");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = selected.has(source.external_id);
    input.setAttribute("aria-label", source.label);
    const copy = textElement("span", "source-copy");
    copy.append(textElement("strong", "", source.label), textElement("span", "", sourceDetail(source)));
    input.addEventListener("change", () => {
      const current = new Map((state.pendingSources || []).map((item) => [item.external_id, item]));
      if (input.checked) {
        if (current.size >= 5) { input.checked = false; sourceDialogError("Select up to five Teams chats for one request."); return; }
        current.set(source.external_id, source);
      } else current.delete(source.external_id);
      state.pendingSources = [...current.values()];
      sourceDialogError("");
      updateSourceDone();
    });
    label.append(textElement("span", "avatar", initial(source.label)), copy, input);
    list.append(label);
  });
}
function updateSourceDone() {
  const count = (state.pendingSources || []).length;
  $("#prism-source-done").textContent = count ? `Use ${count} ${count === 1 ? "chat" : "chats"}` : "Done";
}
async function openSourceDialog() {
  const dialog = $("#prism-source-dialog");
  $("#prism-source-search").value = "";
  state.pendingSources = [...state.selectedSources];
  sourceDialogError("");
  updateSourceDone();
  dialog.showModal();
  $("#prism-source-search").focus();
  if (state.sourceCatalog.length) { renderSourceOptions(); return; }
  const list = $("#prism-source-list");
  list.className = "agent-source-list empty-state";
  list.textContent = "Loading Teams chats…";
  try {
    const result = await agentApi("/api/v2/agent/sources/teams");
    state.sourceCatalog = result.items || [];
    renderSourceOptions();
  } catch (error) {
    list.textContent = error.message;
  }
}
function closeSourceDialog() { state.pendingSources = null; $("#prism-source-dialog").close(); }
function clearSelectedSources() { state.selectedSources = []; state.pendingSources = null; updateSourceSummary(); $("#prism-source-dialog").close(); }
function useSelectedSources() { state.selectedSources = [...(state.pendingSources || [])]; updateSourceSummary(); closeSourceDialog(); }
function policyDialogError(message = "") {
  const error = $("#prism-policy-error");
  error.hidden = !message;
  error.textContent = message;
}
function renderPolicySources(query = "") {
  const wrap = $("#prism-policy-selection-wrap");
  const pending = state.pendingPolicy;
  const mode = pending?.mode || "all_chats";
  wrap.hidden = mode === "all_chats";
  document.querySelectorAll('input[name="prism-policy-mode"]').forEach((input) => { input.checked = input.value === mode; });
  if (mode === "all_chats") return;
  $("#prism-policy-selection-note").textContent = mode === "include_only" ? "Check each chat this Prism may monitor." : "Check each chat this Prism must never read.";
  const list = $("#prism-policy-source-list");
  const needle = query.trim().toLowerCase();
  const sources = state.sourceCatalog.filter((source) => !needle || `${source.label} ${(source.participants || []).join(" ")}`.toLowerCase().includes(needle));
  list.replaceChildren();
  if (!sources.length) { list.className = "agent-source-list empty-state"; list.textContent = "No matching Teams chats."; return; }
  list.className = "agent-source-list";
  const selected = new Set(pending.externalIds);
  sources.forEach((source) => {
    const label = textElement("label", "source-option prism-source-option");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = selected.has(source.external_id);
    input.setAttribute("aria-label", source.label);
    input.addEventListener("change", () => {
      const ids = new Set(state.pendingPolicy.externalIds);
      if (input.checked) ids.add(source.external_id); else ids.delete(source.external_id);
      state.pendingPolicy.externalIds = [...ids];
    });
    const copy = textElement("span", "source-copy");
    copy.append(textElement("strong", "", source.label), textElement("span", "", sourceDetail(source)));
    label.append(textElement("span", "avatar", initial(source.label)), copy, input);
    list.append(label);
  });
}
async function openPolicyDialog() {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  if (!prism) return;
  policyDialogError("");
  if (!state.sourcePolicy || state.sourcePolicy === "error") await loadTeamsMonitoring();
  const policy = state.sourcePolicy;
  if (!policy || typeof policy !== "object") { policyDialogError("Teams monitoring scope is unavailable. Try again."); return; }
  state.pendingPolicy = { mode: policy.mode, externalIds: (policy.rules || []).map((rule) => rule.external_id) };
  $("#prism-policy-search").value = "";
  $("#prism-policy-dialog").showModal();
  const list = $("#prism-policy-source-list");
  list.className = "agent-source-list empty-state";
  list.textContent = "Loading Teams chats…";
  try {
    const result = await agentApi("/api/v2/agent/sources/teams");
    state.sourceCatalog = result.items || [];
    renderPolicySources();
  } catch (error) { list.textContent = error.message; policyDialogError("Could not load accessible Teams chats."); }
}
function closePolicyDialog() { state.pendingPolicy = null; $("#prism-policy-dialog").close(); }
async function savePolicy() {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  const policy = state.sourcePolicy;
  if (!prism || !policy || typeof policy !== "object" || !state.pendingPolicy) return;
  const button = $("#prism-policy-save");
  button.disabled = true;
  policyDialogError("");
  try {
    state.sourcePolicy = await agentApi(`/api/v2/prisms/${prism.id}/teams-policy`, { method: "PUT", body: JSON.stringify({ expected_revision: policy.revision, mode: state.pendingPolicy.mode, external_ids: state.pendingPolicy.mode === "all_chats" ? [] : state.pendingPolicy.externalIds }) });
    closePolicyDialog();
    ui().setStatus?.("Teams monitoring scope saved. It applies before Prism reads chats.");
    renderWorkspace();
  } catch (error) { policyDialogError(error.message); await loadTeamsMonitoring(); }
  finally { button.disabled = false; }
}
async function loadTeamsMonitoring() {
  const prismId = state.selectedId;
  if (!prismId) return;
  state.sourcePolicy = "loading";
  try {
    const [policy, activity, observations] = await Promise.all([
      agentApi(`/api/v2/prisms/${prismId}/teams-policy`),
      agentApi(`/api/v2/prisms/${prismId}/teams-activity`),
      agentApi(`/api/v2/prisms/${prismId}/observations`),
    ]);
    if (state.selectedId === prismId) { state.sourcePolicy = policy; state.activity = activity; state.observations = observations; }
  } catch (error) {
    if (state.selectedId === prismId) { state.sourcePolicy = "error"; ui().setStatus?.(error.message, true); }
  }
  if (state.selectedId === prismId) {
    renderWorkspace();
    if (state.sourcePolicy === null) loadTeamsMonitoring();
  }
}
async function loadRunStatus() {
  const prismId = state.selectedId;
  if (!prismId) return;
  state.triggerPolicy = "loading";
  try {
    const [policy, runs] = await Promise.all([
      agentApi(`/api/v2/prisms/${prismId}/trigger-policy`),
      agentApi(`/api/v2/prisms/${prismId}/runs`),
    ]);
    if (state.selectedId === prismId) { state.triggerPolicy = policy; state.runs = runs; }
  } catch (error) {
    if (state.selectedId === prismId) { state.triggerPolicy = "error"; ui().setStatus?.(error.message, true); }
  }
  if (state.selectedId === prismId) renderWorkspace();
}
function triggerDialogError(message = "") {
  const error = $("#prism-trigger-error");
  error.hidden = !message;
  error.textContent = message;
}
function updateTriggerFields() {
  const mode = $("#prism-trigger-mode").value;
  $("#prism-trigger-schedule-fields").hidden = mode !== "scheduled";
  $("#prism-trigger-continuous-fields").hidden = mode !== "continuous";
  $("#prism-trigger-event-fields").hidden = mode !== "event_driven";
}
async function openTriggerDialog() {
  if (!state.triggerPolicy || state.triggerPolicy === "error") await loadRunStatus();
  const policy = state.triggerPolicy;
  if (!policy || typeof policy !== "object") { ui().setStatus?.("Monitoring schedule is unavailable. Try again.", true); return; }
  $("#prism-trigger-mode").value = policy.mode;
  $("#prism-trigger-enabled").checked = policy.enabled;
  $("#prism-trigger-timezone").value = policy.timezone;
  $("#prism-trigger-time").value = policy.daily_time;
  $("#prism-trigger-missed").value = policy.missed_run_policy;
  $("#prism-trigger-interval").value = policy.continuous_interval_seconds;
  $("#prism-trigger-coalesce").value = policy.event_coalesce_seconds;
  triggerDialogError("");
  updateTriggerFields();
  $("#prism-trigger-dialog").showModal();
}
function closeTriggerDialog() { $("#prism-trigger-dialog").close(); }
async function saveTriggerPolicy() {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  const policy = state.triggerPolicy;
  if (!prism || !policy || typeof policy !== "object") return;
  const button = $("#prism-trigger-save");
  button.disabled = true;
  triggerDialogError("");
  try {
    state.triggerPolicy = await agentApi(`/api/v2/prisms/${prism.id}/trigger-policy`, {
      method: "PUT",
      body: JSON.stringify({
        expected_revision: policy.revision,
        mode: $("#prism-trigger-mode").value,
        enabled: $("#prism-trigger-enabled").checked,
        timezone: $("#prism-trigger-timezone").value,
        daily_time: $("#prism-trigger-time").value,
        missed_run_policy: $("#prism-trigger-missed").value,
        continuous_interval_seconds: Number($("#prism-trigger-interval").value),
        event_coalesce_seconds: Number($("#prism-trigger-coalesce").value),
      }),
    });
    closeTriggerDialog();
    ui().setStatus?.("Monitoring schedule saved. It only reads Teams; it cannot send messages.");
    renderWorkspace();
  } catch (error) { triggerDialogError(error.message); }
  finally { button.disabled = false; }
}
async function syncTeamsActivity() {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  if (!prism) return;
  const button = $("#prism-sync-button");
  button.disabled = true;
  try {
    const run = await agentApi(`/api/v2/prisms/${prism.id}/runs/manual`, { method: "POST", body: "{}" });
    if (run.state === "queued" || run.state === "running") {
      ui().setStatus?.("Monitoring run started. Its status will appear in the pinned Teams monitoring panel.");
    } else {
      const result = run.result || {};
      const degraded = Boolean(run.safe_error || result.status === "degraded");
      ui().setStatus?.(degraded ? `Monitoring run is degraded: ${run.safe_error || "try again shortly"}` : `Checked ${result.scanned_chats || 0} Teams ${result.scanned_chats === 1 ? "chat" : "chats"}; found ${result.created_events || 0} new activity ${(result.created_events || 0) === 1 ? "event" : "events"}.`, degraded);
    }
    await Promise.all([loadTeamsMonitoring(), loadRunStatus()]);
  } catch (error) { ui().setStatus?.(error.message, true); await Promise.all([loadTeamsMonitoring(), loadRunStatus()]); }
  finally { button.disabled = false; }
}
function choiceLabel(question, value) { return question.choices.find((choice) => choice.value === value)?.label || value; }
const acknowledgements = ["Got it, thanks.", "Great, that helps.", "Noted.", "Perfect, thank you.", "Makes sense."];
function answerText(question, answer) {
  return answer.skipped ? "Skip for now" : answer.custom_text || answer.selected_values.map((value) => choiceLabel(question, value)).join(", ");
}
function renderOnboardingConversation(stream, session) {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  const name = prism?.name || "Prism";
  const answers = new Map(session.answers.map((answer) => [answer.question_id, answer]));
  const activeId = state.editingQuestionId || session.current_question_id;
  const total = session.questions.length;
  const activeQuestion = session.status === "completed" ? null : session.questions.find((question) => question.id === activeId);
  const intro = `Hi, I’m ${name}. I’ll ask you a few quick questions so I can help the way you like. Answer in your own words, or pick an option. You can skip anything optional.`;
  let lead = intro;
  session.questions.forEach((question) => {
    const answer = answers.get(question.id);
    if (!answer || question.id === activeId) return;
    stream.append(bubble(name, `${lead}\n\n${question.prompt}`));
    stream.append(bubble("You", answerText(question, answer), "user"));
    lead = acknowledgements[session.questions.indexOf(question) % acknowledgements.length];
  });
  if (!activeQuestion) {
    renderAgreement(stream, lead);
    return;
  }
  const position = session.questions.indexOf(activeQuestion) + 1;
  stream.append(bubble(name, `${lead}\n\n${activeQuestion.prompt}`, "assistant", null, `Question ${position} of ${total}`));
  if (state.answering) {
    stream.append(bubble("You", state.answering.text, "user"));
    stream.append(typingIndicator(name, `${name} is reading your answer…`));
    return;
  }
  renderQuestionForm(activeQuestion, answers.get(activeQuestion.id), session);
  const choices = $("#prism-onboarding-choices");
  if (!choices.hidden) stream.lastElementChild.querySelector(".turn-body").append(choices);
}
function agreementList(value) {
  const list = document.createElement("ul");
  (Array.isArray(value) ? value : [value]).filter(Boolean).forEach((item) => list.append(textElement("li", "", item)));
  return list;
}
function renderAgreement(stream, lead = "") {
  if (state.agreement === "loading" || !state.agreement) {
    stream.append(bubble("Prism", `${lead}\n\nThat’s everything I need. Give me a moment while I write up how we’ll work together.`));
    return;
  }
  if (state.agreement === "error") {
    stream.append(textElement("div", "empty-state inline-error", "The working agreement could not be loaded. Refresh this Prism and try again."));
    return;
  }
  const agreement = state.agreement;
  const content = agreement.agreement;
  stream.append(bubble("Prism", agreement.status === "confirmed" ? "Your working agreement is confirmed." : `${lead}\n\nAll set. Here’s how I understood our working relationship. Have a look, and activate me when it feels right.`));
  const card = textElement("section", "chat-card working-agreement");
  card.append(textElement("h3", "", "Working agreement"));
  const sections = [
    ["Mission", content.mission],
    ["Bring to your attention", content.attention_signals],
    ["Regular brief", content.regular_brief],
    ["Teams scope", content.teams_scope],
    ["Tone", content.tone],
    ["May prepare for approval", content.allowed_proposals],
    ["Restrictions", content.restrictions],
  ];
  sections.forEach(([label, value]) => {
    const row = textElement("div", "agreement-row");
    row.append(textElement("strong", "", label));
    row.append(Array.isArray(value) ? agreementList(value) : textElement("p", "", value));
    card.append(row);
  });
  const safety = textElement("p", "agreement-safety", content.safety_rule);
  card.append(safety, textElement("p", "panel-note", content.current_limitations));
  if (agreement.status === "draft") {
    const confirm = textElement("button", "button", "Confirm and activate");
    confirm.type = "button";
    confirm.addEventListener("click", confirmAgreement);
    card.append(confirm);
  }
  stream.append(card);
}
function renderQuestionForm(question, existing, session) {
  const form = $("#prism-onboarding-form");
  const choices = $("#prism-onboarding-choices");
  const custom = $("#prism-onboarding-custom");
  const customWrap = $("#prism-onboarding-custom-wrap");
  choices.replaceChildren();
  $("#prism-source-control").hidden = true;
  $("#prism-composer-hint").textContent = "Enter to send · Shift+Enter for a new line";
  choices.hidden = !question.choices.length;
  custom.value = existing?.custom_text || "";
  requestAnimationFrame(() => autoGrow(custom));
  customWrap.hidden = !question.allows_custom && question.question_type !== "long_text" && question.question_type !== "short_text";
  if (!question.choices.length) customWrap.hidden = false;
  $("#prism-choice-hint").hidden = !customWrap.hidden;
  custom.placeholder = question.choices.length ? "Or answer in your own words…" : "Type your answer…";
  question.choices.forEach((choice) => {
    const label = textElement("label", "onboarding-choice");
    const input = document.createElement("input");
    input.type = question.question_type === "multiple_choice" ? "checkbox" : "radio";
    input.name = "prism-onboarding-choice";
    input.value = choice.value;
    input.checked = Boolean(existing?.selected_values.includes(choice.value));
    label.append(input, textElement("span", "", choice.label));
    choices.append(label);
  });
  const index = session.questions.findIndex((item) => item.id === question.id);
  const back = $("#prism-onboarding-back");
  back.hidden = index <= 0;
  back.onclick = () => { state.editingQuestionId = session.questions[index - 1].id; renderWorkspace(); };
  const skip = $("#prism-onboarding-skip");
  skip.hidden = question.required;
  skip.onclick = () => submitAnswer(question, session, true);
  setSendLabel(state.editingQuestionId ? "Save answer" : "Continue");
  $("#prism-onboarding-error").hidden = true;
  form.hidden = false;
}
async function loadOnboarding() {
  if (!state.selectedId) return;
  state.onboarding = "loading";
  renderWorkspace();
  try {
    state.onboarding = await agentApi(`/api/v2/prisms/${state.selectedId}/onboarding`);
    if (state.onboarding.status === "completed") loadAgreement();
    if (state.prisms.find((item) => item.id === state.selectedId)?.state === "active") loadConversation();
  }
  catch (error) { state.onboarding = error.status === 404 ? "missing" : "error"; if (state.onboarding === "error") ui().setStatus?.(error.message, true); }
  renderWorkspace();
}
async function loadConversation() {
  if (!state.selectedId) return;
  const prismId = state.selectedId;
  // Keep the visible conversation while refreshing; only the first load shows a placeholder.
  if (!state.conversation || state.conversation === "error") {
    state.conversation = "loading";
    renderWorkspace();
  }
  try {
    const result = await agentApi(`/api/v2/prisms/${prismId}/conversation`);
    if (state.selectedId === prismId) state.conversation = result;
  } catch (error) {
    if (state.selectedId === prismId) {
      state.conversation = "error";
      ui().setStatus?.(error.message, true);
    }
  }
  if (state.selectedId === prismId) {
    renderWorkspace();
    if (state.sourcePolicy === null) loadTeamsMonitoring();
    if (state.triggerPolicy === null) loadRunStatus();
  }
}
async function sendConversationMessage() {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  const input = $("#prism-onboarding-custom");
  const content = input.value.trim();
  if (!prism || !content) return;
  const button = $("#prism-onboarding-next");
  button.disabled = true;
  try {
    const remembered = content.match(/^remember\s*:\s*(.+)$/i);
    if (remembered) {
      await agentApi(`/api/v2/prisms/${prism.id}/memory`, { method: "POST", body: JSON.stringify({ instruction: remembered[1] }) });
      input.value = "";
      autoGrow(input);
      ui().setStatus?.(`Saved to ${prism.name}’s private memory.`);
      await loadConversation();
      return;
    }
    const selectedExternalIds = state.selectedSources.map((source) => source.external_id);
    state.pending = { prismId: prism.id, content, stage: "Sending your message…" };
    input.value = "";
    autoGrow(input);
    setPending("Sending your message…");
    const job = await agentApi(`/api/v2/prisms/${prism.id}/conversation/messages`, { method: "POST", body: JSON.stringify({ content, source_external_ids: selectedExternalIds }) });
    state.selectedSources = [];
    updateSourceSummary();
    setPending(selectedExternalIds.length ? "Searching the selected Teams chats…" : "Searching your Teams chats for relevant messages…");
    await agentApi(`/api/v2/agent/jobs/${job.id}/evidence/sync`, { method: "POST" });
    setPending("Reading what it found and preparing a response…");
    await agentApi(`/api/v2/agent/jobs/${job.id}/review`, { method: "POST" });
    state.pending = null;
    await loadConversation();
  } catch (error) {
    ui().setStatus?.(error.message, true);
    if (state.pending && !input.value) input.value = state.pending.content;
    state.pending = null;
    await loadConversation();
  } finally { button.disabled = false; }
}
async function loadAgreement() {
  if (!state.selectedId) return;
  const prismId = state.selectedId;
  state.agreement = "loading";
  renderWorkspace();
  try {
    const agreement = await agentApi(`/api/v2/prisms/${prismId}/agreement`);
    if (state.selectedId === prismId) state.agreement = agreement;
  } catch (error) {
    if (state.selectedId === prismId) {
      state.agreement = "error";
      ui().setStatus?.(error.message, true);
    }
  }
  if (state.selectedId === prismId) renderWorkspace();
}
async function confirmAgreement() {
  const prism = state.prisms.find((item) => item.id === state.selectedId);
  if (!prism || !state.agreement || typeof state.agreement !== "object") return;
  try {
    const result = await agentApi(`/api/v2/prisms/${prism.id}/agreement/confirm`, {
      method: "POST",
      body: JSON.stringify({ expected_agreement_revision: state.agreement.revision, expected_lifecycle_version: prism.lifecycle_version }),
    });
    state.agreement = result.agreement;
    state.prisms = state.prisms.map((item) => item.id === result.prism.id ? result.prism : item);
    ui().setStatus?.(`${result.prism.name} is active. Set its Teams monitoring scope when you are ready.`);
    render();
    await loadConversation();
  } catch (error) {
    ui().setStatus?.(error.message, true);
    await loadPrisms();
    await loadAgreement();
  }
}
async function startOnboarding() {
  try {
    state.onboarding = "loading";
    renderWorkspace();
    state.onboarding = await agentApi(`/api/v2/prisms/${state.selectedId}/onboarding/start`, { method: "POST", body: "{}" });
    ui().setStatus?.("Onboarding started. Your answers are saved after every step.");
    // The selected Prism is already in the sidebar. Rendering directly avoids
    // a second list fetch resetting the first free-text answer while the
    // manager begins typing it.
    renderWorkspace();
  } catch (error) { state.onboarding = "error"; renderWorkspace(); ui().setStatus?.(error.message, true); }
}
async function submitAnswer(question, session, skipped = false) {
  const selectedValues = [...document.querySelectorAll('input[name="prism-onboarding-choice"]:checked')].map((input) => input.value);
  const customText = $("#prism-onboarding-custom").value;
  const error = $("#prism-onboarding-error");
  const next = $("#prism-onboarding-next");
  next.disabled = true;
  error.hidden = true;
  const text = skipped ? "Skip for now" : customText.trim() || selectedValues.map((value) => choiceLabel(question, value)).join(", ") || "Skip for now";
  state.answering = { text };
  state.forceScroll = true;
  renderWorkspace();
  const beat = new Promise((resolve) => setTimeout(resolve, 700));
  try {
    state.onboarding = await agentApi(`/api/v2/prisms/${state.selectedId}/onboarding/questions/${question.id}/answer`, { method: "POST", body: JSON.stringify({ expected_revision: session.revision, selected_values: skipped ? [] : selectedValues, custom_text: skipped ? null : customText, skipped }) });
    state.editingQuestionId = null;
    await beat;
    state.answering = null;
    if (state.onboarding.status === "completed") loadAgreement();
    await loadPrisms();
  } catch (requestError) { state.answering = null; renderWorkspace(); error.textContent = requestError.message; error.hidden = false; }
  finally { state.answering = null; next.disabled = false; }
}
async function loadPrisms() {
  if (!state.enabled) return;
  state.loading = true;
  render();
  let shouldLoadSelected = false;
  try {
    state.prisms = await agentApi(`/api/v2/prisms?include_archived=${state.includeArchived}`);
    // This local workspace intentionally has one Executive Assistant. Open it
    // immediately on a new browser/profile so its preserved history is never
    // hidden behind an empty-state screen.
    if (!state.selectedId && state.prisms.length === 1) {
      state.selectedId = state.prisms[0].id;
      localStorage.setItem(selectedKey, state.selectedId);
    }
    // A refresh restores the selected Prism id from localStorage.  Load its
    // conversation as well as its sidebar item; otherwise its history stays
    // blank until the manager happens to click it again.
    shouldLoadSelected = Boolean(
      state.selectedId
      && state.prisms.some((prism) => prism.id === state.selectedId)
      && state.onboarding === null
    );
  }
  catch (error) { state.prisms = []; ui().setStatus?.(error.message, true); }
  finally { state.loading = false; render(); }
  if (shouldLoadSelected) loadOnboarding();
  else if (!state.selectedId) document.dispatchEvent(new CustomEvent("prism:no-prism-selected"));
}
function resetEditor() {
  $("#prism-editor-id").value = ""; $("#prism-editor-version").value = "";
  $("#prism-editor-title").textContent = "Create a Prism";
  $("#prism-editor-note").textContent = "Start with a role, then answer tailored onboarding questions.";
  $("#prism-editor-name").value = ""; $("#prism-editor-description").value = "";
  $("#prism-editor-name").disabled = false; $("#prism-editor-description").disabled = false;
  $("#prism-editor-submit").textContent = "Create draft"; $("#prism-editor-submit").disabled = false; showEditorError("");
}
function showEditorError(message) { const element = $("#prism-editor-error"); element.hidden = !message; element.textContent = message; }
function openCreate() { resetEditor(); $("#prism-editor-dialog").showModal(); $("#prism-editor-name").focus(); }
function openEditor(prism) {
  resetEditor(); $("#prism-editor-id").value = prism.id; $("#prism-editor-version").value = String(prism.lifecycle_version);
  $("#prism-editor-title").textContent = isArchived(prism) ? "Archived Prism" : "Edit Prism";
  $("#prism-editor-note").textContent = isArchived(prism) ? "Archived Prisms are read-only. You can still review their original role." : "Update this Prism’s role before working-agreement review is added in Phase 4.";
  $("#prism-editor-name").value = prism.name; $("#prism-editor-description").value = prism.description;
  $("#prism-editor-submit").textContent = isArchived(prism) ? "Close" : "Save changes";
  $("#prism-editor-name").disabled = isArchived(prism); $("#prism-editor-description").disabled = isArchived(prism); $("#prism-editor-submit").disabled = isArchived(prism);
  $("#prism-editor-dialog").showModal();
  if (!isArchived(prism)) $("#prism-editor-name").focus();
}
function closeEditor() { $("#prism-editor-dialog").close(); }
async function submitEditor(event) {
  event.preventDefault();
  const id = $("#prism-editor-id").value;
  const submit = $("#prism-editor-submit");
  const payload = { name: $("#prism-editor-name").value, description: $("#prism-editor-description").value };
  if (!payload.name.trim() || !payload.description.trim()) { showEditorError("Give this Prism both a name and a short responsibility."); return; }
  if (id) payload.expected_lifecycle_version = Number($("#prism-editor-version").value);
  showEditorError(""); submit.disabled = true;
  try {
    const prism = await agentApi(id ? `/api/v2/prisms/${id}` : "/api/v2/prisms", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
    closeEditor(); if (!id) { selectPrism(prism.id); ui().setActiveTab?.("prisms"); } ui().setStatus?.(id ? `${prism.name} updated.` : `${prism.name} was created as a draft.`); await loadPrisms();
  } catch (error) { showEditorError(error.message); } finally { submit.disabled = false; }
}
async function archivePrism(prism) {
  const confirmed = await ui().askDialog?.({ title: `Archive ${prism.name}?`, message: "It will be hidden from the default directory. Its audit history remains intact.", confirmLabel: "Archive Prism", danger: true });
  if (!confirmed) return;
  try {
    await agentApi(`/api/v2/prisms/${prism.id}/archive`, { method: "POST", body: JSON.stringify({ expected_lifecycle_version: prism.lifecycle_version }) });
    if (state.selectedId === prism.id) { state.selectedId = null; state.onboarding = null; state.agreement = null; localStorage.removeItem(selectedKey); }
    ui().setStatus?.(`${prism.name} archived.`); await loadPrisms();
  } catch (error) { ui().setStatus?.(error.message, true); await loadPrisms(); }
}
function initialize() {
  $("#prism-create-button").addEventListener("click", openCreate);
  $("#prism-edit-button").addEventListener("click", () => { const prism = state.prisms.find((item) => item.id === state.selectedId); if (prism) openEditor(prism); });
  $("#prism-archive-button").addEventListener("click", () => { const prism = state.prisms.find((item) => item.id === state.selectedId); if (prism) archivePrism(prism); }); $("#prism-editor-close").addEventListener("click", closeEditor); $("#prism-editor-cancel").addEventListener("click", closeEditor); $("#prism-editor-form").addEventListener("submit", submitEditor);
  $("#prism-onboarding-form").addEventListener("submit", (event) => { event.preventDefault(); const prism = state.prisms.find((item) => item.id === state.selectedId); if (prism?.state === "active") { sendConversationMessage(); return; } const question = state.onboarding?.questions.find((item) => item.id === (state.editingQuestionId || state.onboarding.current_question_id)); if (question) submitAnswer(question, state.onboarding); });
  $("#prism-source-button").addEventListener("click", openSourceDialog);
  $("#prism-source-search").addEventListener("input", (event) => renderSourceOptions(event.target.value));
  $("#prism-source-clear").addEventListener("click", clearSelectedSources);
  $("#prism-source-cancel").addEventListener("click", closeSourceDialog);
  $("#prism-source-done").addEventListener("click", useSelectedSources);
  $("#prism-policy-button").addEventListener("click", openPolicyDialog);
  $("#prism-trigger-button").addEventListener("click", openTriggerDialog);
  $("#prism-sync-button").addEventListener("click", syncTeamsActivity);
  document.querySelectorAll('input[name="prism-policy-mode"]').forEach((input) => input.addEventListener("change", (event) => {
    if (!state.pendingPolicy) return;
    state.pendingPolicy.mode = event.target.value;
    policyDialogError("");
    renderPolicySources($("#prism-policy-search").value);
  }));
  $("#prism-policy-search").addEventListener("input", (event) => renderPolicySources(event.target.value));
  $("#prism-policy-cancel").addEventListener("click", closePolicyDialog);
  $("#prism-policy-save").addEventListener("click", savePolicy);
  $("#prism-trigger-mode").addEventListener("change", updateTriggerFields);
  $("#prism-trigger-cancel").addEventListener("click", closeTriggerDialog);
  $("#prism-trigger-save").addEventListener("click", saveTriggerPolicy);
  $("#prism-archived-button").addEventListener("click", (event) => {
    state.includeArchived = !state.includeArchived;
    const button = event.currentTarget;
    button.setAttribute("aria-pressed", String(state.includeArchived));
    button.dataset.tooltip = state.includeArchived ? "Hide archived" : "Show archived";
    loadPrisms();
  });
  const composer = $("#prism-onboarding-custom");
  composer.addEventListener("input", () => autoGrow(composer));
  composer.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    if (!$("#prism-onboarding-next").disabled) $("#prism-onboarding-form").requestSubmit();
  });
  $("#prism-menu-button").addEventListener("click", (event) => { event.stopPropagation(); setMenuOpen($("#prism-menu").hidden); });
  $("#prism-menu").addEventListener("click", (event) => { if (event.target.closest(".menu-item")) setMenuOpen(false); });
  document.addEventListener("click", (event) => { if (!event.target.closest("#prism-menu")) setMenuOpen(false); });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || $("#prism-menu").hidden) return;
    setMenuOpen(false);
    $("#prism-menu-button").focus();
  });
  document.addEventListener("prism:open", (event) => {
    const prism = state.prisms.find((item) => item.id === event.detail.id);
    if (!prism) return;
    openPrismView(prism);
  });
  document.addEventListener("prism:updates", (event) => { state.updates = event.detail.summaries; render(); });
  document.addEventListener("prism:v22-mode", (event) => { state.enabled = event.detail.enabled; if (state.enabled) loadPrisms(); });
  if (ui().isV22Enabled?.() === true) { state.enabled = true; loadPrisms(); }
}
initialize();
