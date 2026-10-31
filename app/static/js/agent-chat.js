import { agentApi } from "./api.js";

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
  const head = textElement("div", "turn-head");
  head.append(textElement("strong", "", "Prism"), textElement("span", `tag ${URGENCY_TONES[item.urgency] || "blue"}`, `${item.urgency[0].toUpperCase()}${item.urgency.slice(1)} urgency`));
  if (!item.read_at) head.append(textElement("span", "tag purple", "New"));
  if (item.state !== "open") head.append(textElement("span", "tag green", item.state === "resolved" ? "Resolved" : "Superseded"));
  head.append(textElement("time", "", formatTime(item.created_at)));
  body.append(head, textElement("p", "review-summary", item.summary));
  const meta = textElement("div", "chips");
  meta.append(textElement("span", "tag blue", SIGNAL_LABELS[item.signal_type] || "Update"), confidenceTag(item.confidence));
  if (item.source_label) meta.append(textElement("span", "tag gray", item.source_label));
  body.append(meta);
  const facts = item.verified_facts.length ? reviewSection("What Teams shows", item.verified_facts.length, item.verified_facts.map((fact) => textElement("p", "", fact))) : null;
  if (facts) body.append(facts);
  if (item.inference) body.append(textElement("p", "update-inference", `Inference, not a verified fact: ${item.inference}`));
  body.append(textElement("p", "update-why", `Why it matters: ${item.why_it_matters}`), textElement("p", "update-next", `Suggested next step: ${item.suggested_next_step}`));
  if (item.unknowns.length) {
    const limits = textElement("details", "limitations");
    limits.append(textElement("summary", "", "What Prism could not verify"));
    const list = document.createElement("ul");
    item.unknowns.forEach((unknown) => list.append(textElement("li", "", unknown)));
    limits.append(list);
    body.append(limits);
  }
  if (item.state === "open") body.append(actionButton("Prepare a Teams draft", "mini-button", () => draftFromUpdate(item)));
  body.append(renderFeedback(item));
  body.append(renderIncidentHistory(item));
  body.append(textElement("p", "turn-meta", "Recommendation only. Nothing was sent."));
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
function renderFeedback(item) {
  const row = textElement("div", "update-feedback");
  row.append(textElement("span", "turn-meta", "Was this useful?"));
  const selected = new Set(item.feedback_kinds || []);
  Object.entries(FEEDBACK_LABELS).forEach(([kind, label]) => {
    const button = actionButton(label, `mini-button feedback${selected.has(kind) ? " selected" : ""}`, async () => {
      try {
        const result = await agentApi(`/api/v2/prisms/${item.prism_id}/observations/${item.id}/feedback`, { method: "POST", body: JSON.stringify({ kind }) });
        item.feedback_kinds = result.feedback_kinds;
        row.querySelectorAll("button.feedback").forEach((node) => node.classList.toggle("selected", result.feedback_kinds.includes(node.dataset.kind)));
        ui().setStatus?.("Thanks. Noted for this Prism only.");
      } catch (error) { ui().setStatus?.(error.message, true); }
    });
    button.dataset.kind = kind;
    button.setAttribute("aria-pressed", String(selected.has(kind)));
    row.append(button);
  });
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
  $("#agent-prism-menu-wrap").hidden = !agentState.prism;
  $("#agent-source-label").textContent = !thread
    ? (agentState.prism ? "Private conversation" : "Your manager agent")
    : label
      ? (participants.length ? `Source constraint · ${participants.slice(0, 4).join(", ")}${participants.length > 4 ? ` +${participants.length - 4}` : ""}` : `Source constraint · ${label}`)
      : (agentState.prism ? "Private conversation" : "Your manager agent");
  $("#agent-source-chip-label").textContent = label ? `Only ${label}` : "Auto";
  $("#agent-source-chip").title = label
    ? "Requests are limited to this chat. Choose Auto to let Prism pick and disclose sources."
    : "Auto: Prism picks the relevant Teams chats and shows what it read. Choose one to limit requests.";
  $("#agent-source-chip").classList.toggle("empty", !label);
  $("#agent-message-input").placeholder = label
    ? `Ask Prism about ${label}…`
    : "Ask Prism about your team’s work…";
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
  // Oldest first, so each update sits between the messages around the time it was found.
  const updates = [...agentState.updates].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  const flushUpdates = (before) => {
    while (updates.length && (!before || new Date(updates[0].created_at) <= new Date(before))) timeline.append(renderUpdate(updates.shift()));
  };
  messages.forEach((message) => {
    flushUpdates(message.created_at);
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
    timeline.append(renderUserMessage({
      id: "pending-submission",
      content: pending.content,
      created_at: pending.createdAt,
    }));
    const { article, body } = assistantShell("working pending-submission");
    const progress = textElement("div", "progress-title");
    progress.setAttribute("role", "status");
    progress.setAttribute("aria-live", "polite");
    progress.append(textElement("span", "spinner"), textElement("strong", "", pending.label));
    body.append(progress);
    timeline.append(article);
  }
  timeline.querySelectorAll("textarea.autogrow").forEach((textarea) => autoGrow(textarea));
  if (scroll === "keep") return;
  scroller.scrollTop = scroll === "bottom" || (scroll === "auto" && nearBottom) ? scroller.scrollHeight : previousTop;
}

function dayLabel(value) {
  const date = new Date(value);
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(date).setHours(0, 0, 0, 0)) / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric", year: days > 300 ? "numeric" : undefined });
}

