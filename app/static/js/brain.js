import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
let entries = [];

const setStatus = (message, isError = false) => (window.prism || {}).setStatus?.(message, isError);
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(label, onClick, className = "mini-button") {
  const node = el("button", className, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}
const showError = (message) => { const node = $("#brain-error"); node.hidden = !message; node.textContent = message; };

function card(entry, actions) {
  const node = el("article", "brain-entry");
  const text = el("div", "brain-entry-text");
  text.append(el("strong", "", entry.title), el("p", "", entry.body));
  const meta = entry.source === "chat" ? "Learned from a chat" : entry.source === "prism" ? "Prism work note" : "";
  if (meta) text.append(el("span", "brain-entry-meta", meta));
  node.append(text, el("div", "brain-entry-actions"));
  node.lastChild.append(...actions);
  return node;
}

function render() {
  const proposed = entries.filter((entry) => entry.status === "proposed");
  const facts = entries.filter((entry) => entry.status === "approved" && entry.source !== "prism");
  const work = entries.filter((entry) => entry.status === "approved" && entry.source === "prism");
  $("#brain-proposed-section").hidden = !proposed.length;
  $("#brain-work-section").hidden = !work.length;
  const count = $("#nav-brain-count");
  count.hidden = !proposed.length; count.textContent = String(proposed.length);
  $("#brain-proposed").replaceChildren(...proposed.map((entry) => card(entry, [
    button("Add", () => decide(entry, "approve"), "mini-button primary"), button("Dismiss", () => decide(entry, "reject")), button("Edit", () => edit(entry)),
  ])));
  const list = $("#brain-facts");
  list.classList.toggle("empty-state", !facts.length);
  if (facts.length) list.replaceChildren(...facts.map((entry) => card(entry, [button("Edit", () => edit(entry)), button("Delete", () => remove(entry))])));
  else list.textContent = "Nothing yet. Add what Prisms should know about your organisation.";
  $("#brain-work").replaceChildren(...work.map((entry) => { const item = card(entry, [button("Clear", () => remove(entry))]); item.querySelector("strong").textContent = entry.prism_name || entry.title; return item; }));
}

async function load() {
  try { entries = await agentApi("/api/v2/brain"); render(); } catch (error) { setStatus(error.message, true); }
}
function edit(entry) {
  $("#brain-id").value = entry.id; $("#brain-title").value = entry.title; $("#brain-body").value = entry.body;
  $("#brain-save").textContent = "Save"; $("#brain-cancel").hidden = false; $("#brain-title").focus();
}
function reset() {
  $("#brain-id").value = ""; $("#brain-title").value = ""; $("#brain-body").value = "";
  $("#brain-save").textContent = "Add to Brain"; $("#brain-cancel").hidden = true; showError("");
}
async function decide(entry, action) {
  try { await agentApi(`/api/v2/brain/${entry.id}/${action}`, { method: "POST" }); await load(); } catch (error) { setStatus(error.message, true); }
}
async function remove(entry) {
  const confirmed = await window.prism?.askDialog?.({ title: "Remove from the Brain?", message: "Prisms will no longer know this.", confirmLabel: "Remove", danger: true });
  if (!confirmed) return;
  try { await agentApi(`/api/v2/brain/${entry.id}`, { method: "DELETE" }); await load(); } catch (error) { setStatus(error.message, true); }
}
async function submit(event) {
  event.preventDefault();
  const id = $("#brain-id").value;
  const payload = { title: $("#brain-title").value, body: $("#brain-body").value };
  const save = $("#brain-save");
  save.disabled = true; showError("");
  try {
    const saved = await agentApi(id ? `/api/v2/brain/${id}` : "/api/v2/brain", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
    // Editing a suggestion is approving it.
    if (id && entries.find((entry) => entry.id === id)?.status === "proposed") await agentApi(`/api/v2/brain/${saved.id}/approve`, { method: "POST" });
    reset(); await load();
  } catch (error) { showError(error.message); } finally { save.disabled = false; }
}

$("#brain-form").addEventListener("submit", submit);
$("#brain-cancel").addEventListener("click", reset);
document.addEventListener("prism:tab", (event) => { if (event.detail.tab === "settings") load(); });
$("[data-subtab-target=\"brain\"]").addEventListener("click", load);
document.addEventListener("prism:v22-mode", (event) => { if (event.detail.enabled) load(); });
