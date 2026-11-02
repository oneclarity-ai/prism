import { agentApi } from "./api.js";
import { colorPicker, prismColorKey, prismLogo } from "./prism-logo.js";
import { computersEnabled, initQa, onPrism as onQaPrism, planRequest, renderQaMessage, setOpen as setComputerOpen } from "./qa-tester.js";

const $ = (selector) => document.querySelector(selector);
const ui = () => window.prism || {};
const ACTIVE_JOB_STATES = ["queued", "researching", "planning"];
const PROGRESS_LABELS = {
  queued: "Resolving the Teams source…",
  researching: "Reading the Teams conversation…",
  planning: "Working out what needs your attention…",
  waiting_for_approval: "Waiting for your approval",
  executing: "Sending your approved message…",
  completed: "Done",
  failed: "Prism could not finish this review",
  cancelled: "Review cancelled",
};
const SUGGESTIONS = [
  "What needs my attention?",
  "Summarize decisions and open questions",
  "Draft a reply to the latest message",
  "What did I commit to?",
];
const CHAT_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4V5Z"/></svg>';
const EDIT_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4ZM13.5 6.5l4 4"/></svg>';
const TONES = ["gray", "blue", "green", "orange", "purple", "yellow", "red"];

const agentState = {
  threads: [],
  activeThread: null,
  messages: [],
  jobs: [],
  turns: new Map(), // job id -> { job, review, evidence: Map, error }
  updates: [], // stored proactive observations for the open Prism, shown as conversation updates
  currentJob: null,
  sources: [],
  preferences: [],
  drafts: new Map(), // proposal id -> unsaved text
  showAllThreads: false,
  loading: false,
  openToken: 0,
  prism: null, // the Prism whose private thread this page shows; null = legacy single conversation
  pendingSubmission: null,
  hasEarlier: false,
  anchor: null, // set while viewing history up to a searched message
  search: { open: false, query: "", results: null, token: 0 },
};
const PAGE_SIZE = 60;
const messagesUrl = (threadId, params = {}) => {
  const query = new URLSearchParams({ limit: PAGE_SIZE, ...params });
  return `/api/v2/agent/threads/${threadId}/messages?${query}`;
};

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function actionButton(label, className, onClick) {
  const button = textElement("button", className, label);
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
}

function humanize(value) {
  return String(value || "").replaceAll("_", " ");
}

function toneFor(text) {
  let hash = 0;
  for (const character of String(text || "")) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return TONES[hash % TONES.length];
}

function avatarFor(text) {
  const initial = String(text || "?").trim().charAt(0).toUpperCase() || "?";
  return textElement("span", `avatar ${toneFor(text)}`, initial);
}

