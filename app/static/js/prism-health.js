import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
const ui = () => window.prism || {};
const selectedKey = "prism-v22-selected-id";
const selectedPrism = () => { try { return localStorage.getItem(selectedKey); } catch { return null; } };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
const when = (value) => (value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "never");
function showError(message = "") {
  const error = $("#prism-health-error");
  error.hidden = !message;
  error.textContent = message;
}
function stat(value, label) {
  const box = el("div", "health-stat");
  box.append(el("strong", "", String(value)), el("span", "", label));
  return box;
}
function section(title, ...children) {
  const wrap = el("section");
  wrap.append(el("h3", "", title), ...children);
  return wrap;
}

function renderHealth(prismId, health, tuning) {
  const body = $("#prism-health-body");
  const diagnosis = el("ul");
  health.diagnosis.forEach((line) => diagnosis.append(el("li", "", line)));
  const m = health.metrics;
  const grid = el("div", "health-grid");
  [
    [m.runs, "runs (24h)"], [m.failed, "failed"], [m.skipped, "skipped by limits"], [m.graph_reads, "Teams chats read"],
    [m.events_created, "new messages"], [m.observations_created, "updates created"], [m.alerts_deduplicated, "duplicate alerts avoided"],
    [m.notifications_delivered, "alerts shown"], [m.drafts_prepared, "drafts prepared"], [m.false_positive_feedback, "marked not useful"],
    [m.model_calls, "model calls"], [m.avg_duration_ms === null ? "—" : `${m.avg_duration_ms} ms`, "avg run time"],
  ].forEach(([value, label]) => grid.append(stat(value, label)));

  const mon = health.monitoring;
  const status = el("ul");
  [
    `Microsoft: ${health.microsoft.connected ? "connected" : "not connected"}`,
    `Model provider: ${health.provider.configured ? "configured" : "not configured"}${health.provider.signal_model_enabled ? "" : " (signal model off; rules only)"}`,
    `Scheduler: server ${health.scheduler.server_enabled ? "on" : "off"}, mode ${health.scheduler.mode.replace("_", " ")}${health.scheduler.mode_enabled ? "" : " (disabled)"}`,
    `Last checked Teams: ${when(mon.last_checked_at)}`,
    `Last successful run: ${when(mon.last_successful_run_at)}`,
    `Runs today: ${health.budget.runs_today} of ${health.budget.max_runs_per_day}`,
    `Raw Teams activity is kept for ${health.retention_days} days; updates and approvals are kept.`,
  ].forEach((line) => status.append(el("li", "", line)));

  const signals = el("div");
  tuning.signals.forEach((signal) => {
    const row = el("div", "health-signal");
    const label = el("div", "grow");
    label.append(el("strong", "", signal.label));
    const notes = [];
    if (signal.protected) notes.push("Safety signal: always on.");
    if (signal.muted) notes.push(`Muted by you${signal.suppressed_count ? `; hid ${signal.suppressed_count} update${signal.suppressed_count === 1 ? "" : "s"}` : ""}.`);
    const feedback = Object.entries(signal.feedback).map(([kind, count]) => `${count} ${kind.replaceAll("_", " ")}`);
    if (feedback.length) notes.push(`Feedback: ${feedback.join(", ")}.`);
    if (signal.suggestion) notes.push(signal.suggestion);
    if (notes.length) label.append(el("div", "turn-meta", notes.join(" ")));
    row.append(label);
    if (!signal.protected) {
      const button = el("button", "mini-button", signal.muted ? "Unmute" : signal.suggestion ? "Mute for this Prism" : "Mute");
      button.type = "button";
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await agentApi(`/api/v2/prisms/${prismId}/tuning/signals/${signal.signal_type}`, { method: "PUT", body: JSON.stringify({ muted: !signal.muted }) });
          await load();
        } catch (error) { showError(error.message); button.disabled = false; }
      });
      row.append(button);
    }
    signals.append(row);
  });

  const budget = el("div", "health-budget");
  const fields = [
    ["max_runs_per_day", "Runs per day"], ["max_model_calls_per_day", "Model calls per day"], ["max_consecutive_failures", "Pause after failed runs in a row"],
  ];
  fields.forEach(([key, label]) => {
    const wrap = el("label", "", label);
    const input = el("input");
    input.type = "number"; input.min = key === "max_model_calls_per_day" ? "0" : "1"; input.value = health.budget[key]; input.dataset.key = key;
    wrap.append(input);
    budget.append(wrap);
  });
  const save = el("button", "button", "Save limits");
  save.type = "button";
  save.addEventListener("click", async () => {
    save.disabled = true;
    showError();
    try {
      const values = {};
      budget.querySelectorAll("input").forEach((input) => { values[input.dataset.key] = Number(input.value); });
      await agentApi(`/api/v2/prisms/${prismId}/budget`, { method: "PUT", body: JSON.stringify(values) });
      ui().setStatus?.("Limits saved for this Prism.");
      await load();
    } catch (error) { showError(error.message); save.disabled = false; }
  });

  const review = el("div");
  if (health.review_required) {
    const confirm = el("button", "button", "I've reviewed this Prism");
    confirm.type = "button";
    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      try {
        await agentApi(`/api/v2/prisms/${prismId}/migration-review/acknowledge`, { method: "POST" });
        ui().setStatus?.("Thanks. Automatic monitoring is now allowed for this Prism.");
        await load();
      } catch (error) { showError(error.message); confirm.disabled = false; }
    });
    review.append(confirm);
  }
  body.replaceChildren(
    section("What's going on", diagnosis, review),
    section("Last 24 hours", grid),
    section("Status", status),
    section("Signals for this Prism (mute only after you confirm)", signals),
    section("Limits", budget, save),
  );
}

async function load() {
  const prismId = selectedPrism();
  if (!prismId) return;
  showError();
  try {
    const [health, tuning] = await Promise.all([agentApi(`/api/v2/prisms/${prismId}/health`), agentApi(`/api/v2/prisms/${prismId}/tuning`)]);
    renderHealth(prismId, health, tuning);
  } catch (error) { $("#prism-health-body").textContent = ""; showError(error.message); }
}

$("#prism-health-button").addEventListener("click", () => {
  $("#prism-health-body").textContent = "Loading…";
  $("#prism-health-dialog").showModal();
  load();
});
$("#prism-health-close").addEventListener("click", () => $("#prism-health-dialog").close());
