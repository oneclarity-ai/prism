import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
const ui = () => window.prism || {};
const selectedKey = "prism-v22-selected-id";
const POLL_MS = 15000;

// One id per open page; the server uses it for presence and to give each notification a single claimant.
const clientId = (() => {
  try {
    let id = sessionStorage.getItem("prism-client-id");
    if (!id) { id = crypto.randomUUID(); sessionStorage.setItem("prism-client-id", id); }
    return id;
  } catch { return crypto.randomUUID(); }
})();

let timer = null;
let busy = false;
const supported = () => "Notification" in window;
const permission = () => (supported() ? Notification.permission : "unsupported");

async function refreshSummaries() {
  const rows = await agentApi("/api/v2/prisms/updates/summary");
  document.dispatchEvent(new CustomEvent("prism:updates", { detail: { summaries: new Map(rows.map((row) => [row.prism_id, row])) } }));
}

async function deliver() {
  // Never claim without permission: a claim is the one attempt, so it must be able to succeed.
  if (permission() !== "granted") return;
  const { notification } = await agentApi("/api/v2/prisms/notifications/claim", { method: "POST", body: JSON.stringify({ client_id: clientId }) });
  if (!notification) return;
  let result = "delivered";
  try {
    const shown = new Notification(notification.title, { body: notification.body, tag: notification.tag });
    shown.onclick = () => {
      window.focus();
      document.dispatchEvent(new CustomEvent("prism:open", { detail: { id: notification.prism_id } }));
      shown.close();
    };
  } catch { result = "error"; }
  await agentApi(`/api/v2/prisms/notifications/${notification.notification_id}/result`, { method: "POST", body: JSON.stringify({ client_id: clientId, result }) });
}

async function tick() {
  if (busy) return;
  busy = true;
  try {
    await agentApi("/api/v2/prisms/notifications/presence", { method: "POST", body: JSON.stringify({ client_id: clientId }) });
    await refreshSummaries();
    await deliver();
  } catch {
    // Updates and alerts are additive; a failed poll never blocks the workspace and retries next tick.
  } finally { busy = false; }
}

function start() {
  if (timer) return;
  tick();
  timer = setInterval(tick, POLL_MS);
}
function stop() { clearInterval(timer); timer = null; }

/* Per-Prism notification settings. Permission is requested only from an explicit click, once. */

const selectedPrism = () => { try { return localStorage.getItem(selectedKey); } catch { return null; } };
function dialogError(message = "") {
  const error = $("#prism-notify-error");
  error.hidden = !message;
  error.textContent = message;
}
function permissionCopy() {
  return {
    unsupported: "This browser does not support notifications, so updates appear only inside Prism.",
    denied: "Notifications are blocked for this site in your browser settings. Updates still appear inside Prism.",
    granted: "Browser permission is allowed.",
    default: "Your browser will ask for permission when you save with alerts on.",
  }[permission()];
}
async function openNotifyDialog() {
  const prismId = selectedPrism();
  if (!prismId) return;
  dialogError();
  try {
    const setting = await agentApi(`/api/v2/prisms/${prismId}/notification-settings`);
    $("#prism-notify-enabled").checked = setting.enabled;
    $("#prism-notify-urgency").value = setting.min_urgency;
    $("#prism-notify-permission").textContent = permissionCopy();
    $("#prism-notify-dialog").dataset.prismId = prismId;
    $("#prism-notify-dialog").showModal();
  } catch (error) { ui().setStatus?.(error.message, true); }
}
async function saveNotifySettings() {
  const dialog = $("#prism-notify-dialog");
  const button = $("#prism-notify-save");
  const enabled = $("#prism-notify-enabled").checked;
  button.disabled = true;
  try {
    if (enabled && permission() === "default") await Notification.requestPermission();
    await agentApi(`/api/v2/prisms/${dialog.dataset.prismId}/notification-settings`, { method: "PUT", body: JSON.stringify({ enabled, min_urgency: $("#prism-notify-urgency").value }) });
    dialog.close();
    ui().setStatus?.(enabled && permission() !== "granted" ? "Alerts saved. Browser permission is off, so updates appear only inside Prism." : enabled ? "Browser alerts are on while a Prism page is open." : "Browser alerts are off.");
  } catch (error) { dialogError(error.message); }
  finally { button.disabled = false; }
}

$("#prism-notify-button").addEventListener("click", openNotifyDialog);
$("#prism-notify-cancel").addEventListener("click", () => $("#prism-notify-dialog").close());
$("#prism-notify-save").addEventListener("click", saveNotifySettings);
document.addEventListener("prism:updates-refresh", () => refreshSummaries().catch(() => {}));
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && timer) tick(); });
document.addEventListener("prism:v22-mode", (event) => (event.detail.enabled ? start() : stop()));
if (ui().isV22Enabled?.() === true) start();
