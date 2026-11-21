// Settings dialog behaviour: preferences, notifications, connections and search.
const $ = (selector) => document.querySelector(selector);
const prefs = window.prismPrefs;

/* Preferences ------------------------------------------------------------ */
const contrast = $("#contrast-select");
contrast.value = prefs.get("contrast") || "system";
contrast.addEventListener("change", () => prefs.set("contrast", contrast.value === "system" ? null : contrast.value));

const size = $("#size-select");
size.value = window.prismUi.size;
size.addEventListener("change", () => window.prismUi.set(size.value));

const enter = $("#pref-enter-newline");
enter.checked = prefs.get("enter-newline") === "1";
enter.addEventListener("change", () => prefs.set("enter-newline", enter.checked ? "1" : null));

$("#pref-timezone").textContent = Intl.DateTimeFormat().resolvedOptions().timeZone || "Local time";

/* Notifications ---------------------------------------------------------- */
const approvals = $("#pref-notify-approvals");
approvals.checked = prefs.get("notify-approvals") !== "0";
approvals.addEventListener("change", () => prefs.set("notify-approvals", approvals.checked ? null : "0"));

function renderBrowserAlerts() {
  const badge = $("#pref-notify-status");
  const enable = $("#pref-notify-enable");
  if (!("Notification" in window)) { badge.textContent = "Not supported"; badge.className = "badge"; enable.hidden = true; return; }
  const state = Notification.permission;
  badge.textContent = state === "granted" ? "On" : state === "denied" ? "Blocked" : "Off";
  badge.className = `badge ${state === "granted" ? "green" : state === "denied" ? "orange" : ""}`.trim();
  enable.hidden = state !== "default";
}
$("#pref-notify-enable").addEventListener("click", () => Notification.requestPermission().then(renderBrowserAlerts));
renderBrowserAlerts();

/* Connections ------------------------------------------------------------ */
function connection(name, ready, text) {
  $(`#conn-${name}-detail`).textContent = text;
  const badge = $(`#conn-${name}-badge`);
  badge.textContent = ready === null ? "Unknown" : ready ? "Connected" : "Needs attention";
  badge.className = `badge ${ready ? "green" : ready === false ? "orange" : ""}`.trim();
}
function renderStatus({ provider, microsoft, computers }) {
  if (microsoft) {
    const user = microsoft.connection?.user_principal_name;
    connection("microsoft", Boolean(microsoft.is_connected), microsoft.is_connected ? `Signed in as ${user || "your Microsoft account"}.` : "Connect your account so Prism can read Teams chats and send replies you approve.");
  }
  if (provider) connection("provider", Boolean(provider.ready), provider.detail || "AI provider status unavailable.");
  if (computers !== null) connection("engine", Boolean(computers), computers ? "Prisms can use computers for approved browser tasks." : "Computer features are not enabled on this server.");
}
document.addEventListener("prism:status", (event) => renderStatus(event.detail));
// The dashboard may have reported status before this module loaded.
if (window.prismStatus) renderStatus(window.prismStatus);

/* Search ----------------------------------------------------------------- */
const search = $("#settings-search");
search.addEventListener("input", () => {
  const query = search.value.trim().toLowerCase();
  const nav = $("#settings-dialog .settings-nav");
  let shown = 0;
  nav.querySelectorAll("[data-subtab-target]").forEach((tab) => {
    const section = $(`[data-subtab-group="settings"][data-subtab="${tab.dataset.subtabTarget}"]`);
    const hit = !query || `${tab.textContent} ${section?.textContent || ""}`.toLowerCase().includes(query);
    tab.classList.toggle("search-hidden", !hit);
    if (hit) shown += 1;
  });
  nav.querySelectorAll(".settings-nav-label").forEach((label) => {
    let next = label.nextElementSibling;
    let any = false;
    while (next && !next.classList.contains("settings-nav-label")) { any ||= !next.classList.contains("search-hidden"); next = next.nextElementSibling; }
    label.classList.toggle("search-hidden", !any);
  });
  $("#settings-search-empty").hidden = shown > 0;
});
search.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  const tabs = [...$("#settings-dialog .settings-nav").querySelectorAll("[data-subtab-target]")];
  tabs.find((tab) => !tab.hidden && !tab.classList.contains("search-hidden"))?.click();
});
