import { agentApi } from "./api.js";

/* Prism plan cards, live computer panel, approvals and task reports (including QA).
   Everything here talks to Prism only; the testing workspace behind it is never named. */

const $ = (selector) => document.querySelector(selector);
const operatorTokenKey = "manager-agent-operator-token";
const STATE_TEXT = {
  planned: "Waiting for you to start",
  starting: "Getting ready",
  running: "Testing",
  waiting_approval: "Waiting for you",
  succeeded: "Finished",
  failed: "Stopped with a problem",
  cancelled: "Stopped",
  timed_out: "Ran out of time",
  error: "Couldn't run",
};
const STATUS_TEXT = { pass: "Passed", fail: "Failed", blocked: "Couldn't check", skipped: "Skipped", pending: "Not run" };
const STATUS_TONE = { pass: "green", fail: "red", blocked: "orange", skipped: "gray", pending: "gray" };
const SEVERITY_TONE = { critical: "red", high: "red", medium: "orange", low: "gray" };

const state = {
  host: null, // helpers from agent-chat.js
  prism: null,
  runs: new Map(), // run id -> latest snapshot
  order: [], // run ids for the open Prism, newest first
  focus: null, // run shown in the computer panel
  streams: new Map(), // run id -> AbortController
  keys: new Map(), // run id -> what chat cards depend on
  open: false,
  available: null,
  planEdits: new Set(), // runs whose plan is open for editing
  edits: new Map(), // run id -> changes to send when the test starts
  screens: new Map(), // "run:n" -> blob url
  frames: new Map(), // run id -> { n, url } the newest live view of the screen
  frameLoading: new Set(),
  computers: false, // v2.4: every Prism has a computer
  computer: null, // { state, reason } for the open Prism
  logins: [],
  timer: null,
};

const isActive = (run) => Boolean(run?.active);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function chip(text, tone = "gray") {
  return el("span", `qa-chip tag-${tone}`, text);
}

