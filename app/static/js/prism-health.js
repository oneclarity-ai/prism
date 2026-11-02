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

function kv(label, value, tone) {
  const row = el("div", "health-kv");
  row.append(el("span", "", label));
  const right = el("strong", tone ? `tone-${tone}` : "", value);
  row.append(right);
  return row;
}

function renderHealth(prismId, health, tuning) {
  const body = $("#prism-health-body");
  const mon = health.monitoring;
  const m = health.metrics;
  const healthy = health.microsoft.connected && !health.review_required && !m.failed;
  const hero = el("div", `health-hero ${healthy ? "ok" : "warn"}`);
  hero.append(el("span", "health-dot"));
  const heroText = el("div");
  heroText.append(el("strong", "", health.diagnosis[0] || (healthy ? "Everything looks fine." : "Needs attention")));
  health.diagnosis.slice(1).forEach((line) => heroText.append(el("p", "", line)));
  hero.append(heroText);
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
    heroText.append(confirm);
  }

  const grid = el("div", "health-grid");
  [
    [m.runs, "Runs"], [m.failed, "Failed"], [m.events_created, "New messages"],
    [m.observations_created, "Updates"], [m.notifications_delivered, "Alerts shown"], [m.drafts_prepared, "Drafts"],
  ].forEach(([value, label]) => grid.append(stat(value, label)));
  const more = el("details", "health-more");
  more.append(el("summary", "", "More numbers"));
  const moreGrid = el("div", "health-grid");
  [
    [m.skipped, "Skipped by limits"], [m.graph_reads, "Teams chats read"], [m.alerts_deduplicated, "Duplicates avoided"],
    [m.false_positive_feedback, "Marked not useful"], [m.model_calls, "Model calls"], [m.avg_duration_ms === null ? "—" : `${m.avg_duration_ms} ms`, "Avg run time"],
  ].forEach(([value, label]) => moreGrid.append(stat(value, label)));
  more.append(moreGrid);

  const status = el("div", "health-card");
  status.append(
    kv("Microsoft", health.microsoft.connected ? "Connected" : "Not connected", health.microsoft.connected ? "ok" : "warn"),
    kv("Model provider", health.provider.configured ? (health.provider.signal_model_enabled ? "Configured" : "Rules only") : "Not configured", health.provider.configured ? "ok" : "warn"),
    kv("Scheduler", `${health.scheduler.server_enabled ? "On" : "Off"} · ${health.scheduler.mode.replace("_", " ")}${health.scheduler.mode_enabled ? "" : " (disabled)"}`, health.scheduler.server_enabled && health.scheduler.mode_enabled ? "ok" : "warn"),
    kv("Last checked Teams", when(mon.last_checked_at)),
    kv("Last successful run", when(mon.last_successful_run_at)),
    kv("Runs today", `${health.budget.runs_today} of ${health.budget.max_runs_per_day}`),
  );
  const retention = el("p", "health-note", `Raw Teams activity is kept for ${health.retention_days} days. Updates and approvals are kept.`);

  const signals = el("div", "health-card");
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
    if (notes.length) label.append(el("small", "", notes.join(" ")));
    row.append(label);
    const toggle = el("input", "toggle");
    toggle.type = "checkbox";
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-label", `${signal.label} alerts`);
    toggle.checked = !signal.muted;
    toggle.disabled = Boolean(signal.protected);
    toggle.addEventListener("change", async () => {
      toggle.disabled = true;
      try {
        await agentApi(`/api/v2/prisms/${prismId}/tuning/signals/${signal.signal_type}`, { method: "PUT", body: JSON.stringify({ muted: !toggle.checked }) });
        await load();
      } catch (error) { showError(error.message); toggle.checked = !toggle.checked; toggle.disabled = false; }
    });
    row.append(toggle);
    signals.append(row);
  });

  const budget = el("div", "health-budget");
  [["max_runs_per_day", "Runs per day"], ["max_model_calls_per_day", "Model calls per day"], ["max_consecutive_failures", "Pause after failures in a row"]].forEach(([key, label]) => {
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
  const limits = el("div", "health-card");
  limits.append(budget, save);

  body.replaceChildren(
    hero,
    section("Last 24 hours", grid, more),
    section("Status", status, retention),
    section("Signals · switch off to mute", signals),
    section("Limits", limits),
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