function autoGrow(textarea, max = Infinity) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight + 2, max)}px`;
}

const notifyChanged = () => document.dispatchEvent(new CustomEvent("prism:agent-changed"));
const threadLabel = () => "Prism";
const reconnectMicrosoft = () => window.location.assign("/api/v1/microsoft/auth/start");

// Stable domain codes map to one clear next step; none of these claim a message was sent.
const RECOVERY = {
  microsoft_reconnect_required: {
    title: "Reconnect Microsoft to continue",
    detail: "Prism could not use your Microsoft session. Nothing was sent.",
    action: ["Reconnect Microsoft", reconnectMicrosoft],
  },
  microsoft_permission_required: {
    title: "Microsoft permission is missing",
    detail: "Your account cannot read or write this Teams chat with Prism's current consent. Nothing was sent. Ask an admin to grant Teams chat access, then reconnect.",
    action: ["Reconnect Microsoft", reconnectMicrosoft],
  },
  microsoft_throttled: {
    title: "Microsoft is asking Prism to slow down",
    detail: "Nothing was sent. Wait a minute, then retry.",
    action: null,
  },
  no_source_evidence: {
    title: "Nothing to read in this chat yet",
    detail: "Prism found no messages in the reading window, so it has nothing to ground a review on. Nothing was sent. Ask Prism to draft a message from your instruction, or ask again once the chat has messages.",
    action: null,
  },
  reconciliation_required: {
    title: "Delivery needs your confirmation",
    detail: "Prism could not prove whether Microsoft accepted this message, so it will not retry on its own. Check Teams before drafting again.",
    action: null,
  },
};

function renderFailure({ code, message }) {
  const recovery = RECOVERY[code];
  if (!recovery) return textElement("p", "inline-error", message);
  const notice = textElement("div", "callout recovery");
  notice.setAttribute("role", "alert");
  const body = textElement("div", "callout-body");
  body.append(textElement("strong", "", recovery.title), textElement("p", "", recovery.detail));
  if (recovery.action) body.append(actionButton(recovery.action[0], "mini-button", recovery.action[1]));
  notice.append(textElement("span", "callout-icon", "!"), body);
  return notice;
}

/* Threads: the sidebar list, the Today list, and the header. ------------- */

// The legacy page shows one global conversation; inside a Prism it shows that
// Prism's own canonical thread. Everything after loading is thread-id based, and
// the server applies the Prism's Teams policy to its thread.
async function fetchConversation() {
  if (!agentState.prism) return agentApi("/api/v2/agent/conversation");
  return (await agentApi(`/api/v2/prisms/${agentState.prism.id}/conversation`)).thread;
}

async function openPrism(prism) {
  if (agentState.prism?.id === prism.id && (agentState.activeThread || agentState.loading)) {
    agentState.prism = prism;
    renderHeader();
    return;
  }
  Object.assign(agentState, { prism, threads: [], activeThread: null, messages: [], jobs: [], turns: new Map(), currentJob: null, updates: [], loading: true });
  renderHeader();
  renderStream();
  try {
    const thread = await fetchConversation();
    if (agentState.prism?.id !== prism.id) return;
    agentState.threads = [thread];
    await openThread(thread.id);
    loadUpdates();
  } catch (error) {
    agentState.loading = false;
    ui().setStatus?.(error.message, true);
    renderStream();
  }
}

/* Proactive updates: durable observations rendered as first-class turns in this Prism's conversation. */

const SIGNAL_LABELS = { production_incident: "Possible production incident", missed_deadline: "Deadline at risk", blocker: "Blocked work", unanswered_message: "Unanswered message", customer_discussion: "Customer discussion" };
const URGENCY_TONES = { critical: "red", high: "orange", medium: "yellow", low: "blue" };

async function loadUpdates() {
  const prism = agentState.prism;
  if (!prism) return;
  try {
    const page = await agentApi(`/api/v2/prisms/${prism.id}/observations`);
    if (agentState.prism?.id !== prism.id) return;
    const changed = JSON.stringify(page.items) !== JSON.stringify(agentState.updates);
    agentState.updates = page.items;
    if (changed) renderStream();
    markUpdatesRead(prism.id, page.items);
  } catch (error) {
    // Updates are additive; a failed fetch must never block the conversation itself.
  }
}

function markUpdatesRead(prismId, items) {
  // Only a visible conversation counts as reading; the "New" tag stays until the next render.
  if ($("#app").dataset.view !== "agent" || document.visibilityState !== "visible") return;
  const unread = items.filter((item) => !item.read_at).map((item) => item.id);
  if (!unread.length) return;
  agentApi(`/api/v2/prisms/${prismId}/observations/read`, { method: "POST", body: JSON.stringify({ observation_ids: unread }) })
    .then(() => document.dispatchEvent(new CustomEvent("prism:updates-refresh")))
    .catch(() => {});
}

function renderUpdate(item) {
  const { article, body } = assistantShell(`proactive-update ${item.state}`);
  article.dataset.observation = item.id;
  const lead = textElement("p", "review-summary");
  if (["critical", "high"].includes(item.urgency) && item.state === "open") {
    const dot = textElement("span", `urgency-dot ${URGENCY_TONES[item.urgency]}`);
    dot.title = `${item.urgency[0].toUpperCase()}${item.urgency.slice(1)} urgency`;
    lead.append(dot);
  }
  lead.append(item.state === "open" ? `${item.summary}.` : `${item.summary}. ${item.state === "resolved" ? "This looks resolved now." : "There is a newer update on this."}`);
  body.append(msgBubble(lead));
  if (item.verified_facts.length) {
    const quote = textElement("div", "say say-quote");
    item.verified_facts.forEach((fact) => quote.append(textElement("p", "", fact)));
    quote.title = "Show the full message";
    quote.addEventListener("click", () => quote.classList.toggle("expanded"));
    body.append(quote);
  }
  if (item.state === "open" && item.suggested_next_step) body.append(msgBubble(textElement("p", "", item.suggested_next_step)));

  const quiet = textElement("div", "turn-quiet");
  const { details, content } = turnDetails([item.source_label, SIGNAL_LABELS[item.signal_type]].filter(Boolean).join(" · ") || "Details", `update:${item.id}`);
  content.append(
    textElement("p", "turn-meta", `${SIGNAL_LABELS[item.signal_type] || "Update"} · ${item.urgency[0].toUpperCase()}${item.urgency.slice(1)} urgency · ${confidenceText(item.confidence)}`),
    textElement("p", "update-why", `Why it matters: ${item.why_it_matters}`),
  );
  if (item.inference) content.append(textElement("p", "update-inference", `Inference, not a verified fact: ${item.inference}`));
  if (item.unknowns.length) {
    const limits = textElement("details", "limitations");
    limits.append(textElement("summary", "", "What Prism could not verify"));
    const list = document.createElement("ul");
    item.unknowns.forEach((unknown) => list.append(textElement("li", "", unknown)));
    limits.append(list);
    content.append(limits);
  }
  content.append(renderIncidentHistory(item), renderFeedback(item));
  quiet.append(details);
  if (item.state === "open") quiet.append(actionButton("Prepare a Teams draft", "link-button", () => draftFromUpdate(item)));
  body.append(quiet);
  return article;
}

// Explicit drafting intent: Prism prepares the message for the chat where this was seen. The user still approves.
async function draftFromUpdate(item) {
  const destination = item.source_label || "this Teams chat";
  const instruction = await ui().askDialog?.({
    title: "Prepare a Teams draft",
    message: `Prism will prepare a draft to ${destination}, the chat where this was seen. Nothing is sent until you approve it.`,
    confirmLabel: "Create draft",
    field: { label: "What should the message cover?", value: "Ask for the current status, who owns it, and the expected resolution time.", placeholder: "Tell Prism what the message should cover" },
  });
  if (!instruction?.trim() || !agentState.activeThread) return;
  showPendingSubmission(`Draft a follow-up to ${destination}`);
  try {
    updatePendingSubmission("Reading the chat and preparing a draft…");
    await createAndRunMessage("", null, {
      path: `/api/v2/prisms/${item.prism_id}/observations/${item.id}/drafts`,
      body: { request_id: crypto.randomUUID(), instruction: instruction.trim() },
    });
  } catch (error) {
    clearPendingSubmission();
    renderStream({ scroll: "bottom" });
    ui().setStatus?.(error.message, true);
  }
}

const FEEDBACK_LABELS = { helpful: "Helpful", not_helpful: "Not helpful", wrong_urgency: "Wrong urgency", wrong_evidence: "Wrong evidence", duplicate: "Duplicate", no_longer_relevant: "No longer relevant" };

// Feedback is saved for this Prism only. It never changes behavior until you confirm it in Status & tuning.
const FEEDBACK_REASONS = ["wrong_urgency", "wrong_evidence", "duplicate", "no_longer_relevant"];

function renderFeedback(item) {
  const row = textElement("div", "update-feedback");
  const selected = new Set(item.feedback_kinds || []);
  const reasons = textElement("div", "feedback-reasons");
  reasons.id = `feedback-reasons-${item.id}`;
  reasons.setAttribute("role", "group");
  reasons.setAttribute("aria-label", "What was wrong");
  const toggle = actionButton("What was off?", "mini-button ghost feedback-more", () => setReasons(reasons.hidden));
  toggle.setAttribute("aria-controls", reasons.id);
  const setReasons = (open) => {
    reasons.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  };
  const save = async (kind) => {
    try {
      const result = await agentApi(`/api/v2/prisms/${item.prism_id}/observations/${item.id}/feedback`, { method: "POST", body: JSON.stringify({ kind }) });
      item.feedback_kinds = result.feedback_kinds;
      row.querySelectorAll("button.feedback").forEach((node) => {
        const on = result.feedback_kinds.includes(node.dataset.kind);
        node.classList.toggle("selected", on);
        node.setAttribute("aria-pressed", String(on));
      });
      ui().setStatus?.("Thanks. Noted for this Prism only.");
    } catch (error) { ui().setStatus?.(error.message, true); }
  };
  const choice = (kind) => {
    const button = actionButton(FEEDBACK_LABELS[kind], `mini-button feedback${selected.has(kind) ? " selected" : ""}`, () => save(kind));
    button.dataset.kind = kind;
    button.setAttribute("aria-pressed", String(selected.has(kind)));
    return button;
  };
  const main = textElement("div", "feedback-main");
  main.append(textElement("span", "turn-meta", "Was this useful?"), choice("helpful"), choice("not_helpful"), toggle);
  FEEDBACK_REASONS.forEach((kind) => reasons.append(choice(kind)));
  setReasons(FEEDBACK_REASONS.some((kind) => selected.has(kind)));
  row.append(main, reasons);
  return row;
}

const INCIDENT_LABELS = { opened: "Opened", linked: "Linked", updated: "Updated", resolved: "Resolved", reopened: "Reopened", split: "Split" };

function renderIncidentHistory(item) {
  const details = textElement("details", "incident-history");
  details.append(textElement("summary", "", "Why this is grouped"));
  const content = textElement("div", "incident-body");
  details.append(content);
  let loaded = false;
  const load = async () => {
    try {
      const history = await agentApi(`/api/v2/prisms/${item.prism_id}/observations/${item.id}/incident`);
      content.replaceChildren();
      if (history.other_prisms) content.append(textElement("p", "turn-meta", `The same event was also seen by ${history.other_prisms} other Prism${history.other_prisms === 1 ? "" : "s"}. You were alerted once.`));
      const list = document.createElement("ul");
      history.events.forEach((event) => list.append(textElement("li", "", `${INCIDENT_LABELS[event.event_type]} · ${formatTime(event.created_at)} · ${event.reason}`)));
      content.append(list);
      if (history.events.some((event) => event.mine && ["linked", "updated", "reopened"].includes(event.event_type))) {
        content.append(actionButton("This is a different incident", "mini-button", async () => {
          try {
            await agentApi(`/api/v2/prisms/${item.prism_id}/observations/${item.id}/incident/split`, { method: "POST" });
            loaded = false;
            await load();
            ui().setStatus?.("Split into its own incident. Nothing was deleted.");
          } catch (error) { ui().setStatus?.(error.message, true); }
        }));
      }
    } catch (error) { content.replaceChildren(textElement("p", "turn-meta", "Incident history is unavailable right now.")); }
  };
  details.addEventListener("toggle", () => { if (details.open && !loaded) { loaded = true; load(); } });
  return details;
}

async function loadThreads() {
  if (agentState.prism) return;
  try {
    const requested = new URLSearchParams(location.search).get("thread");
    let conversation = await fetchConversation();
    if (requested && requested !== conversation.id) {
      conversation = await agentApi(`/api/v2/agent/threads/${requested}/resolve`).catch(() => conversation);
    }
    if (agentState.prism) return;
    agentState.threads = [conversation];
    renderThreads();
    if (requested) ui().setActiveTab?.("agent");
    await openThread(conversation.id);
  } catch (error) {
    const list = $("#agent-thread-list");
    if (list) {
      list.className = "thread-list empty-state";
      list.textContent = error.message;
    } else ui().setStatus?.(error.message, true);
  }
}

function renderThreads() {
  renderSidebarThreads();
  renderTodayThreads();
}

function openThreadFromList(thread) {
  ui().setActiveTab?.("agent");
  openThread(thread.id);
}

function renderSidebarThreads() {
  const list = $("#agent-thread-list");
  if (!list) return;
  const threads = agentState.threads;
  list.replaceChildren();
  list.className = `thread-list${threads.length ? "" : " empty-state"}`;
  if (!threads.length) {
    list.textContent = "Prism is ready.";
    return;
  }
  const limit = 8;
  (agentState.showAllThreads ? threads : threads.slice(0, limit)).forEach((thread) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `nav-item thread-item${thread.id === agentState.activeThread?.id ? " active" : ""}`;
    item.insertAdjacentHTML("afterbegin", CHAT_ICON);
    item.append(textElement("span", "thread-label", threadLabel(thread)));
    item.addEventListener("click", () => openThreadFromList(thread));
    list.append(item);
  });
  if (threads.length > limit) {
    const more = textElement("button", "nav-item thread-more", agentState.showAllThreads ? "Show fewer" : `Show ${threads.length - limit} more`);
    more.type = "button";
    more.addEventListener("click", () => {
      agentState.showAllThreads = !agentState.showAllThreads;
      renderSidebarThreads();
    });
    list.append(more);
  }
}

function renderTodayThreads() {
  const list = $("#today-thread-list");
  if (!list) return;
  const threads = agentState.threads.slice(0, 5);
  list.replaceChildren();
  list.className = threads.length ? "list" : "list empty-state";
  if (!threads.length) {
    list.textContent = "No activity yet. Open Prism to begin.";
    return;
  }
  threads.forEach((thread) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "list-item thread-row";
    row.append(
      textElement("strong", "", "Continue with Prism"),
      textElement("div", "meta", `${thread.source_label ? `Source constraint: ${thread.source_label} · ` : ""}${formatTime(thread.updated_at)}`),
    );
    row.addEventListener("click", () => openThreadFromList(thread));
    list.append(row);
  });
}

function renderHeader() {
  const thread = agentState.activeThread;
  const label = thread?.source_label;
  const participants = thread?.source_metadata?.participants || [];
  $("#agent-thread-title").textContent = agentState.prism?.name || "Prism";
  const headerLogo = $("#agent-thread-logo");
  headerLogo.hidden = !agentState.prism;
  if (agentState.prism) headerLogo.replaceChildren(prismLogo(agentState.prism, "prism-logo"));
  document.querySelectorAll("[data-needs-prism]").forEach((tab) => { tab.hidden = !agentState.prism; });
  onQaPrism(agentState.prism);
  renderPreferencesIntro();
  if ((agentState.prism?.id || null) !== agentState.preferencesFor) {
    agentState.preferences = [];
    agentState.preferencesFor = agentState.prism?.id || null;
    renderPreferences();
    loadPreferences({ silent: true });
  }
  if (!agentState.prism) setDrawerTab("preferences");
  $("#agent-source-label").textContent = !thread
    ? ""
    : label
      ? (participants.length ? `Source constraint · ${participants.slice(0, 4).join(", ")}${participants.length > 4 ? ` +${participants.length - 4}` : ""}` : `Source constraint · ${label}`)
      : "";
  $("#agent-source-chip-label").textContent = label || "All chats";
  $("#agent-source-chip").title = label
    ? "Requests are limited to this chat. Choose All chats to let Prism pick and disclose sources."
    : "All chats: Prism picks the relevant Teams chats and shows what it read. Choose one to limit requests.";
  $("#agent-source-chip").classList.toggle("empty", !label);
  $("#agent-message-input").placeholder = `Message ${agentState.prism?.name || "Prism"}`;
}

async function createThread() {
  const thread = await fetchConversation();
  agentState.threads = [thread];
  return thread;
}

async function newChat() {
  ui().setActiveTab?.("agent");
  try {
    const thread = agentState.threads[0] || await createThread();
    await openThread(thread.id);
    $("#agent-message-input").focus();
  } catch (error) {
    ui().setStatus?.(error.message, true);
  }
}

async function openThread(threadId) {
  const thread = agentState.threads.find((item) => item.id === threadId);
  if (!thread) return;
  const token = ++agentState.openToken;
  Object.assign(agentState, { activeThread: thread, messages: [], jobs: [], currentJob: null, turns: new Map(), loading: true, hasEarlier: false, anchor: null });
  const url = new URL(location.href);
  url.searchParams.delete("thread");
  history.replaceState({}, "", url);
  renderThreads();
  renderHeader();
  renderStream();
  try {
    const [messages, jobs] = await Promise.all([
      agentApi(messagesUrl(threadId)),
      agentApi(`/api/v2/agent/threads/${threadId}/jobs`),
    ]);
    if (token !== agentState.openToken) return;
    const turns = new Map(jobs.map((job) => [job.id, { job, review: null, evidence: new Map(), error: null }]));
    await ensureTurns(messages, turns);
    if (token !== agentState.openToken) return;
    Object.assign(agentState, { messages, jobs, currentJob: jobs[0] || null, turns, loading: false, hasEarlier: messages.length >= PAGE_SIZE });
  } catch (error) {
    if (token !== agentState.openToken) return;
    agentState.loading = false;
    ui().setStatus?.(error.message, true);
  }
  renderStream({ scroll: "bottom" });
}

// Evidence and the review are both optional: a queued or failed job may not have either yet.
async function hydrateTurn(turn) {
  const [evidence, review] = await Promise.allSettled([
    agentApi(`/api/v2/agent/jobs/${turn.job.id}/evidence`),
    agentApi(`/api/v2/agent/jobs/${turn.job.id}/review`),
  ]);
  if (evidence.status === "fulfilled") turn.evidence = new Map(evidence.value.map((item) => [item.id, item]));
  if (review.status === "fulfilled") turn.review = review.value;
}

// Older pages can reference jobs beyond the recent-jobs list; load and hydrate those on demand.
async function ensureTurns(messages, turns = agentState.turns) {
  const missing = [...new Set(messages.map((message) => message.job_id).filter((id) => id && !turns.has(id)))];
  const loaded = await Promise.all(missing.map((id) => agentApi(`/api/v2/agent/jobs/${id}`).catch(() => null)));
  loaded.filter(Boolean).forEach((job) => turns.set(job.id, { job, review: null, evidence: new Map(), error: null }));
  const ordered = [...new Set(messages.map((message) => message.job_id).filter(Boolean))].reverse().slice(0, 10);
  await Promise.all(ordered.map((id) => turns.get(id)).filter((turn) => turn && !turn.review).map(hydrateTurn));
}

async function refreshMessages() {
  const thread = agentState.activeThread;
  if (!thread) return;
  // Keep already-loaded older pages instead of collapsing back to the newest page.
  const messages = await agentApi(messagesUrl(thread.id, { limit: Math.min(Math.max(agentState.messages.length, PAGE_SIZE), 200) }));
  if (agentState.activeThread?.id !== thread.id) return;
  await ensureTurns(messages);
  agentState.messages = messages;
  renderStream();
  document.dispatchEvent(new CustomEvent("prism:updates-refresh"));
}

async function loadEarlier() {
  const thread = agentState.activeThread;
  const oldest = agentState.messages[0];
  if (!thread || !oldest) return;
  try {
    const earlier = await agentApi(messagesUrl(thread.id, { before: oldest.created_at }));
    if (agentState.activeThread?.id !== thread.id) return;
    await ensureTurns(earlier);
    agentState.messages = [...earlier, ...agentState.messages];
    agentState.hasEarlier = earlier.length >= PAGE_SIZE;
    renderStream({ scroll: "keep" });
    ui().setStatus?.(earlier.length ? `Loaded ${earlier.length} earlier messages.` : "No earlier messages.");
  } catch (error) {
    ui().setStatus?.(error.message, true);
  }
}

// Search results jump into history without turning past topics into separate chats.
async function viewHistoryAt(message) {
  const thread = agentState.activeThread;
  try {
    const upTo = new Date(new Date(message.created_at).getTime() + 1).toISOString();
    const messages = await agentApi(messagesUrl(thread.id, { before: upTo }));
    await ensureTurns(messages);
    Object.assign(agentState, { messages, anchor: message.id, hasEarlier: messages.length >= PAGE_SIZE });
    setSearchOpen(false);
    renderStream({ scroll: "bottom" });
    document.querySelector(`[data-message="${message.id}"]`)?.scrollIntoView({ block: "center" });
    document.querySelector(`[data-message="${message.id}"]`)?.focus();
  } catch (error) {
    ui().setStatus?.(error.message, true);
  }
}

async function backToLatest() {
  agentState.anchor = null;
  await refreshMessages();
  renderStream({ scroll: "bottom" });
  $("#agent-message-input").focus();
}

async function reloadTurn(jobId, { clearError = true } = {}) {
  const turn = agentState.turns.get(jobId);
  if (!turn) return;
  const [job, review] = await Promise.all([
    agentApi(`/api/v2/agent/jobs/${jobId}`),
    agentApi(`/api/v2/agent/jobs/${jobId}/review`).catch(() => null),
  ]);
  turn.job = job;
  if (review) turn.review = review;
  if (clearError) {
    turn.error = null;
    turn.errorCode = null;
  }
  if (agentState.currentJob?.id === jobId) agentState.currentJob = job;
  renderStream();
}

async function failTurn(jobId, error) {
  await reloadTurn(jobId, { clearError: false }).catch(() => {});
  const turn = agentState.turns.get(jobId);
  if (turn) {
    turn.error = error.message;
    turn.errorCode = error.code || null;
  }
  ui().setStatus?.(error.message, true);
  renderStream();
}

function updateTurnJob(job) {
  const turn = agentState.turns.get(job.id);
  if (!turn) return;
  turn.job = job;
  if (agentState.currentJob?.id === job.id) agentState.currentJob = job;
  const current = document.querySelector(`[data-progress="${job.id}"]`);
  if (current) current.replaceWith(renderProgressTurn(turn));
}

/* The conversation. ------------------------------------------------------ */

function renderStream({ scroll = "auto" } = {}) {
  const scroller = $("#agent-scroll");
  const timeline = $("#agent-timeline");
  const nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
  const previousTop = scroller.scrollTop;
  timeline.replaceChildren();
  timeline.className = "agent-timeline";
  if (agentState.loading && !agentState.pendingSubmission) {
    timeline.append(textElement("p", "agent-loading", "Loading conversation…"));
    return;
  }
  const { messages } = agentState;
  if ((!agentState.activeThread || (!messages.length && !agentState.jobs.length)) && !agentState.pendingSubmission && !agentState.updates.length) {
    timeline.append(renderWelcome());
    return;
  }
  const answered = new Set(messages.filter((message) => message.role !== "manager" && message.job_id).map((message) => message.job_id));
  if (agentState.anchor) timeline.append(renderHistoryBanner());
  if (agentState.hasEarlier) timeline.append(actionButton("Load earlier messages", "button secondary load-earlier", loadEarlier));
  let previous = null;
  // A centered time appears at the start, after a pause of 20 minutes, or when the day changes.
  let lastAt = null;
  const stamp = (value) => {
    if (!value) return;
    const at = new Date(value);
    if (lastAt === null || Math.abs(at - lastAt) >= STAMP_GAP_MS || at.toDateString() !== lastAt.toDateString()) timeline.append(renderTimeStamp(value));
    lastAt = at;
  };
  // Oldest first, so each update sits between the messages around the time it was found.
  const updates = [...agentState.updates].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  const flushUpdates = (before) => {
    while (updates.length && (!before || new Date(updates[0].created_at) <= new Date(before))) {
      stamp(updates[0].created_at);
      timeline.append(renderUpdate(updates.shift()));
    }
  };
  messages.forEach((message) => {
    flushUpdates(message.created_at);
    stamp(message.created_at);
    if (message.role === "manager") {
      const separator = renderTopicSeparator(message, previous);
      if (separator) timeline.append(separator);
      previous = message;
      timeline.append(renderUserMessage(message));
      const turn = agentState.turns.get(message.job_id);
      if (turn && !answered.has(message.job_id)) timeline.append(renderProgressTurn(turn));
    } else {
      timeline.append(renderAssistantMessage(message));
    }
  });
  flushUpdates();
  if (agentState.pendingSubmission) {
    const pending = agentState.pendingSubmission;
    stamp(pending.createdAt);
    timeline.append(renderUserMessage({
      id: "pending-submission",
      content: pending.content,
      created_at: pending.createdAt,
    }));
    const { article, body } = assistantShell("working pending-submission");
    body.append(typingBubble(pending.label));
    timeline.append(article);
  }
  timeline.querySelectorAll("textarea.autogrow").forEach((textarea) => autoGrow(textarea));
  if (scroll === "keep") return;
  scroller.scrollTop = scroll === "bottom" || (scroll === "auto" && nearBottom) ? scroller.scrollHeight : previousTop;
  updateJumpButton();
}

// Scrolled up to read earlier messages: offer a way straight back to the latest.
function updateJumpButton() {
  const scroller = $("#agent-scroll");
  $("#agent-jump-latest").hidden = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 240;
}

const STAMP_GAP_MS = 20 * 60 * 1000;
const clockText = (date) => date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

// Centered time between messages: the clock for today, then day and clock the further back it is.
function stampLabel(value) {
  const date = new Date(value);
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(date).setHours(0, 0, 0, 0)) / 86400000);
  if (days <= 0) return clockText(date);
  if (days === 1) return `Yesterday, ${clockText(date)}`;
  if (days < 7) return `${date.toLocaleDateString([], { weekday: "long" })}, ${clockText(date)}`;
  const day = date.toLocaleDateString([], { day: "numeric", month: "short", year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
  return `${day}, ${clockText(date)}`;
}

function renderTimeStamp(value) {
  const stamp = textElement("time", "chat-stamp", stampLabel(value));
  stamp.dateTime = new Date(value).toISOString();
  stamp.title = formatTime(value);
  return stamp;
}

const scopeKey = (job) => `${job?.scope_mode || ""}:${(job?.sources || []).map((source) => source.external_id).sort().join(",")}`;

// A separator appears when Prism starts working from a different source set.
function renderTopicSeparator(message, previous) {
  const job = agentState.turns.get(message.job_id)?.job;
  const previousJob = previous && agentState.turns.get(previous.job_id)?.job;
  const newTopic = Boolean(previous && job?.sources?.length && previousJob?.sources?.length && scopeKey(job) !== scopeKey(previousJob));
  if (!newTopic) return null;
  const separator = textElement("div", "topic-separator");
  separator.setAttribute("role", "separator");
  const parts = [];
  if (newTopic) parts.push(`New topic · ${job.sources.map((source) => source.label || "Teams chat").join(", ")}`);
  separator.append(textElement("span", "", parts.join(" · ")));
  return separator;
}

function renderHistoryBanner() {
  const banner = textElement("div", "callout quiet history-banner");
  banner.append(
    textElement("span", "callout-icon", "↑"),
    textElement("div", "callout-body", "Viewing earlier history."),
    actionButton("Back to latest", "mini-button", backToLatest),
  );
  return banner;
}

// A long job description becomes a one-line blurb: the first sentence, cut at a word boundary.
function briefDescription(text, limit = 140) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (!clean) return "Ask me about your team’s work and I’ll look into it.";
  const first = clean.match(/^.*?[.!?](?=\s|$)/)?.[0] || clean;
  if (first.length <= limit) return first;
  return `${first.slice(0, limit).replace(/\s+\S*$/, "")}…`;
}

// Shown only while the conversation is empty, so they appear once after onboarding.
async function addFirstSuggestions(welcome, prism) {
  const key = `prism-first-suggestions-v2:${prism.id}`;
  let data = {};
  try { data = JSON.parse(localStorage.getItem(key) || "{}"); } catch { data = {}; }
  if (!data.steps?.length && !data.suggestions?.length) {
    try {
      data = await agentApi(`/api/v2/prisms/${prism.id}/suggestions`);
      if (data.steps?.length || data.suggestions?.length) {
        try { localStorage.setItem(key, JSON.stringify(data)); } catch { /* storage unavailable */ }
      }
    } catch { return; }
  }
  if (!welcome.isConnected) return;
  const list = welcome.querySelector(".welcome-steps");
  if (list && data.steps?.length) list.replaceChildren(...data.steps.map((step) => textElement("li", "", step)));
  if (!data.suggestions?.length) return;
  const chips = textElement("div", "suggestions");
  data.suggestions.forEach((suggestion) => chips.append(actionButton(suggestion, "mini-button", () => {
    const input = $("#agent-message-input");
    input.value = suggestion;
    input.dispatchEvent(new Event("input"));
    input.focus();
  })));
  welcome.append(chips);
}

function renderWelcome() {
  const thread = agentState.activeThread;
  const label = thread?.source_label;
  const welcome = textElement("div", "agent-welcome");
  welcome.append(agentState.prism
    ? prismLogo(agentState.prism, "prism-logo welcome-logo")
    : textElement("span", "welcome-mark", "P"));
  if (!label) {
    welcome.append(
      textElement("h2", "", agentState.prism ? `Talk to your ${agentState.prism.name} Prism` : "Talk to your manager agent"),
      textElement("p", "welcome-about", agentState.prism ? briefDescription(agentState.prism.description) : "Ask naturally and Prism will disclose which Teams chats it reads. Use the chat selector in the message box to limit a request to one chat."),
    );
    const steps = textElement("ol", "welcome-steps");
    (agentState.prism?.template_key === "qa_tester"
      ? ["Tell me a site to test, for example “test example.com and check the contact form”", "I'll show you a plan; you decide when I start", "Watch my screen on the right, then read my report here"]
      : agentState.prism && computersEnabled()
      ? ["Give me a task, for example “find 5 fintech companies in Bangalore and list their websites”", "I'll show you a plan; you decide when I start", "Watch my computer on the right, then read my report here"]
      : ["Ask naturally and Prism will choose the relevant chats", "Select a chat only when you want a hard one-chat limit", "Check the evidence and approve only actions you requested"]).forEach((step) => steps.append(textElement("li", "", step)));
    welcome.append(steps);
    if (agentState.prism && computersEnabled()) addFirstSuggestions(welcome, agentState.prism);
  } else {
    welcome.append(
      textElement("h2", "", `Ask Prism about ${label}`),
      textElement("p", "", "Prism reads this conversation and shows the evidence behind everything it flags."),
    );
    const chips = textElement("div", "suggestions");
    SUGGESTIONS.forEach((suggestion) => chips.append(actionButton(suggestion, "mini-button", () => {
      const input = $("#agent-message-input");
      input.value = suggestion;
      input.dispatchEvent(new Event("input"));
      input.focus();
    })));
    welcome.append(chips);
  }
  return welcome;
}

function renderUserMessage(message) {
  const article = textElement("article", "turn user");
  article.dataset.message = message.id;
  article.tabIndex = -1;
  const bubble = textElement("div", "bubble");
  bubble.title = formatTime(message.created_at);
  bubble.append(textElement("p", "", message.content));
  article.append(bubble);
  return article;
}

function assistantShell(extraClass = "") {
  const article = textElement("article", `turn assistant ${extraClass}`.trim());
  const body = textElement("div", "turn-body");
  article.append(textElement("span", "avatar prism", "P"), body);
  return { article, body };
}

// One chat bubble. Replies read like messages from a colleague; the machinery lives in details.
function msgBubble(...children) {
  const bubble = textElement("div", "say");
  bubble.append(...children);
  return bubble;
}

// "• Title → detail" lines, the way a person would summarise a list in chat.
function listBubble(intro, rows) {
  const bubble = textElement("div", "say say-list");
  if (intro) bubble.append(textElement("p", "", intro));
  rows.forEach(([title, detail]) => {
    const line = textElement("p", "say-line");
    line.append(textElement("strong", "", title));
    if (detail) line.append(` → ${detail}`);
    bubble.append(line);
  });
  return bubble;
}

function typingBubble(label) {
  const bubble = textElement("div", "say say-typing");
  bubble.setAttribute("role", "status");
  const dots = textElement("span", "typing-dots");
  dots.setAttribute("aria-hidden", "true");
  dots.append(textElement("i"), textElement("i"), textElement("i"));
  bubble.append(dots, textElement("span", "sr-only", label));
  return bubble;
}

// Sources, confidence, evidence, and the audit trail stay one click away instead of in the message.
const openDetails = new Set();
function turnDetails(label, key) {
  const details = textElement("details", "turn-details");
  if (key) {
    details.open = openDetails.has(key);
    details.addEventListener("toggle", () => { if (details.open) openDetails.add(key); else openDetails.delete(key); });
  }
  details.append(textElement("summary", "", label));
  const content = textElement("div", "turn-details-body");
  details.append(content);
  return { details, content };
}

function confidenceText(confidence) {
  return confidence >= 0.75 ? "High confidence" : confidence >= 0.5 ? "Medium confidence" : "Low confidence";
}

function readLabel(turn) {
  const read = (turn.job.sources || []).filter((source) => source.selection_reason !== "destination").map((source) => source.label || "Teams chat");
  const count = turn.evidence.size;
  const who = read.length > 2 ? `${read.slice(0, 2).join(", ")} +${read.length - 2}` : read.join(", ");
  if (count && who) return `Read ${count} message${count === 1 ? "" : "s"} · ${who}`;
  if (who) return who;
  return "Details";
}

function renderAssistantMessage(message) {
  const turn = agentState.turns.get(message.job_id);
  if (turn?.review && message.message_metadata?.kind === "conversation_review") return renderReviewTurn(turn);
  const { article, body } = assistantShell();
  const qa = renderQaMessage(message);
  if (qa) {
    if (qa.lead) body.append(msgBubble(textElement("p", "review-summary", qa.lead)));
    body.append(qa.card);
    return article;
  }
  body.append(msgBubble(textElement("p", "review-summary", message.content)));
  return article;
}

/* A review: summary, what needs attention, a draft reply, and the audit trail. */

function appendEvidence(container, turn, ids, label = "Evidence") {
  const cited = (ids || []).map((id) => turn.evidence.get(id)).filter(Boolean);
  if (!cited.length) return;
  const details = textElement("details", "evidence");
  const summary = textElement("summary", "", label);
  summary.append(textElement("span", "tab-count", String(cited.length)));
  details.append(summary);
  const groups = new Map();
  cited.forEach((item) => {
    const key = item.source_external_id || "unknown";
    if (!groups.has(key)) groups.set(key, { label: item.source_label || "Teams chat", items: [] });
    groups.get(key).items.push(item);
  });
  groups.forEach((group) => {
    if (groups.size > 1) details.append(textElement("h4", "evidence-source", group.label));
    group.items.forEach((item) => {
      const quote = document.createElement("blockquote");
      const head = textElement("div", "quote-head");
      head.append(textElement("strong", "", item.sender_display_name), textElement("time", "", formatTime(item.sent_at)));
      quote.append(head, textElement("p", "", item.excerpt));
      details.append(quote);
    });
  });
  container.append(details);
}

function reviewSection(title, count, children) {
  const section = textElement("section", "review-section");
  const heading = textElement("h3", "", title);
  heading.append(textElement("span", "tab-count", String(count)));
  section.append(heading, ...children);
  return section;
}

function renderFinding(turn, kind, title, detail, evidenceIds) {
  const finding = textElement("div", `finding ${kind}`);
  const heading = textElement("div", "finding-head");
  heading.append(textElement("strong", "", title));
  if (["inference", "conflict"].includes(kind)) heading.append(textElement("span", `tag ${kind === "conflict" ? "orange" : "blue"}`, kind === "conflict" ? "Conflicting updates" : "Cross-chat inference"));
  finding.append(heading);
  if (detail) finding.append(textElement("p", "", detail));
  appendEvidence(finding, turn, evidenceIds);
  return finding;
}

function renderReviewTurn(turn) {
  const { review, job } = turn;
  const { article, body } = assistantShell();
  article.dataset.job = job.id;
  // When you asked for a message, the draft is the answer. The analysis behind it stays in details.
  if (review.action_plan) body.append(renderActionPlan(turn));
  else if (review.proposal) {
    const to = review.proposal.destination?.label || "them";
    body.append(msgBubble(textElement("p", "review-summary", `Here’s a draft for ${to}. Have a look before it goes out.`)));
    body.append(renderDraft(turn));
  } else {
    body.append(msgBubble(textElement("p", "review-summary", review.summary)));
    if (review.attention_items.length) {
      body.append(listBubble(review.attention_items.length > 1 ? "What needs you:" : "", review.attention_items.map((item) => [item.title, item.detail])));
    }
    if (review.manager_questions.length === 1) body.append(msgBubble(textElement("p", "", review.manager_questions[0].question)));
    else if (review.manager_questions.length > 1) body.append(listBubble("A few things I need from you:", review.manager_questions.map((item) => [item.question, ""])));
  }

  const footer = textElement("div", "turn-quiet");
  const { details, content } = turnDetails(readLabel(turn), `review:${job.id}`);
  content.append(textElement("p", "turn-meta", confidenceText(review.confidence)), renderSourceDisclosure(job));
  if (review.action_plan || review.proposal) content.append(textElement("p", "", review.summary));
  appendEvidence(content, turn, review.summary_evidence_ids, "Messages behind this");
  if (review.attention_items.length) {
    content.append(reviewSection("Needs your attention", review.attention_items.length,
      review.attention_items.map((item) => renderFinding(turn, item.kind || "direct", item.title, item.detail, item.evidence_ids))));
  }
  if (review.manager_questions.length) {
    content.append(reviewSection("Questions for you", review.manager_questions.length,
      review.manager_questions.map((item) => renderFinding(turn, "question", item.question, "", item.evidence_ids))));
  }
  if (review.limitations?.length) {
    const limits = textElement("details", "limitations");
    limits.append(textElement("summary", "", "What Prism could not verify"));
    const list = document.createElement("ul");
    review.limitations.forEach((limit) => list.append(textElement("li", "", limit)));
    limits.append(list);
    content.append(limits);
  }
  content.append(renderAudit(turn));
  footer.append(details);
  const single = (job.sources || []).length <= 1;
  if (!review.action_plan && !review.proposal && !review.requires_reply && single && (review.attention_items.length || review.manager_questions.length)) {
    footer.append(actionButton("Draft a follow-up", "link-button", () => draftFollowUp(job)));
  }
  body.append(footer);
  if (turn.error) body.append(renderFailure({ code: turn.errorCode, message: turn.error }));
  const recovery = textElement("div", "item-actions");
  if (job.state === "executing") recovery.append(actionButton("Check interrupted delivery", "mini-button", () => recoverJob(job)));
  if (["failed", "cancelled"].includes(job.state)) recovery.append(actionButton("Retry", "mini-button", () => retryJob(job, false)));
  if (recovery.children.length) body.append(recovery);
  return article;
}

function draftState(proposal, execution) {
  if (execution?.state === "succeeded" || proposal.state === "executed") return { key: "sent", label: "Sent", tone: "green" };
  if (execution?.state === "uncertain") return { key: "uncertain", label: "Needs confirmation", tone: "orange" };
  if (execution?.state === "failed" || proposal.state === "failed") return { key: "failed", label: "Failed", tone: "red" };
  if (execution?.state === "running" || proposal.state === "executing") return { key: "sending", label: "Sending", tone: "blue" };
  if (proposal.state === "approved") return { key: "approved", label: "Approved", tone: "blue" };
  if (proposal.state === "rejected") return { key: "rejected", label: "Rejected", tone: "gray" };
  if (proposal.state === "expired") return { key: "expired", label: "Expired", tone: "gray" };
  return { key: "pending", label: "Awaiting approval", tone: "orange" };
}

function draftStatusText(proposal, execution) {
  if (execution?.state === "running") return "Sending through your connected Microsoft account…";
  if (execution?.state === "succeeded") return `Delivered from your Microsoft Teams account${execution.completed_at ? ` · ${formatTime(execution.completed_at)}` : ""}.`;
  if (execution?.state === "failed") return execution.safe_error_detail || "Delivery failed.";
  if (execution?.state === "uncertain") return execution.safe_error_detail || "Delivery confirmation required; Prism will not retry automatically.";
  return {
    pending: "Nothing is sent until you approve.",
    approved: "Approved. Ready to send.",
    rejected: "Rejected. Nothing was sent.",
    expired: "This draft expired. Nothing was sent.",
    draft: "Draft.",
    executing: "Sending…",
    executed: "Delivered from your Microsoft Teams account.",
    failed: "Delivery failed.",
  }[proposal.state] || `Status: ${humanize(proposal.state)}.`;
}

function renderActionPlan(turn) {
  const plan = turn.review.action_plan;
  const section = textElement("section", `action-plan plan-${plan.state}`);
  const pendingCount = plan.actions.filter(({ proposal }) => proposal.state === "pending").length;
  section.append(msgBubble(textElement("p", "", pendingCount
    ? `${plan.summary}. ${pendingCount === 1 ? "One message is" : `${pendingCount} messages are`} ready for you to check.`
    : `${plan.summary}.`)));

  const pending = plan.actions.filter(({ proposal }) => proposal.state === "pending");
  if (pending.length > 1) {
    const bulk = actionButton(`Approve all ${pending.length} visible drafts`, "button secondary", (event) => approveActionPlan(turn, event.currentTarget));
    bulk.disabled = pending.some(({ proposal }) => agentState.drafts.has(proposal.id));
    const notice = textElement("div", "action-plan-bulk");
    notice.append(
      textElement("span", "panel-note", "Sends exactly the messages below, as written."),
      bulk,
    );
    section.append(notice);
  }
  plan.actions.forEach(({ proposal, execution }, index) => {
    const wrapper = textElement("div", "planned-action");
    if (proposal.depends_on_logical_action_ids?.length) wrapper.append(textElement("div", "planned-action-order", "Goes after the previous message"));
    wrapper.append(renderDraft(turn, proposal, execution));
    section.append(wrapper);
  });
  return section;
}

function renderDraft(turn, selectedProposal = null, selectedExecution = null) {
  const { review, job } = turn;
  const proposal = selectedProposal || review.proposal;
  const execution = selectedProposal ? selectedExecution : review.execution;
  const state = draftState(proposal, execution);
  const card = textElement("section", `draft-card ${state.key}`);

  const head = textElement("div", "draft-head");
  const label = proposal.destination.label || "the selected Teams chat";
  const destination = textElement("span", "draft-dest", "To ");
  destination.append(textElement("strong", "", label));
  head.append(textElement("span", "draft-avatar", label.trim().charAt(0).toUpperCase()), destination, textElement("span", `draft-state ${state.tone}`, state.label));
  card.append(head);

  const textarea = document.createElement("textarea");
  textarea.className = "draft-body autogrow";
  textarea.rows = 2;
  textarea.setAttribute("aria-label", "Reply that will be sent to Teams");
  textarea.value = agentState.drafts.get(proposal.id) ?? proposal.body;
  textarea.readOnly = proposal.state !== "pending";
  card.append(textarea);

  // No stored Teams messages back this draft; say so instead of implying evidence.
  const fromTests = Boolean(job.requested_scope?.qa_draft);
  if (fromTests) {
    card.append(textElement("p", "draft-basis", "Written from my test results, not from Teams messages. Edit it as you like, then approve to send."));
  } else if (!proposal.evidence_ids?.length) {
    card.append(textElement("p", "draft-basis", "Based on your instruction. There were no Teams messages to go on, so check it before sending."));
  }
  const status = textElement("p", `draft-status ${state.tone}`, draftStatusText(proposal, execution));
  card.append(status);

  // Why it was written, what it was based on, and which preferences shaped it stay one click away.
  const more = textElement("details", "draft-more");
  const detailKey = `draft:${proposal.id}`;
  more.open = openDetails.has(detailKey);
  more.addEventListener("toggle", () => { if (more.open) openDetails.add(detailKey); else openDetails.delete(detailKey); });
  more.append(textElement("summary", "", "Why this reply"));
  const moreBody = textElement("div", "draft-more-body");
  moreBody.append(textElement("p", "", proposal.reason));
  appendEvidence(moreBody, turn, proposal.evidence_ids, "Messages behind this reply");
  if (review.applied_preferences?.length) {
    const used = textElement("div", "pref-used");
    used.append(textElement("span", "pref-label", "Shaped by your preferences"));
    review.applied_preferences.forEach((item) => {
      const chip = textElement("span", "pref-chip", item.instruction);
      chip.title = item.instruction;
      used.append(chip);
    });
    used.append(actionButton("Manage", "link-button", () => setPreferencesOpen(true)));
    moreBody.append(used);
  }
  more.append(moreBody);
  card.append(more);

  if (proposal.state === "pending") {
    const actions = textElement("div", "draft-actions");
    const reject = actionButton("Reject", "button ghost", () => rejectDraft(turn, proposal));
    const regenerate = actionButton("Redraft", "button ghost", () => requestActionRedraft(proposal));
    const save = actionButton("Save edit", "button secondary", () => reviseProposal(turn, proposal, textarea.value));
    const approve = actionButton("Approve and send", "button approve", () => approveAndSend(turn, proposal, approve));
    actions.append(reject, ...(fromTests ? [] : [regenerate]), textElement("span", "spacer"), save, approve);
    card.append(actions);
    // An edited draft must be saved first so the approval covers exactly the text on screen.
    const sync = () => {
      const dirty = textarea.value.trim() !== proposal.body.trim();
      if (dirty) agentState.drafts.set(proposal.id, textarea.value);
      else agentState.drafts.delete(proposal.id);
      save.hidden = !dirty;
      save.disabled = !textarea.value.trim();
      approve.disabled = dirty || !textarea.value.trim();
      status.textContent = dirty ? "You edited this draft. Save the edit, then approve it." : draftStatusText(proposal, execution);
    };
    textarea.addEventListener("input", () => { autoGrow(textarea); sync(); });
    sync();
  } else {
    const actions = textElement("div", "draft-actions");
    if (proposal.state === "approved" && !execution) {
      actions.append(textElement("span", "spacer"), actionButton("Send approved message", "button", (event) => sendApprovedProposal(turn, proposal, event.currentTarget)));
    } else if (!fromTests && (["rejected", "expired", "failed"].includes(proposal.state) || ["failed"].includes(execution?.state))) {
      actions.append(textElement("span", "spacer"), actionButton("Regenerate", "button secondary", () => retryJob(job, true)));
    }
    if (actions.children.length) card.append(actions);
  }
  return card;
}

// Every review, edit, approval, and delivery is stored; this makes that visible.
function renderAudit(turn) {
  const { job, review } = turn;
  const events = [["Review requested", job.created_at]];
  if (turn.evidence.size) events.push([`Read ${turn.evidence.size} Teams message${turn.evidence.size === 1 ? "" : "s"}`, job.started_at || job.created_at]);
  events.push([`Review prepared · ${review.provider} ${review.model}`, review.created_at]);
  const actionRecords = review.action_plan?.actions || (review.proposal
    ? [{ proposal: review.proposal, execution: review.execution }]
    : []);
  actionRecords.forEach(({ proposal, execution }) => {
    const destination = proposal.destination.label || "Teams";
    events.push([proposal.revision > 1 ? `Edited by you · revision ${proposal.revision}` : "Draft created", proposal.created_at]);
    if (proposal.approval) {
      const approval = proposal.approval;
      const decision = `${humanize(approval.decision).replace(/^./, (letter) => letter.toUpperCase())} by ${approval.manager_identity}`;
      events.push([approval.reason ? `${decision} · ${approval.reason}` : decision, approval.decided_at]);
    }
    if (execution) {
      const label = { succeeded: "Delivered to Teams", failed: "Delivery failed", uncertain: "Delivery unconfirmed", running: "Sending started" }[execution.state] || "Delivery queued";
      events.push([`${label} · ${destination}`, execution.completed_at || execution.started_at || execution.created_at]);
    }
  });
  const details = textElement("details", "audit");
  const summary = textElement("summary", "", "Audit trail");
  summary.append(textElement("span", "tab-count", String(events.length)));
  details.append(summary);
  const list = textElement("ol", "audit-list");
  events.forEach(([label, time]) => {
    const item = document.createElement("li");
    item.append(textElement("span", "", label), textElement("time", "", formatTime(time)));
    list.append(item);
  });
  details.append(list);
  return details;
}

/* A review that is still running, or did not finish. -------------------- */

function renderProgressTurn(turn) {
  const { job } = turn;
  const { article, body } = assistantShell("working");
  article.dataset.progress = job.id;
  const active = ACTIVE_JOB_STATES.includes(job.state) || job.state === "executing";
  const failure = job.safe_error_detail
    ? { code: job.safe_error_code, message: job.safe_error_detail }
    : turn.error ? { code: turn.errorCode, message: turn.error } : null;
  if (active && !failure) body.append(typingBubble(PROGRESS_LABELS[job.state] || humanize(job.state)));
  else if (!failure) body.append(msgBubble(textElement("p", "", job.state === "cancelled" ? "Stopped before I finished this one." : "I didn't get to finish this one.")));
  else if (RECOVERY[failure.code]) body.append(renderFailure(failure));
  else body.append(msgBubble(textElement("p", "", `I couldn't finish this one. ${failure.message}`)));
  const controls = textElement("div", "item-actions");
  if (job.state === "executing") controls.append(actionButton("Check interrupted delivery", "mini-button", () => recoverJob(job)));
  if (["failed", "cancelled"].includes(job.state)) controls.append(actionButton("Retry", "mini-button", () => retryJob(job, false)));
  if (controls.children.length) body.append(controls);
  // What it is reading and the step list stay available, out of the conversation.
  const { details, content } = turnDetails(active ? "Working on it" : "Details", `progress:${job.id}`);
  content.append(renderSourcePlan(job, true));
  if (job.steps.length) {
    const steps = textElement("ul", "step-list");
    job.steps.forEach((step) => steps.append(textElement("li", `step ${step.state}`, step.label)));
    content.append(steps);
  }
  if (ACTIVE_JOB_STATES.includes(job.state)) {
    const stop = textElement("div", "item-actions");
    stop.append(actionButton("Cancel", "mini-button", () => cancelJob(job)), actionButton("Resume", "mini-button", () => recoverJob(job)));
    content.append(stop);
  }
  const quiet = textElement("div", "turn-quiet");
  quiet.append(details);
  body.append(quiet);
  return article;
}