const scopeKey = (job) => `${job?.scope_mode || ""}:${(job?.sources || []).map((source) => source.external_id).sort().join(",")}`;

// A separator appears when the day changes or Prism starts working from a different source set.
function renderTopicSeparator(message, previous) {
  const job = agentState.turns.get(message.job_id)?.job;
  const newDay = !previous || dayLabel(previous.created_at) !== dayLabel(message.created_at);
  const previousJob = previous && agentState.turns.get(previous.job_id)?.job;
  const newTopic = Boolean(previous && job?.sources?.length && previousJob?.sources?.length && scopeKey(job) !== scopeKey(previousJob));
  if (!newDay && !newTopic) return null;
  const separator = textElement("div", "topic-separator");
  separator.setAttribute("role", "separator");
  const parts = [];
  if (newDay) parts.push(dayLabel(message.created_at));
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

function renderWelcome() {
  const thread = agentState.activeThread;
  const label = thread?.source_label;
  const welcome = textElement("div", "agent-welcome");
  welcome.append(textElement("span", "welcome-mark", (agentState.prism?.name || "P").trim().charAt(0).toUpperCase()));
  if (!label) {
    welcome.append(
      textElement("h2", "", agentState.prism ? `Talk to your ${agentState.prism.name} Prism` : "Talk to your manager agent"),
      textElement("p", "", agentState.prism?.description || "Ask naturally and Prism will disclose which Teams chats it reads. Use the chat selector in the message box to limit a request to one chat."),
    );
    const steps = textElement("ol", "welcome-steps");
    ["Ask naturally and Auto will choose relevant chats", "Select a chat only when you want a hard one-chat limit", "Check the evidence and approve only actions you requested"].forEach((step) => steps.append(textElement("li", "", step)));
    welcome.append(steps);
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

function renderAssistantMessage(message) {
  const turn = agentState.turns.get(message.job_id);
  if (turn?.review && message.message_metadata?.kind === "conversation_review") return renderReviewTurn(turn);
  const { article, body } = assistantShell();
  const head = textElement("div", "turn-head");
  head.append(textElement("strong", "", "Prism"), textElement("time", "", formatTime(message.created_at)));
  body.append(head, textElement("p", "review-summary", message.content));
  return article;
}

/* A review: summary, what needs attention, a draft reply, and the audit trail. */

function confidenceTag(confidence) {
  const [label, tone] = confidence >= 0.75 ? ["High confidence", "green"] : confidence >= 0.5 ? ["Medium confidence", "yellow"] : ["Low confidence", "orange"];
  const tag = textElement("span", `tag ${tone}`, label);
  tag.title = `${Math.round(confidence * 100)}%`;
  return tag;
}

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
  const head = textElement("div", "turn-head");
  head.append(textElement("strong", "", "Prism"), confidenceTag(review.confidence));
  if (turn.evidence.size) head.append(textElement("span", "turn-meta", `Read ${turn.evidence.size} message${turn.evidence.size === 1 ? "" : "s"}`));
  head.append(textElement("time", "", formatTime(review.created_at)));
  body.append(head, textElement("p", "review-summary", review.summary));
  body.append(renderSourceDisclosure(job));
  appendEvidence(body, turn, review.summary_evidence_ids);
  if (review.attention_items.length) {
    body.append(reviewSection("Needs your attention", review.attention_items.length,
      review.attention_items.map((item) => renderFinding(turn, item.kind || "direct", item.title, item.detail, item.evidence_ids))));
  }
  if (review.manager_questions.length) {
    body.append(reviewSection("Questions for you", review.manager_questions.length,
      review.manager_questions.map((item) => renderFinding(turn, "question", item.question, "", item.evidence_ids))));
  }
  if (review.limitations?.length) {
    const limits = textElement("details", "limitations");
    limits.append(textElement("summary", "", "What Prism could not verify"));
    const list = document.createElement("ul");
    review.limitations.forEach((limit) => list.append(textElement("li", "", limit)));
    limits.append(list);
    body.append(limits);
  }
  if (review.action_plan) {
    body.append(renderActionPlan(turn));
  } else if (review.proposal) {
    body.append(renderDraft(turn));
  } else if (!review.requires_reply) {
    const callout = textElement("div", "callout quiet");
    const calloutBody = textElement("div", "callout-body");
    const multipleSources = (job.sources || []).length > 1;
    calloutBody.append(
      textElement("strong", "", "Information only"),
      textElement("p", "", multipleSources
        ? "No Teams message was drafted. Name one destination if you want Prism to prepare a follow-up."
        : "No Teams message was drafted for this response."),
    );
    if (!multipleSources && (review.attention_items.length || review.manager_questions.length)) {
      calloutBody.append(actionButton("Draft a follow-up", "mini-button", () => draftFollowUp(job)));
    }
    callout.append(textElement("span", "callout-icon", "✓"), calloutBody);
    body.append(callout);
  }
  body.append(renderTurnFooter(turn));
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
  const head = textElement("div", "action-plan-head");
  const title = textElement("div", "");
  title.append(
    textElement("span", "tag purple", "Coordinated plan"),
    textElement("h3", "", plan.summary),
    textElement("p", "panel-note", `${plan.actions.length} independently controlled Teams action${plan.actions.length === 1 ? "" : "s"}.`),
  );
  head.append(title, textElement("span", `tag ${plan.state.includes("failed") ? "red" : plan.state === "completed" ? "green" : "orange"}`, humanize(plan.state)));
  section.append(head);

  const pending = plan.actions.filter(({ proposal }) => proposal.state === "pending");
  if (pending.length > 1) {
    const bulk = actionButton(`Approve all ${pending.length} visible drafts`, "button secondary", (event) => approveActionPlan(turn, event.currentTarget));
    bulk.disabled = pending.some(({ proposal }) => agentState.drafts.has(proposal.id));
    const notice = textElement("div", "action-plan-bulk");
    notice.append(
      textElement("span", "panel-note", "Bulk approval covers only the exact recipients and text shown below."),
      bulk,
    );
    section.append(notice);
  }
  plan.actions.forEach(({ proposal, execution }, index) => {
    const wrapper = textElement("div", "planned-action");
    wrapper.append(textElement("div", "planned-action-order", `Action ${index + 1}${proposal.depends_on_logical_action_ids?.length ? " · waits for a previous action" : ""}`));
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
  const destination = textElement("span", "draft-dest", "To ");
  destination.append(textElement("strong", "", proposal.destination.label || "the selected Teams chat"), " from your Teams account");
  head.append(textElement("span", "tag blue", "Draft reply"), destination, textElement("span", `tag ${state.tone}`, state.label));
  // No stored Teams messages back this draft; say so instead of implying evidence.
  if (!proposal.evidence_ids?.length) {
    const basis = textElement("span", "tag purple", "Based on your instruction");
    basis.title = "No Teams messages were available, so this draft cites none. Check it carefully before approving.";
    head.insertBefore(basis, head.children[1]);
  }
  card.append(head);

  const textarea = document.createElement("textarea");
  textarea.className = "draft-body autogrow";
  textarea.rows = 2;
  textarea.setAttribute("aria-label", "Reply that will be sent to Teams");
  textarea.value = agentState.drafts.get(proposal.id) ?? proposal.body;
  textarea.readOnly = proposal.state !== "pending";
  card.append(textarea);

  const why = textElement("details", "draft-why");
  why.append(textElement("summary", "", "Why this reply"), textElement("p", "", proposal.reason));
  card.append(why);
  appendEvidence(card, turn, proposal.evidence_ids, "Evidence for this reply");

  if (review.applied_preferences?.length) {
    const used = textElement("div", "pref-used");
    used.append(textElement("span", "pref-label", "Shaped by your preferences"));
    review.applied_preferences.forEach((item) => {
      const chip = textElement("span", "pref-chip", item.instruction);
      chip.title = item.instruction;
      used.append(chip);
    });
    used.append(actionButton("Manage", "link-button", () => setPreferencesOpen(true)));
    card.append(used);
  }

  const status = textElement("p", `draft-status ${state.tone}`, draftStatusText(proposal, execution));
  card.append(status);

  if (proposal.state === "pending") {
    const actions = textElement("div", "draft-actions");
    const reject = actionButton("Reject", "button secondary", () => rejectDraft(turn, proposal));
    const regenerate = actionButton("Redraft", "button secondary", () => requestActionRedraft(proposal));
    const save = actionButton("Save edit", "button secondary", () => reviseProposal(turn, proposal, textarea.value));
    const approve = actionButton("Approve and send", "button", () => approveAndSend(turn, proposal, approve));
    actions.append(reject, regenerate, textElement("span", "spacer"), save, approve);
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
    } else if (["rejected", "expired", "failed"].includes(proposal.state) || ["failed"].includes(execution?.state)) {
      actions.append(textElement("span", "spacer"), actionButton("Regenerate", "button secondary", () => retryJob(job, true)));
    }
    if (actions.children.length) card.append(actions);
  }
  return card;
}

function renderTurnFooter(turn) {
  const { job } = turn;
  const footer = textElement("div", "turn-footer");
  if (turn.error) footer.append(renderFailure({ code: turn.errorCode, message: turn.error }));
  if (job.state === "executing") footer.append(actionButton("Check interrupted delivery", "mini-button", () => recoverJob(job)));
  if (["failed", "cancelled"].includes(job.state)) footer.append(actionButton("Retry", "mini-button", () => retryJob(job, false)));
  footer.append(renderAudit(turn));
  return footer;
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
  const title = textElement("div", "progress-title");
  if (ACTIVE_JOB_STATES.includes(job.state) || job.state === "executing") title.append(textElement("span", "spinner"));
  title.append(textElement("strong", "", PROGRESS_LABELS[job.state] || humanize(job.state)));
  body.append(title);
  body.append(renderSourcePlan(job, true));
  if (job.steps.length) {
    const steps = textElement("ul", "step-list");
    job.steps.forEach((step) => steps.append(textElement("li", `step ${step.state}`, step.label)));
    body.append(steps);
  }
  if (job.safe_error_detail) body.append(renderFailure({ code: job.safe_error_code, message: job.safe_error_detail }));
  if (turn.error && !job.safe_error_detail) body.append(renderFailure({ code: turn.errorCode, message: turn.error }));
  const controls = textElement("div", "item-actions");
  if (ACTIVE_JOB_STATES.includes(job.state)) {
    controls.append(actionButton("Cancel", "mini-button", () => cancelJob(job)), actionButton("Resume", "mini-button", () => recoverJob(job)));
  }
  if (job.state === "executing") controls.append(actionButton("Check interrupted delivery", "mini-button", () => recoverJob(job)));
  if (["failed", "cancelled"].includes(job.state)) controls.append(actionButton("Retry", "mini-button", () => retryJob(job, false)));
  if (controls.children.length) body.append(controls);
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
  $("#agent-source-dialog-note").textContent = "Auto resolves every request without a picker. Choose one chat only to apply a hard constraint.";
  search.value = "";
  $("#agent-source-list").className = "agent-source-list empty-state";
  $("#agent-source-list").textContent = "Loading chats…";
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
    copy.append(textElement("strong", "", "Auto"), textElement("span", "", "Resolve the relevant Teams chat from each request"));
    auto.append(avatarFor("Auto"), copy);
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
    option.addEventListener("click", () => selectSource(source));
    list.append(option);
  });
}

async function clearSourceConstraint() {
  const thread = agentState.activeThread;
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
  }
}

