import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
const workState = { prisms: new Map(), runs: [], approvals: [], loaded: false, prismFilter: "", prismListLoaded: false };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function button(label, className, onClick) {
  const node = el("button", className, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

function timestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "" : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function openPrism(prismId, runId = null) {
  const prism = workState.prisms.get(prismId);
  if (!prism) return;
  window.prism?.setActiveTab?.("agent");
  document.dispatchEvent(new CustomEvent("prism:open-agent", { detail: { prism } }));
  if (runId) document.dispatchEvent(new CustomEvent("prism:focus-computer-run", { detail: { runId } }));
}

function runCard(run) {
  const card = el("article", "unified-work-card");
  const head = el("div", "unified-work-head");
  const title = el("div", "unified-work-title");
  title.append(el("h3", "", run.title || "Prism task"), el("span", `qa-chip tag-${run.active ? "blue" : run.state === "succeeded" ? "green" : run.state === "failed" || run.state === "error" ? "red" : "gray"}`, String(run.state || "unknown").replaceAll("_", " ")));
  head.append(title, el("span", "panel-note", run.prism_name || "Prism"));
  const details = el("div", "unified-work-meta");
  details.append(el("span", "", run.kind === "qa" ? "Website test" : "Computer task"));
  if (run.created_at) details.append(el("span", "", timestamp(run.created_at)));
  details.append(el("span", "", `$${Number(run.cost_usd || 0).toFixed(4)}`));
  card.append(head, details);
  if (run.activity) card.append(el("p", "unified-work-activity", run.activity));
  if (run.error) card.append(el("p", "inline-error", run.error));
  if (run.report?.summary) card.append(el("p", "unified-work-summary", run.report.summary));
  const actions = el("div", "unified-work-actions");
  actions.append(button("Open this work", "mini-button", () => openPrism(run.prism_id, run.id)));
  if (run.active) actions.append(button("Watch computer", "mini-button primary", () => openPrism(run.prism_id, run.id)));
  if (run.active) actions.append(button("Stop run", "mini-button danger", async (event) => {
    const control = event.currentTarget;
    control.disabled = true;
    try {
      await agentApi(`/api/v2/qa/runs/${run.id}/cancel`, { method: "POST" });
      await loadRuns();
    } catch (error) {
      showStatus("work-status", error.message, true);
      control.disabled = false;
    }
  }));
  card.append(actions);
  return card;
}

function approvalCard(item) {
  const card = el("article", "unified-work-card approval-work-card");
  const heading = item.kind === "bug_filing" ? item.payload.title || "File a bug" : item.payload.summary || item.payload.question || "Computer action needs review";
  card.append(el("h3", "", heading));
  card.append(el("p", "panel-note", `${item.prism_name} · ${item.run_title} · ${String(item.kind).replaceAll("_", " ")}`));
  if (item.payload.site) card.append(el("p", "unified-work-detail", `Site: ${item.payload.site}`));
  for (const [label, key] of [["Severity", "severity"], ["Steps", "steps"], ["Expected", "expected"], ["Actual", "actual"], ["Details", "details"], ["Reason", "reason"]]) {
    if (item.payload[key]) {
      const row = el("p", "unified-work-detail");
      row.append(el("strong", "", `${label}: `), document.createTextNode(String(item.payload[key])));
      card.append(row);
    }
  }
  const actions = el("div", "unified-work-actions");
  actions.append(button("Open this work in Prism", "mini-button", () => openPrism(item.prism_id, item.run_id)));
  if (item.can_decide_here) {
    for (const [label, decision, className] of [["Reject", "reject", "mini-button"], ["Approve", "approve", "mini-button primary"]]) {
      actions.append(button(label, className, async (event) => {
        const control = event.currentTarget;
        control.disabled = true;
        try {
          await agentApi(`/api/v2/qa/approvals/${item.id}/decision`, {
            method: "POST", body: JSON.stringify({ decision }),
          });
          await loadApprovals();
        } catch (error) {
          showStatus("approval-status", error.message, true);
          control.disabled = false;
        }
      }));
    }
  } else {
    actions.append(el("span", "panel-note", item.kind === "login" ? "Sign-in decisions stay in the chat so credentials are handled safely." : "Answer this question in the Prism conversation."));
  }
  card.append(actions);
  return card;
}

function showStatus(id, message, isError = false) {
  const node = $(`#${id}`);
  if (!node) return;
  node.textContent = message || "";
  node.classList.toggle("error", isError);
}

async function loadRuns() {
  const list = $("#work-run-list");
  if (!list) return;
  list.replaceChildren(el("p", "panel-note", "Loading work…"));
  try {
    await ensurePrisms();
    const query = new URLSearchParams({ limit: "100" });
    if (workState.prismFilter) query.set("prism_id", workState.prismFilter);
    const [runs] = await Promise.all([
      agentApi(`/api/v2/work/runs?${query}`),
      loadRuntimeStatus(),
    ]);
    workState.runs = runs;
    list.replaceChildren();
    if (!workState.runs.length) list.append(el("p", "empty-state", "No Prism work yet. Start a task from a Prism conversation and it will appear here."));
    else workState.runs.forEach((run) => list.append(runCard(run)));
    showStatus("work-status", `${workState.runs.length} recent task${workState.runs.length === 1 ? "" : "s"}. Costs are reported by the computer service.`);
  } catch (error) {
    list.replaceChildren(el("p", "inline-error", error.message));
    showStatus("work-status", "Work could not be loaded.", true);
  }
}

async function ensurePrisms() {
  if (workState.prismListLoaded) return;
  const prisms = await agentApi("/api/v2/prisms?include_archived=false");
  workState.prisms = new Map(prisms.map((prism) => [prism.id, prism]));
  workState.prismListLoaded = true;
  const filter = $("#work-prism-filter");
  if (filter) {
    filter.replaceChildren(new Option("All Prisms", ""));
    for (const prism of workState.prisms.values()) filter.add(new Option(prism.name, prism.id));
  }
}

async function loadRuntimeStatus() {
  const status = $("#work-runtime-status");
  if (!status) return;
  try {
    const result = await agentApi("/api/v2/work/status");
    status.textContent = result.message;
    status.classList.toggle("error", !result.available);
    status.classList.toggle("success", result.available);
  } catch (error) {
    status.textContent = error.message;
    status.classList.add("error");
  }
}

async function loadApprovals() {
  const list = $("#work-approval-list");
  if (!list) return;
  list.replaceChildren(el("p", "panel-note", "Loading approvals…"));
  try {
    await ensurePrisms();
    workState.approvals = await agentApi("/api/v2/work/approvals?limit=100");
    list.replaceChildren();
    if (!workState.approvals.length) list.append(el("p", "empty-state", "No computer actions are waiting for approval."));
    else workState.approvals.forEach((item) => list.append(approvalCard(item)));
    const badge = $("#work-approval-count");
    badge.textContent = String(workState.approvals.length);
    badge.hidden = workState.approvals.length === 0;
    showStatus("approval-status", `${workState.approvals.length} decision${workState.approvals.length === 1 ? "" : "s"} waiting.`);
  } catch (error) {
    list.replaceChildren(el("p", "inline-error", error.message));
    showStatus("approval-status", "Approvals could not be loaded.", true);
  }
}

document.addEventListener("prism:list", (event) => {
  workState.prisms = new Map((event.detail?.prisms || []).map((prism) => [prism.id, prism]));
  workState.prismListLoaded = true;
  const filter = $("#work-prism-filter");
  if (filter) {
    const previous = filter.value;
    filter.replaceChildren(new Option("All Prisms", ""));
    for (const prism of workState.prisms.values()) filter.add(new Option(prism.name, prism.id));
    filter.value = workState.prisms.has(previous) ? previous : "";
    workState.prismFilter = filter.value;
  }
  if (!workState.loaded) {
    workState.loaded = true;
    loadApprovals();
  }
});
document.addEventListener("prism:tab", (event) => {
  if (event.detail?.tab === "work") { loadRuns(); loadApprovals(); }
  if (event.detail?.tab === "approvals") loadApprovals();
});
$("#work-refresh")?.addEventListener("click", loadRuns);
$("#approval-refresh")?.addEventListener("click", loadApprovals);
$("#work-prism-filter")?.addEventListener("change", (event) => {
  workState.prismFilter = event.currentTarget.value;
  loadRuns();
});