/* Choosing a Teams chat. ------------------------------------------------- */

const SCOPE_LABELS = {
  auto: "Auto-selected",
  chat: "You limited this to one chat",
  person: "You limited this to one person",
  "explicit-set": "Sources you chose",
};
const CHAT_KINDS = { oneonone: "1:1 chat", group: "Group chat", private: "1:1 chat", meeting: "Meeting chat" };

// Compact chips say which chats Prism read; the details say why and under what limits.
function renderSourceDisclosure(job) {
  const sources = job.sources || [];
  const wrapper = textElement("div", "source-disclosure");
  if (!sources.length) return wrapper;
  const chips = textElement("div", "source-chips");
  chips.append(textElement("span", "source-chips-label", "Read from"));
  sources
    .filter((source) => source.selection_reason !== "destination")
    .forEach((source) => chips.append(textElement("span", "tag blue", source.label || "Teams chat")));
  sources
    .filter((source) => source.selection_reason === "destination")
    .forEach((source) => chips.append(textElement("span", "tag purple", `Draft to ${source.label || "Teams chat"}`)));
  chips.append(textElement("span", "tag", SCOPE_LABELS[job.scope_mode] || humanize(job.scope_mode)));
  wrapper.append(chips, renderSourcePlan(job));
  return wrapper;
}