async function selectSource(source) {
  const thread = agentState.activeThread;
  if (thread.source_external_id && thread.source_external_id !== source.external_id && agentState.jobs.length) {
    const confirmed = await ui().askDialog?.({
      title: "Change the Teams chat?",
      message: "Future reviews in this Prism conversation will use the new source constraint. Existing reviews keep their original source.",
      confirmLabel: "Change constraint",
    });
    if (confirmed === null) return;
  }
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
  $("#agent-preferences-panel").classList.toggle("open", open);
  const trigger = $("#agent-preferences-button");
  trigger.setAttribute("aria-expanded", String(open));
  trigger.classList.toggle("active", open);
  if (open) {
    loadPreferences();
    $("#agent-preference-input").focus();
  }
}

async function loadPreferences({ silent = false } = {}) {
  try {
    agentState.preferences = await agentApi("/api/v2/agent/preferences");
    renderPreferences();
  } catch (error) {
    if (!silent) ui().setStatus?.(error.message, true);
  }
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
    list.textContent = "No preferences saved yet. Tell Prism how you like to write replies.";
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
      textElement("span", "pref-meta", `${preference.scope === "general" ? "All Teams drafts" : "One chat"} · ${humanize(preference.source_kind)}`),
    );
    const edit = textElement("button", "icon-button small");
    edit.type = "button";
    edit.setAttribute("aria-label", "Edit preference");
    edit.insertAdjacentHTML("afterbegin", EDIT_ICON);
    edit.addEventListener("click", () => editPreference(preference));
    row.append(toggle, copy, edit);
    list.append(row);
  });
}