function button(label, className, onClick) {
  const node = el("button", className, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

export const isQaPrism = (prism) => prism?.template_key === "qa_tester";
export const computersEnabled = () => state.computers;
const usesComputer = (prism) => Boolean(prism) && (isQaPrism(prism) || state.computers);
const isWork = (run) => run?.kind === "work";
const stateText = (run) => (run.startup_warning ? "Waiting for workspace" : isWork(run) && run.state === "running" ? "Working" : STATE_TEXT[run.state] || run.state);

/* ---------- plumbing ---------- */

function authHeaders() {
  const token = localStorage.getItem(operatorTokenKey);
  return token ? { "X-Manager-Operator-Token": token } : {};
}

async function screenUrl(runId, index) {
  const key = `${runId}:${index}`;
  if (state.screens.has(key)) return state.screens.get(key);
  const response = await fetch(`/api/v2/qa/runs/${runId}/screens/${index}`, { headers: authHeaders() });
  if (!response.ok) throw new Error("screenshot unavailable");
  const url = URL.createObjectURL(await response.blob());
  state.screens.set(key, url);
  return url;
}

function elapsed(run) {
  if (!run?.started_at) return "";
  const end = run.ended_at ? new Date(run.ended_at) : new Date();
  const seconds = Math.max(0, Math.round((end - new Date(run.started_at)) / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${String(seconds % 60).padStart(2, "0")}s` : `${seconds}s`;
}

const money = (value) => `$${Number(value || 0).toFixed(2)}`;

// What the chat cards show. The live panel updates on every change; the chat only when this changes.
const cardKey = (run) => [run.state, run.startup_warning || "", run.approvals.map((a) => a.status).join(","), run.report ? "r" : "", run.cases?.total || 0].join("|");

function remember(run) {
  state.runs.set(run.id, run);
  const before = state.keys.get(run.id);
  const after = cardKey(run);
  state.keys.set(run.id, after);
  return before !== after;
}

/* ---------- following a run ---------- */

async function follow(runId) {
  if (state.streams.has(runId)) return;
  const controller = new AbortController();
  state.streams.set(runId, controller);
  let delay = 1000;
  try {
    while (!controller.signal.aborted) {
      let ended = false;
      try {
        const response = await fetch(`/api/v2/qa/runs/${runId}/stream`, { headers: authHeaders(), signal: controller.signal });
        if (!response.ok || !response.body) throw new Error("stream unavailable");
        delay = 1000;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let cut;
          while ((cut = buffer.indexOf("\n\n")) >= 0) {
            const block = buffer.slice(0, cut);
            buffer = buffer.slice(cut + 2);
            const name = /^event: (.+)$/m.exec(block)?.[1];
            const data = /^data: (.+)$/m.exec(block)?.[1];
            if (name === "state" && data) await apply(JSON.parse(data));
            if (name === "end") ended = true;
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        // The stream dropped; fall back to a plain read, then try again.
        try { await apply(await agentApi(`/api/v2/qa/runs/${runId}`)); } catch { /* retried below */ }
      }
      if (ended || !isActive(state.runs.get(runId))) break;
      await new Promise((resolve) => setTimeout(resolve, delay));
      delay = Math.min(delay * 2, 8000);
    }
  } finally {
    state.streams.delete(runId);
  }
}

function track(run) {
  if (state.prism && run.prism_id === state.prism.id && !state.order.includes(run.id)) state.order.unshift(run.id);
}

async function apply(run) {
  const changed = remember(run);
  track(run);
  renderPanel();
  updateButton();
  if (changed && state.prism && run.prism_id === state.prism.id) {
    await state.host.refreshMessages();
    state.host.renderStream({ scroll: "auto" });
  }
}

async function loadRuns() {
  if (!usesComputer(state.prism)) return;
  const prismId = state.prism.id;
  try {
    const runs = await agentApi(`/api/v2/prisms/${prismId}/qa/runs`);
    if (state.prism?.id !== prismId) return;
    runs.forEach(remember);
    state.order = runs.map((run) => run.id);
    runs.filter(isActive).forEach((run) => follow(run.id));
    const active = runs.find(isActive);
    if (active && !isActive(state.runs.get(state.focus))) state.focus = active.id;
    else if (!state.focus || !state.runs.has(state.focus)) state.focus = runs[0]?.id || null;
  } catch { /* the panel just shows no runs */ }
  renderPanel();
  updateButton();
}

async function loadRun(runId) {
  if (state.runs.has(runId)) return state.runs.get(runId);
  try {
    const run = await agentApi(`/api/v2/qa/runs/${runId}`);
    remember(run);
    if (isActive(run)) follow(run.id);
    state.host.renderStream({ scroll: "keep" });
    return run;
  } catch { return null; }
}

/* ---------- called by the chat ---------- */

export function initQa(host) {
  state.host = host;
  $("#agent-computer-button").addEventListener("click", () => setOpen(!state.open));
  $("#qa-computer-close").addEventListener("click", () => setOpen(false));
  checkAvailability().then(() => { if (state.computers) onPrism(state.prism, true); });
}

export function onPrism(prism, force = false) {
  const same = state.prism?.id === prism?.id;
  state.prism = prism || null;
  const show = usesComputer(prism);
  $("#agent-computer-button").hidden = !show;
  if (!show) { setOpen(false); return; }
  if (!same || force) {
    stopLive();
    state.order = []; state.focus = null; state.computer = null;
    renderPanel();
    loadRuns();
  }
}

// A computer-enabled Prism's task request becomes a plan card. Returns true when handled.
export async function planRequest(prism, threadId, content) {
  if (!usesComputer(prism)) return false;
  const result = await agentApi(`/api/v2/prisms/${prism.id}/qa/plan`, { method: "POST", body: JSON.stringify({ thread_id: threadId, content }) });
  return Boolean(result.handled);
}

export function setOpen(open) {
  state.open = open && usesComputer(state.prism);
  $("#qa-computer-panel").classList.toggle("open", state.open);
  $("#agent-chat").classList.toggle("computer-open", state.open);
  const trigger = $("#agent-computer-button");
  trigger.setAttribute("aria-expanded", String(state.open));
  trigger.classList.toggle("active", state.open);
  if (state.open) {
    document.dispatchEvent(new CustomEvent("prism:computer-opened"));
    loadRuns();
    loadComputer();
  }
  if (!state.open) stopLive();
  clearInterval(state.timer);
  state.timer = state.open ? setInterval(() => { if (isActive(state.runs.get(state.focus))) renderClock(); }, 1000) : null;
  renderPanel();
}

export async function focusRun(runId) {
  if (!runId || !state.prism) return;
  state.focus = runId;
  if (!state.runs.has(runId)) await loadRun(runId);
  setOpen(true);
  renderPanel();
}

function updateButton() {
  const runs = state.order.map((id) => state.runs.get(id));
  const live = runs.some(isActive);
  const dot = $("#agent-computer-dot");
  dot.hidden = !live;
  dot.classList.toggle("waiting", runs.some((run) => run?.state === "waiting_approval"));
}

async function loadComputer() {
  if (!state.computers || !state.prism) return;
  const prismId = state.prism.id;
  try {
    const [computer, logins] = await Promise.all([agentApi(`/api/v2/prisms/${prismId}/computer`), agentApi(`/api/v2/prisms/${prismId}/logins`)]);
    if (state.prism?.id !== prismId) return;
    state.computer = computer;
    state.logins = logins;
  } catch { /* the panel falls back to the run list */ }
  renderPanel();
}

/* ---------- chat cards ---------- */

function field(label, value) {
  const row = el("p", "qa-fact");
  row.append(el("span", "qa-fact-label", label), el("span", "", value));
  return row;
}

function chipList(items) {
  const list = el("span", "qa-chips");
  items.forEach((item) => list.append(chip(item)));
  return list;
}

function workPlanBody(run) {
  const plan = run.plan || {};
  const body = el("div", "qa-card");
  const head = el("div", "qa-card-head");
  head.append(el("strong", "", plan.title || "Task"));
  body.append(head);
  body.append(field("Steps", ""));
  const steps = el("ol", "qa-criteria");
  (plan.steps || []).forEach((item) => steps.append(el("li", "", item)));
  body.append(steps);
  const sites = [...(plan.sites || []).map((site) => site.replace(/^https?:\/\//, "")), ...(plan.any_public_site ? ["any public website"] : [])];
  body.append(field("Sites", sites.join("  ·  ") || "None"));
  body.append(field("Uses", (plan.uses || []).join("  ·  ")));
  if ((plan.asks_first || []).length) body.append(field("Asks you first", plan.asks_first.join(", ")));
  body.append(field("Limits", `up to ${plan.max_turns} steps · ${money(plan.budget_usd)} · ${plan.max_minutes || 30} min at most`));
  return body;
}

function workEditForm(run, onDone) {
  const plan = run.plan || {};
  const form = el("form", "qa-edit");
  const steps = el("textarea"); steps.rows = 5; steps.value = (plan.steps || []).join("\n");
  const sites = el("textarea"); sites.rows = 2; sites.value = (plan.sites || []).join(", ");
  const anySite = el("input"); anySite.type = "checkbox"; anySite.checked = Boolean(plan.any_public_site);
  const turns = el("input"); turns.type = "number"; turns.min = "5"; turns.max = "150"; turns.value = plan.max_turns;
  const budget = el("input"); budget.type = "number"; budget.min = "0.1"; budget.max = "3"; budget.step = "0.1"; budget.value = plan.budget_usd;
  const label = (text, input) => { const wrap = el("label", "qa-edit-field"); wrap.append(el("span", "", text), input); return wrap; };
  form.append(label("Steps (one per line)", steps), label("Sites I may use (comma separated)", sites));
  const check = label("Any public website, if needed", anySite); check.classList.add("qa-edit-check"); form.append(check);
  form.append(label("Max steps", turns), label("Budget ($)", budget));
  const actions = el("div", "qa-actions");
  const save = el("button", "button", "Save changes"); save.type = "submit";
  actions.append(save, button("Cancel", "button secondary", () => onDone(null)));
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onDone({
      steps: steps.value.split("\n").map((v) => v.trim()).filter(Boolean),
      sites: sites.value.split(",").map((v) => v.trim()).filter(Boolean),
      any_public_site: anySite.checked,
      max_turns: Number(turns.value) || undefined,
      budget_usd: Number(budget.value) || undefined,
    });
  });
  return form;
}

function planBody(run) {
  if (isWork(run)) return workPlanBody(run);
  const plan = run.plan || {};
  const body = el("div", "qa-card");
  const head = el("div", "qa-card-head");
  head.append(el("strong", "", plan.host || "Website test"), chip(plan.environment === "production" ? (plan.discovery_mode === "automatic" ? "Live site · dummy data" : "Live site · read-only") : plan.environment || "", plan.environment === "production" ? "orange" : "gray"));
  body.append(head);
  if (plan.discovery_mode === "automatic") {
    body.append(field("Pages", "Discover pages automatically"));
    body.append(field("Starting pages", (plan.pages || ["/"]).join("  ·  ")));
    body.append(field("Scope", "Internal pages on this site. I'll ask before opening subdomains or other sites."));
    body.append(field("Actions", "Dummy data only. Login and important changes need your approval."));
  } else body.append(field("Pages", (plan.pages || ["/"]).join("  ·  ")));
  body.append(field("Checks", (plan.features || []).join(", ") || "General smoke test"));
  if ((plan.acceptance_criteria || []).length) {
    const list = el("ul", "qa-criteria");
    plan.acceptance_criteria.forEach((item) => list.append(el("li", "", item)));
    body.append(field("Make sure", ""), list);
  }
  body.append(field("Limits", `up to ${plan.max_turns} steps · ${money(plan.budget_usd)} budget`));
  body.append(field("Bug filing", plan.allow_bug_filing ? "On, I'll ask you first" : "Off"));
  return body;
}

function editForm(run, onDone) {
  if (isWork(run)) return workEditForm(run, onDone);
  const plan = run.plan || {};
  const form = el("form", "qa-edit");
  const pages = el("textarea"); pages.rows = 2; pages.value = (plan.pages || []).join(", ");
  const criteria = el("textarea"); criteria.rows = 3; criteria.value = (plan.acceptance_criteria || []).join("\n");
  const turns = el("input"); turns.type = "number"; turns.min = "5"; turns.max = "150"; turns.value = plan.max_turns;
  const budget = el("input"); budget.type = "number"; budget.min = "0.1"; budget.max = "3"; budget.step = "0.1"; budget.value = plan.budget_usd;
  const bugs = el("input"); bugs.type = "checkbox"; bugs.checked = Boolean(plan.allow_bug_filing);
  const label = (text, input) => { const wrap = el("label", "qa-edit-field"); wrap.append(el("span", "", text), input); return wrap; };
  form.append(label(plan.discovery_mode === "automatic" ? "Starting pages (optional; I'll discover the rest)" : "Pages (comma separated)", pages), label("What to make sure of (one per line)", criteria), label("Max steps", turns), label("Budget ($)", budget));
  if (plan.may_file_bugs && plan.environment !== "production") {
    const wrap = label("Let me ask to file bugs", bugs); wrap.classList.add("qa-edit-check"); form.append(wrap);
  }
  const actions = el("div", "qa-actions");
  const save = el("button", "button", "Save changes"); save.type = "submit";
  actions.append(save, button("Cancel", "button secondary", () => onDone(null)));
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onDone({
      pages: pages.value.split(",").map((v) => v.trim()).filter(Boolean),
      acceptance_criteria: criteria.value.split("\n").map((v) => v.trim()).filter(Boolean),
      max_turns: Number(turns.value) || undefined,
      budget_usd: Number(budget.value) || undefined,
      ...(plan.may_file_bugs && plan.environment !== "production" ? { allow_bug_filing: bugs.checked } : {}),
    });
  });
  return form;
}

async function startRun(run, edits, startButton) {
  startButton.disabled = true;
  state.focus = run.id;
  setOpen(true);
  try {
    const started = await agentApi(`/api/v2/qa/runs/${run.id}/start`, { method: "POST", body: JSON.stringify(edits || {}) });
    state.planEdits.delete(run.id);
    state.edits.delete(run.id);
    remember(started);
    track(started);
    state.focus = started.id;
    follow(started.id);
    setOpen(true);
    await state.host.refreshMessages();
    state.host.renderStream({ scroll: "bottom" });
  } catch (error) {
    startButton.disabled = false;
    state.host.setStatus?.(error.message, true);
  }
}

async function cancelRun(run) {
  try {
    const stopped = await agentApi(`/api/v2/qa/runs/${run.id}/cancel`, { method: "POST" });
    await apply(stopped);
  } catch (error) { state.host.setStatus?.(error.message, true); }
}

function renderPlanCard(message) {
  const runId = message.message_metadata?.qa_run_id;
  const run = state.runs.get(runId);
  const holder = el("div", "qa-plan");
  if (!run) { loadRun(runId); holder.append(el("p", "qa-muted", "Loading the plan…")); return holder; }
  holder.append(planBody(run));
  if (run.state === "planned") {
    if (state.planEdits.has(run.id)) {
      holder.append(editForm(run, (edits) => {
        state.planEdits.delete(run.id);
        if (edits) {
          state.edits.set(run.id, edits);
          run.plan = { ...run.plan, ...edits };
        }
        state.host.renderStream({ scroll: "keep" });
      }));
      return holder;
    }
    const actions = el("div", "qa-actions");
    const start = button(isWork(run) ? "Start" : "Start testing", "button", () => startRun(run, state.edits.get(run.id) || {}, start));
    actions.append(start, button("Edit", "button secondary", () => { state.planEdits.add(run.id); state.host.renderStream({ scroll: "keep" }); }), button("Not now", "button ghost", () => cancelRun(run).then(() => state.host.renderStream({ scroll: "keep" }))));
    holder.append(actions);
    return holder;
  }
  const status = el("div", "qa-status");
  status.append(chip(stateText(run), run.state === "succeeded" ? "green" : run.active ? "blue" : "gray"));
  if (run.cases?.total) status.append(el("span", "qa-muted", `${run.cases.total} checks · ${run.cases.pass || 0} passed${run.cases.fail ? ` · ${run.cases.fail} failed` : ""}`));
  if (run.active) status.append(button("Watch", "mini-button", () => { state.focus = run.id; setOpen(true); }), button("Stop", "mini-button", () => cancelRun(run)));
  holder.append(status);
  return holder;
}

async function decideApproval(approval, body, holder) {
  const buttons = holder.querySelectorAll("button");
  buttons.forEach((b) => { b.disabled = true; });
  try { await apply(await agentApi(`/api/v2/qa/approvals/${approval.id}/decision`, { method: "POST", body: JSON.stringify(body) })); }
  catch (error) { buttons.forEach((b) => { b.disabled = false; }); state.host.setStatus?.(error.message, true); }
}

function decidedLine(approval, yes, no) {
  return el("p", "qa-muted", approval.status === "approved" ? yes : no);
}

function outwardCard(run, approval) {
  const holder = el("div", "qa-plan");
  const view = approval.view || {};
  const body = el("div", "qa-card");
  const head = el("div", "qa-card-head");
  head.append(el("strong", "", "Before I go ahead"));
  body.append(head);
  if (view.summary) body.append(field("I'm about to", view.summary));
  if (view.site) body.append(field("Where", view.site));
  if (view.details) body.append(field("Details", view.details));
  if (view.frame && approval.status === "pending") {
    const image = el("img", "qa-thumb wide"); image.alt = "What the screen shows right now";
    frameUrl(run).then((url) => { image.src = url; }).catch(() => image.remove());
    body.append(image);
  }
  holder.append(body);
  if (approval.status === "pending") {
    const actions = el("div", "qa-actions");
    actions.append(button("Allow", "button", () => decideApproval(approval, { decision: "approve" }, holder)), button("Don't", "button secondary", () => decideApproval(approval, { decision: "reject" }, holder)));
    holder.append(actions);
  } else holder.append(decidedLine(approval, "You allowed it.", "You said no, so I didn't do it."));
  return holder;
}

function questionCard(run, approval) {
  const holder = el("div", "qa-plan");
  if (approval.status !== "pending") { holder.append(decidedLine(approval, "You answered.", "You skipped this question.")); return holder; }
  const form = el("form", "qa-edit");
  const answer = el("textarea"); answer.rows = 2; answer.maxLength = 1000; answer.required = true; answer.setAttribute("aria-label", "Your answer");
  const actions = el("div", "qa-actions");
  const send = el("button", "button", "Send answer"); send.type = "submit";
  actions.append(send, button("Skip", "button secondary", () => decideApproval(approval, { decision: "reject" }, holder)));
  form.append(answer, actions);
  form.addEventListener("submit", (event) => { event.preventDefault(); if (answer.value.trim()) decideApproval(approval, { decision: "approve", answer: answer.value }, holder); });
  holder.append(form);
  return holder;
}

function loginCard(run, approval) {
  const holder = el("div", "qa-plan");
  const name = state.prism?.name || "Prism";
  const site = approval.view?.site || "this site";
  const body = el("div", "qa-card");
  const head = el("div", "qa-card-head");
  head.append(el("strong", "", `${name} needs to sign in to ${site.replace(/^https?:\/\//, "")}`));
  body.append(head);
  if (approval.view?.reason) body.append(el("p", "qa-muted", approval.view.reason));
  holder.append(body);
  if (approval.status !== "pending") { holder.append(decidedLine(approval, "You gave a login.", "You skipped signing in.")); return holder; }
  const form = el("form", "qa-edit qa-login");
  form.autocomplete = "off";
  const user = el("input"); user.type = "text"; user.name = "prism-site-username"; user.autocomplete = "off"; user.required = true; user.maxLength = 200;
  const pass = el("input"); pass.type = "password"; pass.name = "prism-site-password"; pass.autocomplete = "new-password"; pass.required = true; pass.maxLength = 500;
  const remember = el("select"); remember.setAttribute("aria-label", "How long to keep it");
  [["true", `Remember for ${name}`], ["false", "Use once, then forget"]].forEach(([value, text]) => { const option = el("option", "", text); option.value = value; remember.append(option); });
  const label = (text, input) => { const wrap = el("label", "qa-edit-field"); wrap.append(el("span", "", text), input); return wrap; };
  form.append(label("Username or email", user), label("Password", pass), label("Keep it", remember));
  form.append(el("p", "qa-muted", `Only ${name}'s computer uses this. It is encrypted, never shown in chat, and never seen by the AI model.`));
  const actions = el("div", "qa-actions");
  const go = el("button", "button", "Sign in"); go.type = "submit";
  actions.append(go, button(`Skip ${site.replace(/^https?:\/\//, "")}`, "button secondary", () => decideApproval(approval, { decision: "reject" }, holder)));
  form.append(actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const login = { username: user.value, password: pass.value, remember: remember.value === "true" };
    pass.value = ""; // the password leaves the page as soon as it is sent
    await decideApproval(approval, { decision: "approve", login }, holder);
    login.password = "";
  });
  holder.append(form);
  return holder;
}

function renderApprovalCard(message) {
  const runId = message.message_metadata?.qa_run_id;
  const approvalId = message.message_metadata?.qa_approval_id;
  const run = state.runs.get(runId);
  const holder = el("div", "qa-plan");
  if (!run) { loadRun(runId); return holder; }
  const approval = run.approvals.find((item) => item.id === approvalId);
  if (!approval) return holder;
  if (approval.kind === "outward_action") return outwardCard(run, approval);
  if (approval.kind === "site_access") return outwardCard(run, approval);
  if (approval.kind === "budget_extension") {
    const view = approval.view || {};
    const card = el("div", "qa-card");
    card.append(el("strong", "", "More pages remain to test"));
    card.append(el("p", "qa-muted", view.reason || "The current testing limits are almost used."));
    card.append(field("New total limits", `${view.max_turns} steps · ${money(view.budget_usd)} total budget`));
    holder.append(card);
    if (approval.status === "pending") {
      const actions = el("div", "qa-actions");
      actions.append(button("Extend and continue", "button", () => decideApproval(approval, { decision: "approve" }, holder)), button("Finish with partial report", "button secondary", () => decideApproval(approval, { decision: "reject" }, holder)));
      holder.append(actions);
    } else holder.append(decidedLine(approval, "You extended the limits.", "You finished with a partial report."));
    return holder;
  }
  if (approval.kind === "question") return questionCard(run, approval);
  if (approval.kind === "login") return loginCard(run, approval);
  const body = el("div", "qa-card");
  const head = el("div", "qa-card-head");
  head.append(el("strong", "", approval.title || "A bug I found"), chip(approval.severity || "medium", SEVERITY_TONE[approval.severity] || "gray"));
  body.append(head);
  if (approval.steps) body.append(field("Steps", approval.steps));
  if (approval.expected) body.append(field("Expected", approval.expected));
  if (approval.actual) body.append(field("Actually", approval.actual));
  holder.append(body);
  if (approval.status === "pending") {
    const actions = el("div", "qa-actions");
    const decide = async (decision) => {
      actions.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      try { await apply(await agentApi(`/api/v2/qa/approvals/${approval.id}/decision`, { method: "POST", body: JSON.stringify({ decision }) })); }
      catch (error) { actions.querySelectorAll("button").forEach((b) => { b.disabled = false; }); state.host.setStatus?.(error.message, true); }
    };
    actions.append(button("File it", "button", () => decide("approve")), button("Don't file", "button secondary", () => decide("reject")));
    holder.append(actions);
  } else {
    holder.append(el("p", "qa-muted", approval.status === "approved" ? "You approved filing this." : "You chose not to file this."));
  }
  return holder;
}

function thumb(runId, index, label) {
  const image = el("img", "qa-thumb");
  image.alt = label || "Screenshot";
  image.loading = "lazy";
  screenUrl(runId, index).then((url) => { image.src = url; }).catch(() => { image.remove(); });
  image.addEventListener("click", () => lightbox(runId, index, label));
  return image;
}

function lightbox(runId, index, label) {
  const dialog = el("dialog", "qa-lightbox");
  const image = el("img"); image.alt = label || "Screenshot";
  screenUrl(runId, index).then((url) => { image.src = url; });
  const close = button("Close", "button secondary", () => dialog.close());
  dialog.append(image, close);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  document.body.append(dialog);
  dialog.showModal();
}

const isLink = (value) => /^https?:\/\/[^\s]+$/i.test(String(value));
function cellNode(value) {
  const text = String(value ?? "");
  if (!isLink(text)) return document.createTextNode(text);
  const link = el("a", "", text.replace(/^https?:\/\//i, ""));
  link.href = text; link.target = "_blank"; link.rel = "noopener noreferrer";
  return link;
}

async function downloadFile(runId, file) {
  try {
    const response = await fetch(`/api/v2/qa/runs/${runId}/files/${file.index}`, { headers: authHeaders() });
    if (!response.ok) throw new Error("unavailable");
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = file.name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch { state.host.setStatus?.("That file isn't available right now.", true); }
}

function renderWorkReport(runId, report) {
  const holder = el("div", "qa-report");
  const summary = el("div", "qa-counts");
  if (report.outcome !== "succeeded") summary.append(chip(STATE_TEXT[report.outcome] || report.outcome, "orange"));
  if (report.row_count) summary.append(chip(`${report.row_count} found`, "green"));
  (report.files || []).forEach((file) => summary.append(button(`Download ${file.name}`, "mini-button file-chip", () => downloadFile(runId, file))));
  holder.append(summary);


  if (report.rows?.length) {
    const wrap = el("div", "qa-table-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", "Results");
    const table = el("table", "qa-table");
    const head = el("tr");
    report.columns.forEach((column) => head.append(el("th", "", column.replace(/[_-]+/g, " "))));
    const thead = el("thead");
    thead.append(head);
    table.append(thead);
    const bodyNode = el("tbody");
    report.rows.forEach((row) => {
      const line = el("tr");
      report.columns.forEach((column) => { const cell = el("td"); cell.append(cellNode(row[column])); line.append(cell); });
      bodyNode.append(line);
    });
    table.append(bodyNode);
    wrap.append(table);
    holder.append(wrap);
  }
  if (report.needs_attention?.length) {
    const section = el("div", "qa-section");
    section.append(el("h4", "", "Needs your attention"));
    const list = el("ul", "qa-criteria");
    report.needs_attention.forEach((item) => list.append(el("li", "", item)));
    section.append(list);
    holder.append(section);
  }
  if (report.next_steps?.length) {
    const section = el("div", "qa-section");
    section.append(el("h4", "", "What I can do next"));
    const list = el("ul", "qa-criteria");
    report.next_steps.forEach((item) => list.append(el("li", "", item)));
    section.append(list);
    holder.append(section);
  }
  const foot = [report.duration_seconds != null ? `${Math.max(1, Math.round(report.duration_seconds / 60))} min` : null, money(report.cost_usd)].filter(Boolean).join(" · ");
  holder.append(el("p", "qa-muted qa-foot", foot));
  return holder;
}

function renderBusy(message) {
  const run = state.runs.get(message.message_metadata?.qa_run_id);
  const holder = el("div", "qa-plan");
  if (!run) { loadRun(message.message_metadata?.qa_run_id); return holder; }
  if (run.active) {
    const actions = el("div", "qa-actions");
    actions.append(button("Watch", "mini-button", () => { state.focus = run.id; setOpen(true); }), button("Stop that task", "mini-button", () => cancelRun(run)));
    holder.append(actions);
  }
  return holder;
}

function renderReport(message) {
  const runId = message.message_metadata?.qa_run_id;
  const run = state.runs.get(runId);
  const holder = el("div", "qa-report");
  if (!run) loadRun(runId);
  const report = run?.report;
  if (!report) return holder;
  if (report.kind === "work") return renderWorkReport(runId, report);
  const counts = report.counts || {};
  const summary = el("div", "qa-counts");
  summary.append(chip(`${counts.pass || 0} passed`, "green"));
  if (counts.fail) summary.append(chip(`${counts.fail} failed`, "red"));
  if (counts.blocked) summary.append(chip(`${counts.blocked} couldn't check`, "orange"));
  if (counts.skipped) summary.append(chip(`${counts.skipped} skipped`, "gray"));
  if (report.bugs?.length) summary.append(chip(`${report.bugs.length} issue${report.bugs.length === 1 ? "" : "s"}`, "red"));
  holder.append(summary);

  if (report.coverage) {
    if (report.partial) holder.append(el("p", "qa-muted", "Partial coverage: some discovered pages remain untested."));
    const coverage = el("details", "qa-cases");
    coverage.append(el("summary", "", `Page coverage (${report.coverage.pages?.length || 0})`));
    (report.coverage.pages || []).forEach((page) => {
      const row = el("div", "qa-case");
      row.append(el("strong", "", `${page.status === "tested" ? "Tested" : "Untested"}: ${page.url}`));
      if (page.reason || page.status !== "tested") row.append(el("p", "qa-muted", page.reason || "Not tested before this session ended."));
      coverage.append(row);
    });
    if (report.coverage.truncated) coverage.append(el("p", "qa-muted", "The discovery list reached its safety limit. More routes may exist."));
    holder.append(coverage);
  }
  if (report.bugs?.length) {
    const section = el("div", "qa-section");
    section.append(el("h4", "", "Issues"));
    report.bugs.forEach((bug) => {
      const card = el("div", "qa-card");
      const head = el("div", "qa-card-head");
      head.append(el("strong", "", bug.title), chip(bug.severity, SEVERITY_TONE[bug.severity] || "gray"));
      card.append(head);
      if (bug.steps) card.append(field("Steps", bug.steps));
      if (bug.expected) card.append(field("Expected", bug.expected));
      if (bug.actual) card.append(field("Actually", bug.actual));
      if (bug.screens?.length) { const shots = el("div", "qa-thumbs"); bug.screens.slice(0, 3).forEach((n) => shots.append(thumb(runId, n, bug.title))); card.append(shots); }
      section.append(card);
    });
    holder.append(section);
  }

  if (report.cases?.length) {
    const details = el("details", "qa-cases");
    details.open = report.cases.length <= 8;
    details.append(el("summary", "", `All checks (${report.cases.length})`));
    report.cases.forEach((item) => {
      const row = el("div", "qa-case");
      const top = el("div", "qa-case-head");
      top.append(chip(STATUS_TEXT[item.status] || item.status, STATUS_TONE[item.status] || "gray"), el("strong", "", item.title));
      row.append(top);
      const steps = [item.given && `Given ${item.given}`, item.when && `when ${item.when}`, item.then && `then ${item.then}`].filter(Boolean).join(", ");
      if (steps) row.append(el("p", "qa-muted", steps));
      if (item.notes) row.append(el("p", "qa-notes", item.notes));
      if (item.screens?.length) { const shots = el("div", "qa-thumbs"); item.screens.slice(0, 2).forEach((n) => shots.append(thumb(runId, n, item.title))); row.append(shots); }
      details.append(row);
    });
    holder.append(details);
  }

  const foot = [report.duration_seconds != null ? `${Math.max(1, Math.round(report.duration_seconds / 60))} min` : null, `${(report.pages || []).length} page${(report.pages || []).length === 1 ? "" : "s"}`, money(report.cost_usd)].filter(Boolean).join(" · ");
  holder.append(el("p", "qa-muted qa-foot", foot));
  return holder;
}

// Returns the extra card for a QA message, or null to let the chat show it as a normal message.
export function renderQaMessage(message) {
  switch (message.message_metadata?.kind) {
    case "qa_plan": return { lead: message.content, card: renderPlanCard(message) };
    case "qa_approval": return { lead: message.content, card: renderApprovalCard(message) };
    case "qa_report": return { lead: message.content, card: renderReport(message) };
    case "work_plan": return { lead: message.content, card: renderPlanCard(message) };
    case "work_approval": return { lead: message.content, card: renderApprovalCard(message) };
    case "work_report": return { lead: message.content, card: renderReport(message) };
    case "work_busy": return { lead: message.content, card: renderBusy(message) };
    default: return null;
  }
}

/* ---------- the computer panel ---------- */

function renderClock() {
  const run = state.runs.get(state.focus);
  const node = $("#qa-computer-body .qa-elapsed");
  if (node && run) node.textContent = elapsed(run);
}

async function frameUrl(run) {
  const have = state.frames.get(run.id);
  if (have && have.n === run.frame) return have.url;
  const response = await fetch(`/api/v2/qa/runs/${run.id}/frame?v=${run.frame}`, { headers: authHeaders() });
  if (!response.ok) throw new Error("no screen yet");
  const url = URL.createObjectURL(await response.blob());
  if (have?.url) setTimeout(() => URL.revokeObjectURL(have.url), 2000);
  state.frames.set(run.id, { n: run.frame, url });
  return url;
}

/* ---------- the live screen ---------- */

// One open stream per Prism. Every <img> showing the screen (sidebar, enlarged popup) subscribes to it,
// so the panel can re-render freely without dropping the connection.
const liveScreen = { prismId: null, runId: null, controller: null, url: null, views: new Set(), retry: null, status: "Connecting live view…" };

function liveStatus(text) {
  liveScreen.status = text;
  document.querySelectorAll(".qa-stream-status").forEach((node) => { node.textContent = text; });
}

function paintLive(url) {
  for (const image of [...liveScreen.views]) {
    if (!image.isConnected) { liveScreen.views.delete(image); continue; }
    image.src = url;
    image.classList.add("show");
  }
}

function frameBoundaries(buffer) {
  const frames = [];
  for (;;) {
    const end = indexOfBytes(buffer, [13, 10, 13, 10]);
    if (end < 0) break;
    const head = new TextDecoder().decode(buffer.subarray(0, end));
    const length = Number((/content-length:\s*(\d+)/i.exec(head) || [])[1]);
    if (!length) { buffer = buffer.subarray(end + 4); continue; }
    if (buffer.length < end + 4 + length) break;
    frames.push(buffer.slice(end + 4, end + 4 + length));
    // The trailing CRLF can arrive in the next network chunk.
    buffer = buffer.subarray(end + 4 + length);
  }
  return { frames, rest: buffer };
}

function indexOfBytes(buffer, pattern) {
  outer: for (let i = 0; i <= buffer.length - pattern.length; i += 1) {
    for (let j = 0; j < pattern.length; j += 1) if (buffer[i + j] !== pattern[j]) continue outer;
    return i;
  }
  return -1;
}

async function readLive(controller, prismId) {
  const response = await fetch(`/api/v2/prisms/${prismId}/computer/live`, { headers: authHeaders(), signal: controller.signal, cache: "no-store" });
  if (!response.ok || !response.body) throw new Error("asleep");
  const reader = response.body.getReader();
  let buffer = new Uint8Array(0);
  for (;;) {
    const watchdog = setTimeout(() => controller.abort(), 10000);
    let chunk;
    try { chunk = await reader.read(); } finally { clearTimeout(watchdog); }
    const { done, value } = chunk;
    if (done) return;
    const joined = new Uint8Array(buffer.length + value.length);
    joined.set(buffer); joined.set(value, buffer.length);
    const parsed = frameBoundaries(joined);
    buffer = parsed.rest;
    const newest = parsed.frames.at(-1); // a slow tab shows the newest frame, never a backlog
    if (!newest || controller.signal.aborted) continue;
    const url = URL.createObjectURL(new Blob([newest], { type: "image/jpeg" }));
    const decoded = new Image();
    decoded.src = url;
    try { await decoded.decode(); } catch { URL.revokeObjectURL(url); continue; }
    if (controller.signal.aborted || liveScreen.controller !== controller) { URL.revokeObjectURL(url); return; }
    const previous = liveScreen.url;
    liveScreen.url = url;
    paintLive(url);
    liveStatus("Live · continuous screen");
    if (previous) setTimeout(() => URL.revokeObjectURL(previous), 1000);
  }
}

function stopLive() {
  clearTimeout(liveScreen.retry);
  liveScreen.retry = null;
  liveScreen.controller?.abort();
  liveScreen.controller = null;
}

function startLive(prismId, runId) {
  if (liveScreen.controller && liveScreen.prismId === prismId && liveScreen.runId === runId) return;
  stopLive();
  if ((liveScreen.prismId !== prismId || liveScreen.runId !== runId) && liveScreen.url) { URL.revokeObjectURL(liveScreen.url); liveScreen.url = null; }
  Object.assign(liveScreen, { prismId, runId });
  const controller = new AbortController();
  liveScreen.controller = controller;
  liveStatus("Connecting live view…");
  readLive(controller, prismId)
    .catch(() => {})
    .finally(() => {
      if (liveScreen.controller !== controller) return;
      liveScreen.controller = null; // the computer was still starting, or the stream dropped: try again shortly
      liveStatus("Live view disconnected · reconnecting…");
      liveScreen.retry = setTimeout(() => { if (state.open && state.prism?.id === prismId && state.focus === runId && isActive(state.runs.get(runId))) startLive(prismId, runId); }, 1000);
    });
}

// Streams only while the panel is open and a task is running; otherwise nothing is held open.
function syncLive(run) {
  if (state.open && state.prism && usesComputer(state.prism) && isActive(run) && !run.startup_warning) startLive(state.prism.id, run.id);
  else stopLive();
}

function enlargedScreen() {
  let dialog = document.getElementById("qa-enlarged");
  if (!dialog) {
    dialog = el("dialog", "qa-enlarged");
    dialog.id = "qa-enlarged";
    dialog.setAttribute("aria-label", "Computer, enlarged");
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener("close", () => { dialog.replaceChildren(); });
    document.body.append(dialog);
  }
  return dialog;
}

function renderEnlarged() {
  const dialog = document.getElementById("qa-enlarged");
  if (!dialog?.open) return;
  const run = state.runs.get(state.focus);
  const top = el("div", "qa-enlarged-bar");
  top.append(el("strong", "", `${state.prism?.name || "Prism"}'s computer`));
  const close = button("Close", "button secondary", () => dialog.close());
  top.append(close);
  dialog.replaceChildren(top, screenFrame(run, true));
}

function openEnlarged() {
  const dialog = enlargedScreen();
  if (!dialog.open) dialog.showModal();
  renderEnlarged();
  dialog.querySelector("button")?.focus();
}

// The view takes the shape of whatever the computer's window really is.
function fitToShot(image) {
  image.addEventListener("load", () => {
    if (image.naturalWidth && image.parentElement) image.parentElement.style.aspectRatio = `${image.naturalWidth} / ${image.naturalHeight}`;
  });
  return image;
}

function screenFrame(run, large = false) {
  const frame = el("div", large ? "qa-screen large" : "qa-screen");
  const bar = el("div", "qa-chrome");
  const dots = el("span", "qa-dots"); dots.append(el("i"), el("i"), el("i"));
  bar.append(dots, el("span", "qa-address", run?.current_url || (run?.site ? `https://${run.site}` : "")));
  if (!large) {
    const enlarge = button("", "qa-enlarge", openEnlarged);
    enlarge.title = "Enlarge";
    enlarge.setAttribute("aria-label", "Enlarge the computer screen");
    enlarge.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>';
    bar.append(enlarge);
  }
  const view = el("div", "qa-view");
  const idle = el("div", "qa-idle");
  idle.append(el("span", "qa-idle-mark", state.prism?.name?.slice(0, 1) || "P"));
  view.append(idle);
  if (run?.frame != null) {
    const have = state.frames.get(run.id);
    const image = fitToShot(el("img", "qa-shot")); image.alt = "What the screen shows right now";
    if (have) { image.src = have.url; image.classList.add("show"); }
    if ((!have || have.n !== run.frame) && !state.frameLoading.has(run.id)) {
      state.frameLoading.add(run.id);
      frameUrl(run).then(() => { if (state.focus === run.id && state.open) renderPanel(); }).catch(() => {}).finally(() => state.frameLoading.delete(run.id));
    }
    view.append(image);
  } else if (run?.screen != null) {
    const key = `${run.id}:${run.screen}`;
    const image = fitToShot(el("img", "qa-shot")); image.alt = "What the screen shows right now";
    const cached = state.screens.get(key);
    if (cached) { image.src = cached; image.classList.add("show"); }
    else screenUrl(run.id, run.screen).then((url) => { image.src = url; image.classList.add("show"); }).catch(() => {});
    view.append(image);
  }
  if (liveScreen.url && liveScreen.prismId === state.prism?.id && liveScreen.runId === run?.id) {
    // The live stream is newer than any saved frame: show it, and keep this image updated.
    let image = view.querySelector(".qa-shot");
    if (!image) { image = fitToShot(el("img", "qa-shot")); image.alt = "What the screen shows right now"; view.append(image); }
    image.src = liveScreen.url;
    image.classList.add("show");
    liveScreen.views.add(image);
  } else if (isActive(run)) {
    // No live frame yet: the first one to arrive replaces whatever saved frame is showing.
    let image = view.querySelector(".qa-shot");
    if (!image) { image = fitToShot(el("img", "qa-shot")); image.alt = "What the screen shows right now"; view.append(image); }
    liveScreen.views.add(image);
  }
  frame.append(bar, view);
  return frame;
}

function progress(run) {
  const wrap = el("div", "qa-progress");
  if (isWork(run)) {
    const done = (run.checklist || []).filter((step) => step.status === "done" || step.status === "skipped").length;
    const total = (run.checklist || []).length;
    const bar = el("div", "qa-bar");
    const seg = el("span", "qa-seg tone-green"); seg.style.flex = String(done || 0);
    const rest = el("span", "qa-seg tone-none"); rest.style.flex = String(Math.max(total - done, total ? 0 : 1));
    if (done) bar.append(seg);
    if (total - done > 0 || !total) bar.append(rest);
    wrap.append(bar);
    if (total) wrap.append(el("p", "qa-muted", `${done} of ${total} steps done`));
    const meta = el("p", "qa-muted");
    const elapsedNode = el("span", "qa-elapsed", elapsed(run));
    meta.append(`Step ${run.turn}${run.max_turns ? ` of up to ${run.max_turns}` : ""} · ${money(run.cost_usd)}${run.budget_usd ? ` of ${money(run.budget_usd)}` : ""} · `, elapsedNode);
    wrap.append(meta);
    return wrap;
  }
  const cases = run.cases || {};
  const total = cases.total || 0;
  const bar = el("div", "qa-bar");
  [["pass", "green"], ["fail", "red"], ["blocked", "orange"], ["skipped", "gray"]].forEach(([key, tone]) => {
    if (cases[key]) { const seg = el("span", `qa-seg tone-${tone}`); seg.style.flex = String(cases[key]); bar.append(seg); }
  });
  const rest = total - ((cases.pass || 0) + (cases.fail || 0) + (cases.blocked || 0) + (cases.skipped || 0));
  if (rest > 0 || !total) { const seg = el("span", "qa-seg tone-none"); seg.style.flex = String(Math.max(rest, 1)); bar.append(seg); }
  wrap.append(bar);
  const line = el("p", "qa-muted");
  line.textContent = total ? `${total} checks · ${cases.pass || 0} passed · ${cases.fail || 0} failed${cases.blocked ? ` · ${cases.blocked} couldn't check` : ""}` : "No checks yet";
  wrap.append(line);
  const meta = el("p", "qa-muted");
  const elapsedNode = el("span", "qa-elapsed", elapsed(run));
  meta.append(`Step ${run.turn}${run.max_turns ? ` of ${run.max_turns}` : ""} · ${money(run.cost_usd)}${run.budget_usd ? ` of ${money(run.budget_usd)}` : ""} · `, elapsedNode);
  wrap.append(meta);
  return wrap;
}

function checklistBlock(run) {
  const wrap = el("div", "qa-checklist");
  wrap.append(el("h4", "", "Plan"));
  const marks = { done: "✓", doing: "●", skipped: "–", todo: "○" };
  run.checklist.forEach((step) => {
    const row = el("p", `qa-step ${step.status}`);
    row.append(el("span", "qa-step-mark", marks[step.status] || "○"), el("span", "", step.title));
    wrap.append(row);
  });
  return wrap;
}

async function resetComputer() {
  const name = state.prism?.name || "Prism";
  if (!window.confirm(`This signs ${name} out of every site and clears its browser. Continue?`)) return;
  try {
    state.computer = await agentApi(`/api/v2/prisms/${state.prism.id}/computer/reset`, { method: "POST" });
    state.logins = [];
    state.host.setStatus?.(`${name}'s computer was reset.`);
  } catch (error) { state.host.setStatus?.(error.message, true); }
  renderPanel();
}

async function removeLogin(login) {
  try { state.logins = await agentApi(`/api/v2/prisms/${state.prism.id}/logins/${login.id}`, { method: "DELETE" }); }
  catch (error) { state.host.setStatus?.(error.message, true); }
  renderPanel();
}

function computerFooter(live) {
  const wrap = el("div", "qa-footer");
  const logins = el("details", "qa-logins");
  logins.append(el("summary", "", `Saved logins (${state.logins.length})`));
  if (!state.logins.length) logins.append(el("p", "qa-muted", "None. I'll ask you in the chat when a site needs one."));
  state.logins.forEach((login) => {
    const row = el("div", "qa-login-row");
    const label = el("span", "");
    label.append(el("strong", "", login.site.replace(/^https?:\/\//, "")), document.createTextNode(` · ${login.username}${login.remember ? "" : " · one task"}`));
    row.append(label, button("Remove", "mini-button", () => removeLogin(login)));
    logins.append(row);
  });
  wrap.append(logins);
  const reset = button("Reset computer", "button secondary", resetComputer);
  reset.disabled = live;
  reset.title = live ? "Stop the task first" : "Forget every login and clear the browser";
  wrap.append(reset);
  return wrap;
}

function renderPanel() {
  const body = $("#qa-computer-body");
  if (!body) return;
  const name = state.prism?.name || "Prism";
  $("#qa-computer-title").textContent = `${name}'s computer`;
  if (!state.open) return;
  const run = state.runs.get(state.focus);
  const work = !run ? state.computers && !isQaPrism(state.prism) : isWork(run);
  const scrollTop = body.scrollTop;
  body.replaceChildren();
  body.append(screenFrame(run));
  syncLive(run);
  renderEnlarged();
  const caption = el("div", "qa-caption");
  const live = isActive(run);
  const waiting = run?.state === "waiting_approval" || Boolean(run?.startup_warning);
  caption.append(el("span", `qa-live${live ? " on" : ""}${waiting ? " waiting" : ""}`), el("strong", "", `${name}'s screen`));
  const offline = !run && state.computer?.state === "unavailable";
  caption.append(el("span", "qa-muted", run ? stateText(run) : offline ? "Offline" : state.computers ? "Asleep" : "Idle"));
  body.append(caption);
  if (live) {
    const status = el("p", "qa-muted qa-stream-status", run.startup_warning ? "Live view will connect when the testing workspace is available." : liveScreen.status);
    status.setAttribute("role", "status");
    body.append(status);
  } else if (run && (run.frame != null || run.screen != null || liveScreen.runId === run.id && liveScreen.url)) {
    body.append(el("p", "qa-muted", "Last screen · task ended"));
  }
  if (!run) {
    if (offline) body.append(el("p", "qa-error", state.computer.reason || "My computer is offline right now."));
    else if (work) body.append(el("p", "qa-empty", `Asleep. ${name}'s computer wakes up when you give it a task, for example "find five fintech companies in Bangalore and list their websites". You'll watch the work here.`));
    else body.append(el("p", "qa-empty", `Ask ${name} to test a website, for example "test example.com and check the contact form". You'll watch the work here.`));
  } else {
    if (run.startup_warning) body.append(el("p", "qa-now qa-waiting", run.startup_warning));
    else if (run.state === "starting") body.append(el("p", "qa-now live", run.activity || "Connecting to my testing workspace…"));
    else if (waiting) body.append(el("p", "qa-now qa-waiting", "Waiting for you in the chat"));
    else if (run.activity) body.append(el("p", `qa-now${live ? " live" : ""}`, run.activity));
    if (isWork(run) && run.checklist?.length) body.append(checklistBlock(run));
    body.append(progress(run));
    if (live) body.append(button(isWork(run) ? "Stop" : "Stop the test", "button secondary qa-stop", () => cancelRun(run)));
    if (run.state === "error" && run.error) body.append(el("p", "qa-error", run.error));
    if (run.activity_log?.length) {
      const details = el("details", "qa-log");
      details.append(el("summary", "", "What I've done"));
      [...run.activity_log].reverse().forEach((item) => details.append(el("p", "", item.text)));
      body.append(details);
    }
  }
  const past = state.order.map((id) => state.runs.get(id)).filter(Boolean);
  if (past.length) {
    const section = el("div", "qa-runs");
    section.append(el("h4", "", isWork(past[0]) ? "Tasks" : "Tests"));
    past.slice(0, 8).forEach((item) => {
      const row = el("button", `qa-run${item.id === state.focus ? " current" : ""}`);
      row.type = "button";
      row.append(el("strong", "", item.site || item.plan?.title || "Task"), el("span", "qa-muted", `${stateText(item)}${item.cases?.total ? ` · ${item.cases.pass || 0}/${item.cases.total}` : ""}`));
      row.addEventListener("click", () => { state.focus = item.id; renderPanel(); });
      section.append(row);
    });
    body.append(section);
  }
  if (state.computers) body.append(computerFooter(live));
  body.scrollTop = scrollTop;
}

export async function checkAvailability() {
  try {
    const status = await agentApi("/api/v2/qa/status");
    state.available = status.available;
    state.computers = Boolean(status.computers);
  } catch { state.available = null; }
  return state.available;
}