function renderSourcePlan(job, open = false) {
  const details = textElement("details", "source-plan");
  details.open = open;
  const sources = job.sources || [];
  const summary = textElement("summary", "", sources.length ? "Why these sources" : "Resolving source");
  if (sources.length) summary.append(textElement("span", "tab-count", String(sources.length)));
  details.append(summary);
  if (!sources.length) {
    details.append(textElement("p", "panel-note", "Prism is resolving an accessible Teams chat from your request."));
    return details;
  }
  const list = textElement("ul", "source-plan-list");
  sources.forEach((source) => {
    const metadata = source.source_metadata || {};
    const kind = CHAT_KINDS[String(metadata.chat_type || "").toLowerCase()];
    const participants = (metadata.participants || []).slice(0, 4).join(", ");
    const item = document.createElement("li");
    item.append(
      textElement("strong", "", source.label || "Teams chat"),
      textElement("span", "", [kind, participants].filter(Boolean).join(" · ")),
      textElement(
        "span",
        "",
        source.selection_reason === "destination"
          ? "Draft destination only · Prism did not read this chat"
          : (metadata.resolution_rationale || humanize(source.selection_reason)),
      ),
    );
    list.append(item);
  });
  details.append(list);
  const scope = job.requested_scope || {};
  const notes = [];
  if ((scope.excluded_external_ids || []).length) notes.push(`${scope.excluded_external_ids.length} chat(s) excluded at your request`);
  Object.entries(scope.limits || {}).forEach(([key, value]) => {
    if (["number", "string"].includes(typeof value)) notes.push(`${humanize(key)}: ${value}`);
  });
  if (notes.length) details.append(textElement("p", "panel-note", `Limits · ${notes.join(" · ")}`));
  details.append(textElement("p", "panel-note", "Reading a chat never lets Prism write to it. Every destination is shown separately on its own approval card."));
  return details;
}