async function putPreference(preference, changes) {
  try {
    await agentApi(`/api/v2/agent/preferences/${preference.id}`, {
      method: "PUT",
      body: JSON.stringify({
        instruction: preference.instruction,
        scope: preference.scope,
        is_active: preference.is_active,
        ...changes,
      }),
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
  const scope = $("#agent-preference-scope").value;
  try {
    await agentApi("/api/v2/agent/preferences", {
      method: "POST",
      body: JSON.stringify({
        instruction: input.value.trim(),
        scope,
        source_thread_id: scope === "teams_chat" ? agentState.activeThread?.id : null,
      }),
    });
    input.value = "";
    ui().setStatus?.("Preference saved. Prism will use it in future drafts.");
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
function setPrismMenu(open) {
  const menu = $("#agent-prism-menu");
  menu.hidden = !open;
  $("#agent-prism-menu-button").setAttribute("aria-expanded", String(open));
  if (open) menu.querySelector(".menu-item")?.focus();
}
$("#agent-prism-menu-button").addEventListener("click", (event) => { event.stopPropagation(); setPrismMenu($("#agent-prism-menu").hidden); });
// Prism management lives with the Prism list; the menu just triggers those actions.
$("#agent-prism-menu").addEventListener("click", (event) => {
  const item = event.target.closest("[data-prism-action]");
  if (!item) return;
  setPrismMenu(false);
  document.getElementById(item.dataset.prismAction)?.click();
});
document.addEventListener("click", (event) => { if (!event.target.closest("#agent-prism-menu-wrap")) setPrismMenu(false); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !$("#agent-prism-menu").hidden) setPrismMenu(false); });
document.addEventListener("prism:open-agent", (event) => openPrism(event.detail.prism));
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
