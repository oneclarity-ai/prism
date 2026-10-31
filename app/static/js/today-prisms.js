import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
const WORKING = "active";
const SETUP = new Set(["draft", "onboarding", "awaiting_confirmation"]);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
const currencyKey = "prism-currency";
const rateKey = "prism-usd-inr";
let currency = "USD";
let inrRate = null;
try {
  currency = localStorage.getItem(currencyKey) === "INR" ? "INR" : "USD";
  inrRate = Number(JSON.parse(localStorage.getItem(rateKey) || "{}").rate) || null;
} catch { /* storage unavailable */ }
function money(value) {
  const usd = Number(value) || 0;
  if (currency === "INR" && inrRate) {
    const amount = usd * inrRate;
    return `₹${amount.toLocaleString("en-IN", { minimumFractionDigits: amount >= 1 ? 2 : 4, maximumFractionDigits: amount >= 1 ? 2 : 4 })}`;
  }
  return `$${usd.toFixed(usd >= 1 ? 2 : 4)}`;
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
function label(name) { return String(name || "unknown").replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase()); }
function ago(iso) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / 1440)}d ago`;
}
function stateLabel(value) {
  const key = String(value).toLowerCase();
  return { active: "Active", draft: "Draft", onboarding: "Onboarding", awaiting_confirmation: "Review agreement" }[key] || label(key);
}

function renderBreakdown(selector, rows, total) {
  const box = $(selector);
  box.replaceChildren();
  const priced = rows.filter((row) => Number(row.estimated_cost_usd) > 0 || row.calls);
  box.classList.toggle("empty-state", !priced.length);
  if (!priced.length) { box.textContent = "No usage yet this month."; return; }
  priced.sort((a, b) => Number(b.estimated_cost_usd) - Number(a.estimated_cost_usd)).forEach((row) => {
    const share = total > 0 ? Math.round((Number(row.estimated_cost_usd) / total) * 100) : 0;
    const line = el("div", "cost-row");
    const head = el("div", "cost-row-head");
    head.append(el("span", "cost-name", label(row.group)), el("strong", "", money(row.estimated_cost_usd)));
    const bar = el("div", "cost-bar");
    const fill = el("i");
    fill.style.width = `${Math.max(share, row.calls ? 2 : 0)}%`;
    bar.append(fill);
    line.append(head, bar, el("span", "cost-meta", `${row.calls} ${row.calls === 1 ? "call" : "calls"} · ${share}%`));
    box.append(line);
  });
}

let cost = null;
async function loadCost() {
  await loadRate();
  const today = await agentApi("/api/v1/usage/llm/today");
  const day = String(today.from);
  const monthStart = `${day.slice(0, 8)}01`;
  const range = (from) => `from=${from}&to=${day}`;
  const [total, week, month, byFeature, byModel] = await Promise.all([
    agentApi(`/api/v1/usage/llm?${range(addDays(day, -365))}&limit=1`),
    agentApi(`/api/v1/usage/llm?${range(addDays(day, -6))}&limit=1`),
    agentApi(`/api/v1/usage/llm?${range(monthStart)}&limit=1`),
    agentApi(`/api/v1/usage/llm/by-feature?${range(monthStart)}`),
    agentApi(`/api/v1/usage/llm/by-model?${range(monthStart)}`),
  ]);
  cost = { today, total, week, month, byFeature, byModel };
  renderCost();
}

function renderCost() {
  if (!cost) return;
  const { today, total, week, month, byFeature, byModel } = cost;
  $("#cost-today").textContent = money(today.estimated_cost_usd);
  $("#cost-week").textContent = money(week.summary.estimated_cost_usd);
  $("#cost-total").textContent = money(total.summary.estimated_cost_usd);
  $("#cost-month").textContent = money(month.summary.estimated_cost_usd);
  $("#cost-calls").textContent = month.summary.calls;
  const unpriced = month.summary.unpriced_calls;
  $("#cost-note").textContent = unpriced
    ? `Estimated from provider tokens. ${unpriced} ${unpriced === 1 ? "call is" : "calls are"} missing pricing, so the real total may be higher.`
    : "Estimated from provider tokens, month to date.";
  const monthTotal = Number(month.summary.estimated_cost_usd);
  $("#cost-updated").textContent = `${currency === "INR" && inrRate ? ` · 1 USD = ₹${inrRate.toFixed(2)}` : ""} · updated ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}, refreshes hourly`;
  renderBreakdown("#cost-by-feature", byFeature, monthTotal);
  renderBreakdown("#cost-by-model", byModel, monthTotal);
}

function renderPrisms(prisms) {
  $("#prisms-active").textContent = prisms.filter((p) => String(p.state).toLowerCase() === WORKING).length;
  $("#prisms-setup").textContent = prisms.filter((p) => SETUP.has(String(p.state).toLowerCase())).length;
  const grid = $("#today-prism-grid");
  grid.replaceChildren();
  grid.classList.toggle("empty-state", !prisms.length);
  if (!prisms.length) { grid.textContent = "No Prisms yet. Use + in the sidebar to create one."; return; }
  prisms.forEach((prism) => {
    const working = String(prism.state).toLowerCase() === WORKING;
    const card = el("button", "prism-card");
    card.type = "button";
    const head = el("div", "prism-card-head");
    head.append(el("span", "prism-icon", (prism.name.trim()[0] || "P").toUpperCase()), el("strong", "", prism.name), el("span", `prism-state ${String(prism.state).toLowerCase()}`, stateLabel(prism.state)));
    card.append(head, el("p", "prism-card-desc", prism.description), el("span", "prism-card-foot", `${working ? "Open conversation" : "Continue setup"} · updated ${ago(prism.updated_at)}`));
    card.addEventListener("click", () => document.dispatchEvent(new CustomEvent("prism:open", { detail: { id: prism.id } })));
    grid.append(card);
  });
}

let loading = false;
async function load() {
  if (loading || !$("#today-prisms") || $("#today-prisms").hidden) return loadCost().catch(() => {});
  loading = true;
  try {
    await Promise.allSettled([
      agentApi("/api/v2/prisms?include_archived=false").then(renderPrisms),
      loadCost().catch(() => { $("#cost-today").textContent = "n/a"; $("#cost-note").textContent = "Spend could not be loaded."; }),
    ]);
  } finally { loading = false; }
}

document.addEventListener("prism:tab", (event) => { if (event.detail.tab === "overview") load();
  if (event.detail.tab === "settings") loadCost().catch(() => {}); });
document.addEventListener("prism:v22-mode", (event) => { if (event.detail.enabled) setTimeout(load, 0); });
document.querySelector('[data-subtab-target="usage"]')?.addEventListener("click", () => loadCost().catch(() => {}));
$("#refresh-button")?.addEventListener("click", () => setTimeout(load, 0));
load();
setInterval(() => loadCost().catch(() => {}), 60 * 60 * 1000);
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-currency]");
  if (!button) return;
  currency = button.dataset.currency;
  try { localStorage.setItem(currencyKey, currency); } catch { /* ignore */ }
  renderCurrency();
  renderCost();
});
renderCurrency();