async function chooseSource() {
  try {
    if (!agentState.activeThread) await openThread((await createThread()).id);
  } catch (error) {
    ui().setStatus?.(error.message, true);
    return;
  }
  const dialog = $("#agent-source-dialog");
  const search = $("#agent-source-search");
  $("#agent-source-dialog-title").textContent = "Choose a Teams source constraint";
  $("#agent-source-dialog-note").textContent = "All chats lets Prism choose for every request. Choose one chat only to apply a hard constraint.";
  search.value = "";
  $("#agent-source-list").className = "agent-source-list empty-state";
  $("#agent-source-list").replaceChildren(textElement("span", "spinner"), document.createTextNode(" Loading your Teams chats…"));
  dialog.showModal();
  search.focus();
  try {
    const result = await agentApi("/api/v2/agent/sources/teams");
    agentState.sources = result.items;
    renderSources("");
  } catch (error) {
    $("#agent-source-list").textContent = error.message;
  }
}

function renderSources(query) {
  const list = $("#agent-source-list");
  const needle = query.trim().toLowerCase();
  const sources = agentState.sources.filter((source) =>
    `${source.label} ${source.participants.join(" ")}`.toLowerCase().includes(needle));
  list.replaceChildren();
  if (!needle) {
    const auto = document.createElement("button");
    auto.type = "button";
    auto.className = "source-option";
    const copy = textElement("span", "source-copy");
    copy.append(textElement("strong", "", "All chats"), textElement("span", "", "Prism picks the relevant Teams chats from each request"));
    auto.append(avatarFor("All chats"), copy);
    auto.addEventListener("click", clearSourceConstraint);
    list.append(auto);
  }
  list.className = `agent-source-list${sources.length || list.children.length ? "" : " empty-state"}`;
  if (!sources.length && !list.children.length) {
    list.textContent = "No matching Teams chats.";
    return;
  }
  const kinds = { oneonone: "1:1", group: "Group", meeting: "Meeting" };
  sources.forEach((source) => {
    const option = document.createElement("button");
    option.type = "button";
    option.className = "source-option";
    const copy = textElement("span", "source-copy");
    copy.append(
      textElement("strong", "", source.label),
      textElement("span", "", source.resolution_rationale || `${kinds[String(source.chat_type).toLowerCase()] || humanize(source.chat_type)} · ${source.participants.join(", ") || "Participants unavailable"}`),
    );
    option.append(avatarFor(source.label), copy);
    option.addEventListener("click", () => selectSource(source, option));
    list.append(option);
  });
}

