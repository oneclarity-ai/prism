import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
const currencyKey = "prism-currency";
const rateKey = "prism-usd-inr";
let currency = "INR";
let inrRate = null;
try {
  currency = localStorage.getItem(currencyKey) === "USD" ? "USD" : "INR";
  inrRate = Number(JSON.parse(localStorage.getItem(rateKey) || "{}").rate) || null;
} catch { /* storage unavailable */ }
function money(value) {
  const usd = Number(value) || 0;
  if (currency === "INR" && inrRate) {
    const amount = usd * inrRate;
    const digits = amount >= 100 ? 2 : amount >= 1 ? 3 : 4;
    return `₹${amount.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
  }
  return `$${usd.toFixed(usd >= 1 ? 2 : usd >= 0.01 ? 4 : 6)}`;
}
async function loadRate() {
  try {
    const response = await fetch("https://open.er-api.com/v6/latest/USD", { signal: AbortSignal.timeout(4000) });
    const rate = Number((await response.json()).rates?.INR);
    if (rate > 0) {
      inrRate = rate;
      localStorage.setItem(rateKey, JSON.stringify({ rate, at: Date.now() }));
    }
  } catch { /* keep the last known rate */ }
}
function renderCurrency() {
  document.querySelectorAll("[data-currency]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.currency === currency)));
}
function isoDay(date) { return date.toISOString().slice(0, 10); }
function addDays(day, delta) {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  return isoDay(date);
}
const COST_LABELS = {
  qa_tester_test_runs: "QA tester: website test runs",
  qa_workspace_other_runs: "QA tester: runs started outside Prism",
  prism_computer_tasks: "Prism tasks on its own computer",
  prism_work_plan: "Task plans",
  prism_work_report: "Task reports",
  prism_work_intent: "Understanding task requests",
  prism_role_instructions: "Writing how a Prism works",
  prism_qa_plan: "QA tester: test plans",
  prism_qa_report: "QA tester: reports",
  prism_qa_followup: "QA tester: follow-up answers",
  prism_message_voice: "Wording drafted messages",
  prism_job_description: "Drafting job descriptions",
};
function label(name) { if (COST_LABELS[name]) return COST_LABELS[name]; return String(name || "unknown").replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase()); }

const SOURCES = ["prism", "swarm"];
const number = (value) => Number(value || 0).toLocaleString("en-IN");
let range = "month";
let view = "feature";

function sum(rows, field) { return rows.reduce((total, row) => total + Number(row[field] || 0), 0); }

function tokenLine(rows) {
  const input = sum(rows, "input_tokens"), cached = sum(rows, "cached_input_tokens"), output = sum(rows, "output_tokens");
  return `${number(sum(rows, "calls"))} calls · ${number(input)} in (${number(cached)} cached) · ${number(output)} out`;
}

function renderRows(box, rows, total) {
  box.replaceChildren();
  const used = rows.filter((row) => Number(row.estimated_cost_usd) > 0 || row.calls);
  box.classList.toggle("empty-state", !used.length);
  if (!used.length) { box.textContent = "No usage in this range."; return; }
  used.sort((a, b) => Number(b.estimated_cost_usd) - Number(a.estimated_cost_usd)).forEach((row) => {
    const share = total > 0 ? Math.round((Number(row.estimated_cost_usd) / total) * 100) : 0;
    const line = el("div", "cost-row");
    const head = el("div", "cost-row-head");
    head.append(el("span", "cost-name", view === "model" ? String(row.group) : label(row.group)), el("strong", "", money(row.estimated_cost_usd)));
    const bar = el("div", "cost-bar");
    const fill = el("i");
    fill.style.width = `${Math.max(share, row.calls ? 2 : 0)}%`;
    bar.append(fill);
    const unpriced = row.unpriced_calls ? ` · ${row.unpriced_calls} unpriced` : "";
    line.append(head, bar, el("span", "cost-meta", `${tokenLine([row])} · ${share}%${unpriced}`));
    box.append(line);
  });
}

function billedLine(source, billed) {
  if (!billed?.configured) return "";
  const row = billed.sources?.[source];
  if (!row) return "Azure billed: not set up for this source";
  if (row.error) return `Azure billed: ${row.error}`;
  const amount = row.currency === "USD" ? money(row.cost)
    : row.currency === "INR" && currency === "INR" ? `₹${Number(row.cost).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : `${Number(row.cost).toFixed(4)} ${row.currency || ""}`.trim();
  return `Azure billed: ${amount} (posts hours late)`;
}

let cost = null;
let costRequest = 0;

function renderProviderCosts(data) {
  const box = $("#settings-provider-costs");
  if (!box) return;
  box.replaceChildren();
  const rows = [...(data.by_provider || [])].sort((a, b) => Number(b.estimated_cost_usd) - Number(a.estimated_cost_usd));
  if (!rows.length) { box.textContent = "No recorded usage in this period."; return; }
  for (const item of rows) {
    const provider = item.group;
    const name = provider === "qa_workspace" ? "Agentic swarm (upstream provider unrecorded)"
      : provider === "azure_openai" ? "Azure OpenAI" : provider === "codex_local" ? "Local Codex"
        : provider === "openai" ? "OpenAI" : label(provider);
    const line = el("div", "provider-cost-row");
    line.append(el("span", "", `${name} · ${number(item.calls)} calls${item.unpriced_calls ? ` · ${number(item.unpriced_calls)} unpriced` : ""}`), el("strong", "", money(item.estimated_cost_usd)));
    box.append(line);
  }
}

async function loadCost() {
  const request = ++costRequest;
  const selectedRange = range;
  await loadRate();
  if (request !== costRequest) return;
  const data = await agentApi(`/api/v1/usage/llm/sources?period=${selectedRange}`);
  if (request !== costRequest) return;
  cost = { data, billed: null };
  renderCost();
  agentApi(`/api/v1/usage/llm/azure-billed?from=${data.range.from}&to=${data.range.to}`)
    .then((billed) => { cost.billed = billed; renderCost(); })
    .catch(() => {});
}

function renderCost() {
  if (!cost) return;
  const { data, billed } = cost;
  document.querySelectorAll("[data-cost]").forEach((node) => {
    const [source, period] = node.dataset.cost.split(":");
    const usd = source === "all"
      ? SOURCES.reduce((total, name) => total + Number(data.periods[period][name].estimated_cost_usd), 0)
      : data.periods[period][source].estimated_cost_usd;
    node.textContent = money(usd);
  });
  const todayAll = SOURCES.reduce((total, source) => total + Number(data.periods.today[source].estimated_cost_usd), 0);
  const periodAll = SOURCES.reduce((total, source) => total + Number(data.periods[range][source].estimated_cost_usd), 0);
  $("#settings-cost-total").textContent = money(periodAll);
  const todayUnpriced = SOURCES.reduce((total, source) => total + data.periods.today[source].unpriced_calls, 0);
  const topbar = $("#ai-cost-today");
  if (topbar) {
    topbar.textContent = `Today's AI cost: ${money(todayAll)}${todayUnpriced ? " + unpriced usage" : ""}`;
    topbar.title = `${data.timezone} day. Prism plus agent swarm, estimated from provider tokens.`;
  }
  const unpriced = SOURCES.reduce((total, source) => total + sum(data.by_feature[source], "unpriced_calls"), 0);
  $("#cost-note").textContent = `Estimated from exact token counts and each model's rate, ${data.timezone} days.`
    + (unpriced ? ` ${unpriced} ${unpriced === 1 ? "call is" : "calls are"} missing a rate, so the real total may be higher.` : "");
  $("#cost-updated").textContent = `${currency === "INR" && inrRate ? `1 USD = ₹${inrRate.toFixed(2)} · ` : ""}Updated ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  document.querySelectorAll("[data-cost-source]").forEach((panel) => {
    const source = panel.dataset.costSource;
    const rows = data[view === "model" ? "by_model" : "by_feature"][source];
    const total = sum(data.by_feature[source], "estimated_cost_usd");
    panel.querySelector("[data-cost-total]").textContent = money(total);
    panel.querySelector("[data-cost-tokens]").textContent = tokenLine(data.by_feature[source]);
    const azure = panel.querySelector("[data-cost-azure]");
    azure.textContent = billedLine(source, billed);
    azure.hidden = !azure.textContent;
    renderRows(panel.querySelector("[data-cost-rows]"), rows, total);
  });
  document.querySelectorAll("[data-cost-range]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.costRange === range)));
  document.querySelectorAll("[data-cost-view]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.costView === view)));
  renderProviderCosts(data);
}

function load() {
  return loadCost().catch(() => { $("#cost-note").textContent = "Spend could not be loaded."; });
}

document.addEventListener("prism:tab", (event) => { if (event.detail.tab === "spending") load(); });
document.addEventListener("prism:v22-mode", (event) => { if (event.detail.enabled) setTimeout(load, 0); });
$("#refresh-button")?.addEventListener("click", () => setTimeout(load, 0));
load();
setInterval(() => loadCost().catch(() => {}), 60 * 60 * 1000);
document.addEventListener("click", (event) => {
  const choice = event.target.closest("[data-cost-range], [data-cost-view]");
  if (choice) {
    if (choice.dataset.costRange) range = choice.dataset.costRange; else view = choice.dataset.costView;
    loadCost().catch(() => {});
    return;
  }
  const button = event.target.closest("[data-currency]");
  if (!button) return;
  currency = button.dataset.currency;
  try { localStorage.setItem(currencyKey, currency); } catch { /* ignore */ }
  renderCurrency();
  renderCost();
});
renderCurrency();
