import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
const setStatus = (message, isError = false) => (window.prism || {}).setStatus?.(message, isError);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function remove(prism) {
  const confirmed = await window.prism?.askDialog?.({ title: `Delete ${prism.name}?`, message: "This removes the Prism, its chats and its saved logins for good. It cannot be undone.", confirmLabel: "Delete Prism", danger: true });
  if (!confirmed) return;
  try {
    await agentApi(`/api/v2/prisms/${prism.id}`, { method: "DELETE" });
    setStatus(`${prism.name} deleted.`);
    document.dispatchEvent(new CustomEvent("prism:prisms-changed"));
    await load();
  } catch (error) { setStatus(error.message, true); }
}

async function load() {
  const list = $("#archived-prisms");
  try {
    const prisms = (await agentApi("/api/v2/prisms?include_archived=true")).filter((prism) => String(prism.state).toLowerCase() === "archived");
    list.classList.toggle("empty-state", !prisms.length);
    if (!prisms.length) { list.textContent = "No archived Prisms."; return; }
    list.replaceChildren(...prisms.map((prism) => {
      const card = el("article", "brain-entry");
      const text = el("div", "brain-entry-text");
      text.append(el("strong", "", prism.name), el("p", "", prism.description), el("span", "brain-entry-meta", `Archived ${new Date(prism.updated_at).toLocaleDateString()}`));
      const delete_ = el("button", "mini-button", "Delete");
      delete_.type = "button";
      delete_.addEventListener("click", () => remove(prism));
      const actions = el("div", "brain-entry-actions");
      actions.append(delete_);
      card.append(text, actions);
      return card;
    }));
  } catch (error) { setStatus(error.message, true); }
}

document.addEventListener("prism:tab", (event) => { if (event.detail.tab === "settings") load(); });
$('[data-subtab-target="archived"]').addEventListener("click", load);