// Choosing a chat saves it on the server, which can take a few seconds: show it working, and ignore
// further clicks until it is done.
function markChoosing(option, text) {
  const list = $("#agent-source-list");
  list.classList.add("is-busy");
  list.setAttribute("aria-busy", "true");
  option.classList.add("choosing");
  option.querySelector(".source-copy span")?.replaceChildren(document.createTextNode(text));
  option.append(textElement("span", "spinner"));
  return () => {
    list.classList.remove("is-busy");
    list.removeAttribute("aria-busy");
    option.classList.remove("choosing");
    option.querySelector(".spinner")?.remove();
  };
}

async function clearSourceConstraint(event) {
  const thread = agentState.activeThread;
  const done = event?.currentTarget ? markChoosing(event.currentTarget, "Switching to all chats…") : () => {};
  try {
    const updated = await agentApi(`/api/v2/agent/threads/${thread.id}/source/teams`, { method: "DELETE" });
    agentState.activeThread = updated;
    agentState.threads = agentState.threads.map((item) => item.id === updated.id ? updated : item);
    $("#agent-source-dialog").close();
    renderThreads();
    renderHeader();
    if (!agentState.messages.length) renderStream();
    $("#agent-message-input").focus();
  } catch (error) {
    ui().setStatus?.(error.message, true);
    done();
  }
}

async function selectSource(source, option) {
  const thread = agentState.activeThread;
  if (thread.source_external_id && thread.source_external_id !== source.external_id && agentState.jobs.length) {
    const confirmed = await ui().askDialog?.({
      title: "Change the Teams chat?",
      message: "Future reviews in this Prism conversation will use the new source constraint. Existing reviews keep their original source.",
      confirmLabel: "Change constraint",
    });
    if (confirmed === null) return;
  }
  const done = option ? markChoosing(option, "Selecting this chat…") : () => {};
  try {
    const updated = await agentApi(`/api/v2/agent/threads/${thread.id}/source/teams`, {
      method: "PUT",
      body: JSON.stringify({ external_id: source.external_id }),
    });
    agentState.activeThread = updated;
    agentState.threads = agentState.threads.map((item) => item.id === updated.id ? updated : item);
    $("#agent-source-dialog").close();
    renderThreads();
    renderHeader();
    if (!agentState.messages.length) renderStream();
    $("#agent-message-input").focus();
  } catch (error) {
    ui().setStatus?.(error.message, true);
    done();
  }
}

/* Asking, running, and acting on a review. ------------------------------- */

// Failures before a job exists (reconnect, permission, throttling) have no turn to live in.
function showComposerFailure(error) {
  const slot = $("#agent-composer-notice");
  slot.replaceChildren();
  if (error) slot.append(renderFailure({ code: error.code, message: error.message }));
}

function showPendingSubmission(content, label = "Getting Prism ready…") {
  agentState.pendingSubmission = { content, label, createdAt: new Date().toISOString() };
  renderStream({ scroll: "bottom" });
}

function updatePendingSubmission(label) {
  if (!agentState.pendingSubmission) return;
  agentState.pendingSubmission.label = label;
  renderStream({ scroll: "bottom" });
}

function clearPendingSubmission() {
  agentState.pendingSubmission = null;
}

async function draftFollowUp(job) {
  const destination = job.source_label || "the selected Teams conversation";
  const instruction = await ui().askDialog?.({
    title: "Draft a follow-up",
    message: `Prism will prepare a Teams draft for ${destination}. Nothing will be sent until you approve it.`,
    confirmLabel: "Create draft",
    field: {
      label: "Follow-up instruction",
      value: `Draft a follow-up message to ${destination} based on this update.`,
      placeholder: "Tell Prism what the follow-up should cover",
    },
  });
  if (!instruction?.trim()) return;
  const input = $("#agent-message-input");
  input.value = instruction.trim();
  input.dispatchEvent(new Event("input"));
  $("#agent-composer").requestSubmit();
}

async function submitMessage(event) {
  event.preventDefault();
  showComposerFailure(null);
  const input = $("#agent-message-input");
  const content = input.value.trim();
  if (!content) return;
  setComposerBusy(true);
  input.value = "";
  input.dispatchEvent(new Event("input"));
  showPendingSubmission(content);
  try {
    if (!agentState.activeThread) await openThread((await createThread()).id);
  } catch (error) {
    clearPendingSubmission();
    input.value = content;
    input.dispatchEvent(new Event("input"));
    renderStream();
    ui().setStatus?.(error.message, true);
    setComposerBusy(false);
    return;
  }
  try {
    // A QA tester turns "test example.com" into a plan card; anything else carries on below.
    if (await planRequest(agentState.prism, agentState.activeThread.id, content)) {
      await refreshMessages();
      clearPendingSubmission();
      renderStream({ scroll: "bottom" });
      setComposerBusy(false);
      input.focus();
      return;
    }
    // Small talk ("hi", "thanks") never needs Teams, so Prism just answers.
    const chat = await agentApi(`/api/v2/agent/threads/${agentState.activeThread.id}/chat-reply`, { method: "POST", body: JSON.stringify({ content }) });
    if (chat.handled) {
      await refreshMessages();
      clearPendingSubmission();
      renderStream({ scroll: "bottom" });
      setComposerBusy(false);
      input.focus();
      return;
    }
    updatePendingSubmission(agentState.activeThread.source_external_id
      ? "Reading the selected Teams chat…"
      : "Auto-selecting the relevant Teams chats…");
    await createAndRunMessage(content, null);
  } catch (error) {
    if (agentState.pendingSubmission) {
      clearPendingSubmission();
      input.value = content;
      input.dispatchEvent(new Event("input"));
      renderStream({ scroll: "bottom" });
    }
    ui().setStatus?.(error.message, true);
    showComposerFailure(error);
  } finally {
    setComposerBusy(false);
    input.focus();
  }
}

async function createAndRunMessage(content, sourceExternalId, request = null) {
  const input = $("#agent-message-input");
  const job = await agentApi(request?.path || `/api/v2/agent/threads/${agentState.activeThread.id}/messages`, {
    method: "POST",
    body: JSON.stringify(request?.body || { content, source_external_id: sourceExternalId }),
  });
  clearPendingSubmission();
  input.value = "";
  input.dispatchEvent(new Event("input"));
  agentState.jobs.unshift(job);
  agentState.currentJob = job;
  agentState.turns.set(job.id, { job, review: null, evidence: new Map(), error: null });
  const thread = agentState.activeThread;
  agentState.threads = [thread, ...agentState.threads.filter((item) => item.id !== thread.id)];
  renderSidebarThreads();
  await refreshMessages();
  renderStream({ scroll: "bottom" });
  await runJob(job.id);
}

function updateSendState() {
  $("#agent-send-button").disabled = $("#agent-message-input").disabled || !$("#agent-message-input").value.trim();
}

function setComposerBusy(busy) {
  $("#agent-message-input").disabled = busy;
  $("#agent-source-chip").disabled = busy;
  updateSendState();
}

async function runJob(jobId) {
  const threadId = agentState.activeThread?.id;
  let pollTimer;
  try {
    pollTimer = setInterval(() => agentApi(`/api/v2/agent/jobs/${jobId}`).then(updateTurnJob).catch(() => {}), 900);
    const synced = await agentApi(`/api/v2/agent/jobs/${jobId}/evidence/sync`, { method: "POST" });
    const turn = agentState.turns.get(jobId);
    if (turn) turn.evidence = new Map(synced.evidence.map((item) => [item.id, item]));
    const review = await agentApi(`/api/v2/agent/jobs/${jobId}/review`, { method: "POST" });
    if (turn) turn.review = review;
    clearInterval(pollTimer);
    if (agentState.activeThread?.id !== threadId) return;
    await Promise.all([reloadTurn(jobId), refreshMessages()]);
    renderStream({ scroll: "bottom" });
  } catch (error) {
    clearInterval(pollTimer);
    if (agentState.activeThread?.id === threadId) await failTurn(jobId, error);
  } finally {
    clearInterval(pollTimer);
    notifyChanged();
  }
}

async function recoverJob(job) {
  try {
    const recovered = await agentApi(`/api/v2/agent/jobs/${job.id}/recover`, { method: "POST" });
    updateTurnJob(recovered);
    const turn = agentState.turns.get(job.id);
    if (turn) await hydrateTurn(turn);
    await refreshMessages();
    renderStream();
    notifyChanged();
  } catch (error) {
    await failTurn(job.id, error);
  }
}

async function cancelJob(job) {
  try {
    updateTurnJob(await agentApi(`/api/v2/agent/jobs/${job.id}/transition`, {
      method: "POST",
      body: JSON.stringify({ target: "cancelled", expected_version: job.version }),
    }));
  } catch (error) {
    await failTurn(job.id, error);
  }
}

async function retryJob(job, regenerate) {
  try {
    if (regenerate) {
      await agentApi(`/api/v2/agent/jobs/${job.id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ event_type: "regeneration_requested", details: {} }),
      });
    }
    const content = regenerate
      ? `Regenerate the review and proposed reply for this request: ${job.goal}`
      : job.goal;
    const replacement = await agentApi(`/api/v2/agent/threads/${job.thread_id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    agentState.jobs.unshift(replacement);
    agentState.currentJob = replacement;
    agentState.turns.set(replacement.id, { job: replacement, review: null, evidence: new Map(), error: null });
    await refreshMessages();
    renderStream({ scroll: "bottom" });
    await runJob(replacement.id);
  } catch (error) {
    await failTurn(job.id, error);
  }
}

async function reviseProposal(turn, proposal, body) {
  try {
    const revised = await agentApi(`/api/v2/agent/proposals/${proposal.id}/revisions`, {
      method: "POST",
      body: JSON.stringify({ body, reason: "Edited by manager in Agent workspace" }),
    });
    agentState.drafts.delete(proposal.id);
    if (turn.review.action_plan) {
      const action = turn.review.action_plan.actions.find((item) => item.proposal.id === proposal.id);
      if (action) action.proposal = revised;
    } else {
      turn.review.proposal = revised;
    }
    turn.error = null;
    renderStream();
    ui().setStatus?.("Edit saved. Review it, then approve to send.");
  } catch (error) {
    await failTurn(proposal.job_id, error);
  }
}

async function postDecision(proposal, decision, reason) {
  await agentApi(`/api/v2/agent/proposals/${proposal.id}/decision`, {
    method: "POST",
    body: JSON.stringify({
      decision,
      expected_revision: proposal.revision,
      expected_payload_hash: proposal.payload_hash,
      ...(reason ? { reason } : {}),
    }),
  });
}

async function rejectDraft(turn, selectedProposal = null) {
  const proposal = selectedProposal || turn.review.proposal;
  const reason = await ui().askDialog?.({
    title: "Reject this draft?",
    message: "Nothing will be sent. You can ask Prism to regenerate it.",
    confirmLabel: "Reject",
    danger: true,
    field: { label: "Reason (optional)" },
  });
  if (reason === null || reason === undefined) return;
  try {
    await postDecision(proposal, "rejected", String(reason).trim());
    await reloadTurn(proposal.job_id);
    notifyChanged();
  } catch (error) {
    await failTurn(proposal.job_id, error);
  }
}

function requestActionRedraft(proposal) {
  const input = $("#agent-message-input");
  const destination = proposal.destination.label || "the selected Teams chat";
  input.value = `Redraft only the message to ${destination}. Keep the same purpose, but improve this draft: ${proposal.body}`;
  input.dispatchEvent(new Event("input"));
  input.focus();
}

async function approveActionPlan(turn, button) {
  const plan = turn.review.action_plan;
  const pending = plan.actions.filter(({ proposal }) => proposal.state === "pending");
  if (!pending.length || pending.some(({ proposal }) => agentState.drafts.has(proposal.id))) return;
  button.disabled = true;
  button.textContent = "Approving exact drafts…";
  try {
    const approved = await agentApi(`/api/v2/agent/plans/${plan.id}/approve-all`, {
      method: "POST",
      body: JSON.stringify({
        items: pending.map(({ proposal }) => ({
          proposal_id: proposal.id,
          expected_revision: proposal.revision,
          expected_payload_hash: proposal.payload_hash,
        })),
      }),
    });
    turn.review.action_plan = approved;
    renderStream();
    const failures = [];
    for (const { proposal, execution } of approved.actions.sort((left, right) => left.proposal.sequence - right.proposal.sequence)) {
      if (proposal.state !== "approved" || execution) continue;
      try {
        await agentApi(`/api/v2/agent/proposals/${proposal.id}/execution`, { method: "POST" });
      } catch (error) {
        failures.push(`${proposal.destination.label || "Teams action"}: ${error.message}`);
      }
    }
    await Promise.all([reloadTurn(plan.job_id), refreshMessages()]);
    notifyChanged();
    if (failures.length) ui().setStatus?.(`Some actions need attention: ${failures.join(" ")}`, true);
  } catch (error) {
    await failTurn(plan.job_id, error);
  }
}

async function approveAndSend(turn, proposal, button) {
  button.disabled = true;
  button.textContent = "Approving…";
  try {
    await postDecision(proposal, "approved");
    button.textContent = "Sending…";
    await executeProposal(proposal);
  } catch (error) {
    await failTurn(proposal.job_id, error);
    notifyChanged();
  }
}

async function sendApprovedProposal(turn, proposal, button) {
  button.disabled = true;
  button.textContent = "Sending…";
  try {
    await executeProposal(proposal);
  } catch (error) {
    await failTurn(proposal.job_id, error);
    notifyChanged();
  }
}

async function executeProposal(proposal) {
  await agentApi(`/api/v2/agent/proposals/${proposal.id}/execution`, { method: "POST" });
  await Promise.all([reloadTurn(proposal.job_id), refreshMessages()]);
  notifyChanged();
}

/* Search: find anything in the one conversation, then view history at that point. */

function setSearchOpen(open) {
  agentState.search.open = open;
  $("#agent-search-panel").hidden = !open;
  const trigger = $("#agent-search-button");
  trigger.setAttribute("aria-expanded", String(open));
  trigger.classList.toggle("active", open);
  if (open) {
    $("#agent-search-input").focus();
    return;
  }
  agentState.search.token += 1;
  $("#agent-search-input").value = "";
  $("#agent-search-results").replaceChildren();
  trigger.focus();
}

function snippetFor(content, query) {
  const text = String(content).replace(/\s+/g, " ");
  const at = text.toLowerCase().indexOf(query.toLowerCase());
  const start = Math.max(0, at - 50);
  return `${start ? "…" : ""}${text.slice(start, start + 160)}${text.length > start + 160 ? "…" : ""}`;
}

async function runSearch() {
  const thread = agentState.activeThread;
  const query = $("#agent-search-input").value.trim();
  const results = $("#agent-search-results");
  const token = ++agentState.search.token;
  results.replaceChildren();
  if (!thread || query.length < 2) {
    if (query) results.append(textElement("p", "panel-note", "Type at least 2 characters."));
    return;
  }
  results.append(textElement("p", "panel-note", "Searching…"));
  try {
    const found = await agentApi(messagesUrl(thread.id, { q: query, limit: 20 }));
    if (token !== agentState.search.token) return;
    results.replaceChildren();
    if (!found.length) {
      results.append(textElement("p", "panel-note", `No messages match “${query}”.`));
      return;
    }
    const list = textElement("ul", "search-result-list");
    [...found].reverse().forEach((message) => {
      const item = document.createElement("li");
      const button = textElement("button", "search-result");
      button.type = "button";
      button.append(
        textElement("strong", "", message.role === "manager" ? "You" : "Prism"),
        textElement("time", "", formatTime(message.created_at)),
        textElement("span", "", snippetFor(message.content, query)),
      );
      button.addEventListener("click", () => viewHistoryAt(message));
      item.append(button);
      list.append(item);
    });
    results.append(list);
  } catch (error) {
    if (token === agentState.search.token) {
      results.replaceChildren(renderFailure({ code: error.code, message: error.message }));
    }
  }
}

/* Reply preferences: a side drawer, so the chat keeps its full width. ---- */

function setPreferencesOpen(open) {
  if (open) setComputerOpen(false);
  $("#agent-preferences-panel").classList.toggle("open", open);
  $("#agent-chat").classList.toggle("drawer-open", open);
  const trigger = $("#agent-preferences-button");
  trigger.setAttribute("aria-expanded", String(open));
  trigger.classList.toggle("active", open);
  if (open) {
    loadPreferences();
    setDrawerTab("preferences");
    $("#agent-preference-input").focus();
  }
}

// A Prism's instructions live under that Prism; only the old unscoped assistant uses the global list.
const preferencesPath = () => (agentState.prism ? `/api/v2/prisms/${agentState.prism.id}/preferences` : "/api/v2/agent/preferences");

async function loadPreferences({ silent = false } = {}) {
  const owner = agentState.prism?.id || null;
  try {
    const items = await agentApi(preferencesPath());
    if ((agentState.prism?.id || null) !== owner) return;
    agentState.preferences = items;
    agentState.preferencesFor = owner;
    renderPreferences();
  } catch (error) {
    if (!silent) ui().setStatus?.(error.message, true);
  }
}

function renderPreferencesIntro() {
  const name = agentState.prism?.name;
  $("#agent-preferences-intro").textContent = name
    ? `How ${name} should work. These apply to ${name} only, never to your other Prisms.`
    : "Only explicit instructions are remembered. Draft edits stay feedback, not global rules.";
  $("#agent-preference-input").placeholder = name ? `For example: Keep replies short and friendly` : "For example: Keep replies concise and direct";
}

function renderPreferences() {
  const list = $("#agent-preference-list");
  const preferences = agentState.preferences;
  const active = preferences.filter((preference) => preference.is_active).length;
  const count = $("#agent-preferences-count");
  count.textContent = active;
  count.hidden = !active;
  list.replaceChildren();
  list.className = `agent-preference-list${preferences.length ? "" : " empty-state"}`;
  if (!preferences.length) {
    list.textContent = agentState.prism
      ? `No instructions yet. Tell ${agentState.prism.name} how you want it to work.`
      : "No preferences saved yet. Tell Prism how you like to write replies.";
    return;
  }
  preferences.forEach((preference) => {
    const row = textElement("article", `pref-item${preference.is_active ? "" : " inactive"}`);
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "switch";
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-checked", String(preference.is_active));
    toggle.setAttribute("aria-label", `${preference.is_active ? "Disable" : "Enable"} this preference`);
    toggle.addEventListener("click", () => updatePreference(preference, !preference.is_active));
    const copy = textElement("div", "pref-copy");
    copy.append(
      textElement("p", "pref-text", preference.instruction),
      textElement("span", "pref-meta", `${preference.is_active ? "On" : "Paused"} · added ${new Date(preference.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}`),
    );
    const edit = textElement("button", "icon-button small");
    edit.type = "button";
    edit.setAttribute("aria-label", "Edit preference");
    edit.insertAdjacentHTML("afterbegin", EDIT_ICON);
    edit.addEventListener("click", () => editPreference(preference));
    const remove = textElement("button", "icon-button small danger-icon");
    remove.type = "button";
    remove.setAttribute("aria-label", "Delete preference");
    remove.insertAdjacentHTML("afterbegin", TRASH_ICON);
    remove.addEventListener("click", () => deletePreference(preference));
    row.append(toggle, copy, edit, remove);
    list.append(row);
  });
}

const TRASH_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12h10l1-12M9 7V4h6v3"/></svg>';

async function deletePreference(preference) {
  const confirmed = await ui().askDialog?.({ title: "Delete this preference?", message: `Prism will stop following "${preference.instruction}". This can't be undone.`, confirmLabel: "Delete", danger: true });
  if (!confirmed) return;
  try {
    await agentApi(`${preferencesPath()}/${preference.id}`, { method: "DELETE" });
    await loadPreferences();
    ui().setStatus?.("Preference deleted.");
  } catch (error) { ui().setStatus?.(error.message, true); }
}

async function putPreference(preference, changes) {
  try {
    await agentApi(`${preferencesPath()}/${preference.id}`, {
      method: agentState.prism ? "PATCH" : "PUT",
      body: JSON.stringify(agentState.prism
        ? changes
        : { instruction: preference.instruction, scope: preference.scope, is_active: preference.is_active, ...changes }),
    });
    await loadPreferences();
  } catch (error) {
    ui().setStatus?.(error.message, true);
  }
}

const updatePreference = (preference, isActive) => putPreference(preference, { is_active: isActive });

async function editPreference(preference) {
  const instruction = await ui().askDialog?.({
    title: "Edit preference",
    confirmLabel: "Save",
    field: { label: "Instruction", value: preference.instruction },
  });
  if (!instruction?.trim() || instruction.trim() === preference.instruction) return;
  await putPreference(preference, { instruction: instruction.trim() });
}

async function savePreference(event) {
  event.preventDefault();
  const input = $("#agent-preference-input");
  try {
    await agentApi(preferencesPath(), {
      method: "POST",
      body: JSON.stringify(agentState.prism
        ? { instruction: input.value.trim() }
        : { instruction: input.value.trim(), scope: "general" }),
    });
    input.value = "";
    autoGrow(input, 140);
    ui().setStatus?.(agentState.prism ? `Saved. Only ${agentState.prism.name} will follow this.` : "Preference saved. Prism will use it in future drafts.");
    await loadPreferences();
  } catch (error) {
    ui().setStatus?.(error.message, true);
  }
}

/* Wiring. ---------------------------------------------------------------- */

const composerInput = $("#agent-message-input");
composerInput.addEventListener("input", () => {
  autoGrow(composerInput, 200);
  updateSendState();
});
composerInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (composerInput.value.trim()) $("#agent-composer").requestSubmit();
  }
});
$("#agent-composer").addEventListener("submit", submitMessage);
$("#agent-source-chip").addEventListener("click", chooseSource);
// Listing chats is slow on the first call; start it as soon as the user reaches for the picker.
let sourcesWarmed = 0;
["pointerenter", "focus"].forEach((name) => $("#agent-source-chip").addEventListener(name, () => {
  if (Date.now() - sourcesWarmed < 30000) return;
  sourcesWarmed = Date.now();
  agentApi("/api/v2/agent/sources/teams").catch(() => {});
}));
$("#agent-scroll").addEventListener("scroll", updateJumpButton, { passive: true });
// The scrollbar fades in while scrolling and out shortly after.
document.querySelectorAll("#agent-scroll, #prism-scroll").forEach((scroller) => {
  let hideTimer = null;
  scroller.addEventListener("scroll", () => {
    scroller.classList.add("scrolling");
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => scroller.classList.remove("scrolling"), 900);
  }, { passive: true });
});
$("#agent-jump-latest").addEventListener("click", () => {
  const scroller = $("#agent-scroll");
  scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" });
});
// Settings tabs live in the right drawer. Prism management stays with the Prism list; rows just trigger those actions.
function setDrawerTab(name) {
  document.querySelectorAll("[data-drawer-tab]").forEach((tab) => {
    const active = tab.dataset.drawerTab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-drawer-panel]").forEach((panel) => { panel.hidden = panel.dataset.drawerPanel !== name; });
  $("#agent-archive-confirm").hidden = true;
  if (name === "profile" && agentState.prism) loadProfile();
  if (name === "scope" && agentState.prism) document.dispatchEvent(new CustomEvent("prism:scope-open"));
  if (name === "people" && agentState.prism) document.dispatchEvent(new CustomEvent("prism:people-open", { detail: { prismId: agentState.prism.id, prismName: agentState.prism.name } }));
}

// Edit profile happens right here in the drawer: name, description, and notifications.
let profileSetting = null;
let profileColor = null;
function renderProfileColor() {
  $("#agent-drawer-avatar").replaceChildren(prismLogo(profileColor, "prism-logo"));
  $("#agent-profile-colors").replaceChildren(colorPicker(profileColor, (key) => {
    profileColor = key;
    renderProfileColor();
    $("#agent-profile-save").disabled = !profileDirty();
  }, "agent-profile-color"));
}
async function loadProfile() {
  const prism = agentState.prism;
  profileColor = prismColorKey(prism);
  renderProfileColor();
  $("#agent-profile-name").value = prism.name;
  $("#agent-profile-description").value = prism.description || "";
  $("#agent-profile-error").hidden = true;
  $("#agent-profile-logins").hidden = !computersEnabled();
  document.querySelectorAll('input[name="agent-profile-logins"]').forEach((input) => { input.checked = input.value === (prism.logins_policy || "never"); });
  const archived = String(prism.state).toLowerCase() === "archived";
  ["#agent-profile-name", "#agent-profile-description", "#agent-profile-notify"].forEach((id) => { $(id).disabled = archived; });
  try {
    profileSetting = await agentApi(`/api/v2/prisms/${prism.id}/notification-settings`);
    if (agentState.prism?.id === prism.id) $("#agent-profile-notify").checked = profileSetting.enabled;
  } catch { profileSetting = null; }
  $("#agent-profile-save").disabled = true;
}
const profileLogins = () => document.querySelector('input[name="agent-profile-logins"]:checked')?.value || "never";
function profileDirty() {
  const prism = agentState.prism;
  return profileColor !== prismColorKey(prism)
    || $("#agent-profile-name").value.trim() !== prism.name
    || $("#agent-profile-description").value.trim() !== (prism.description || "")
    || (!$("#agent-profile-logins").hidden && profileLogins() !== (prism.logins_policy || "never"))
    || Boolean(profileSetting && $("#agent-profile-notify").checked !== profileSetting.enabled);
}
document.querySelectorAll('input[name="agent-profile-logins"]').forEach((input) => input.addEventListener("change", () => { $("#agent-profile-save").disabled = !profileDirty(); }));
["#agent-profile-name", "#agent-profile-description", "#agent-profile-notify"].forEach((id) => {
  $(id).addEventListener("input", () => { $("#agent-profile-save").disabled = !profileDirty(); });
});
$("#agent-profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const prism = agentState.prism;
  const save = $("#agent-profile-save");
  const error = $("#agent-profile-error");
  error.hidden = true;
  save.disabled = true;
  try {
    const name = $("#agent-profile-name").value.trim();
    const description = $("#agent-profile-description").value.trim();
    if (name !== prism.name || description !== (prism.description || "") || profileColor !== prismColorKey(prism)) {
      const updated = await agentApi(`/api/v2/prisms/${prism.id}`, { method: "PATCH", body: JSON.stringify({ name, description, color: profileColor, expected_lifecycle_version: prism.lifecycle_version }) });
      Object.assign(agentState.prism, updated);
      document.dispatchEvent(new CustomEvent("prism:prism-updated", { detail: { prism: updated } }));
    }
    if (!$("#agent-profile-logins").hidden && profileLogins() !== (prism.logins_policy || "never")) {
      const updated = await agentApi(`/api/v2/prisms/${prism.id}/profile`, { method: "PATCH", body: JSON.stringify({ logins_policy: profileLogins() }) });
      Object.assign(agentState.prism, updated);
      document.dispatchEvent(new CustomEvent("prism:prism-updated", { detail: { prism: updated } }));
    }
    const notify = $("#agent-profile-notify").checked;
    if (profileSetting && notify !== profileSetting.enabled) {
      if (notify && "Notification" in window && Notification.permission === "default") await Notification.requestPermission();
      profileSetting = await agentApi(`/api/v2/prisms/${prism.id}/notification-settings`, { method: "PUT", body: JSON.stringify({ enabled: notify, min_urgency: profileSetting.min_urgency }) });
    }
    renderHeader();
    ui().setStatus?.("Profile saved.");
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally { save.disabled = !profileDirty(); }
});
document.querySelectorAll("[data-drawer-tab]").forEach((tab) => tab.addEventListener("click", () => setDrawerTab(tab.dataset.drawerTab)));
// Archiving is confirmed right here in the drawer, not in another popup.
$("#agent-archive-start").addEventListener("click", () => { $("#agent-archive-confirm").hidden = false; $("#agent-archive-yes").focus(); });
$("#agent-archive-cancel").addEventListener("click", () => { $("#agent-archive-confirm").hidden = true; });
$("#agent-archive-yes").addEventListener("click", () => {
  if (!agentState.prism) return;
  setPreferencesOpen(false);
  document.dispatchEvent(new CustomEvent("prism:archive-confirmed", { detail: { id: agentState.prism.id } }));
});
$("#agent-preferences-panel").addEventListener("click", (event) => {
  const item = event.target.closest("[data-prism-action]");
  if (!item) return;
  setPreferencesOpen(false);
  document.getElementById(item.dataset.prismAction)?.click();
});
document.addEventListener("prism:open-agent", (event) => openPrism(event.detail.prism));
initQa({ refreshMessages, renderStream, setStatus: (message, isError) => ui().setStatus?.(message, isError) });
document.addEventListener("prism:computer-opened", () => setPreferencesOpen(false));
// New unread updates for the open Prism arrive through the shared poller; reopening the tab marks them read.
document.addEventListener("prism:updates", (event) => {
  const current = agentState.prism && event.detail.summaries.get(agentState.prism.id);
  if (current?.unread) loadUpdates();
});
document.addEventListener("prism:tab", (event) => { if (event.detail?.tab === "agent" || event.detail === "agent") loadUpdates(); });
$("#agent-source-search").addEventListener("input", (event) => renderSources(event.target.value));
let searchTimer;
$("#agent-search-button").addEventListener("click", () => setSearchOpen(!agentState.search.open));
$("#agent-search-input").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 250);
});
$("#agent-search-input").addEventListener("keydown", (event) => {
  if (event.key === "Escape") setSearchOpen(false);
});
$("#agent-preferences-button").addEventListener("click", () => setPreferencesOpen(!$("#agent-preferences-panel").classList.contains("open")));
$("#agent-preferences-close").addEventListener("click", () => setPreferencesOpen(false));
$("#agent-preference-form").addEventListener("submit", savePreference);
$("#agent-preference-input").addEventListener("input", (event) => autoGrow(event.target, 140));
$("#agent-preference-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("#agent-preference-form").requestSubmit();
  }
});
document.addEventListener("prism:new-chat", newChat);
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-agent-new]")) newChat();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("#agent-preferences-panel").classList.contains("open") && !document.querySelector("dialog[open]")) setPreferencesOpen(false);
});

updateSendState();

// v2.2 migrates the original Assistant conversation into the Executive
// Assistant Prism. Waiting for the feature decision avoids creating a second,
// empty legacy conversation during page startup.
let agentWorkspaceStarted = false;
function startLegacyWorkspace() {
  if (agentWorkspaceStarted) return;
  agentWorkspaceStarted = true;
  loadThreads();
}
document.addEventListener("prism:v22-mode", (event) => {
  // With v2.2 on, the page always shows a Prism's own thread (openPrism).
  if (!event.detail.enabled) startLegacyWorkspace();
});
// Without a selected Prism the original conversation (and its approval cards) must still reload after a refresh.
document.addEventListener("prism:no-prism-selected", startLegacyWorkspace);
if (ui().isV22Enabled?.() === false) startLegacyWorkspace();
loadPreferences({ silent: true });
