import { agentApi } from "./api.js";
import { prismLogo } from "./prism-logo.js";
import { el, icon, button, empty, chip, panel, searchInput, formDialog, plainSummary } from "./workspace-ui.js";

// The Brain: what every Prism knows. Rendered as a Workspace page.
export const brainApi = {
  list: () => agentApi("/api/v2/brain"),
  decide: (entry, action) => agentApi(`/api/v2/brain/${entry.id}/${action}`, { method: "POST" }),
  remove: (entry) => agentApi(`/api/v2/brain/${entry.id}`, { method: "DELETE" }),
};
export const brainProposedCount = (entries) => entries.filter((entry) => entry.status === "proposed").length;

const fail = (error) => window.prism?.setStatus?.(error.message, true);
const sourceLabel = (entry) => (entry.source === "chat" ? "Learned from a chat" : entry.source === "prism" ? "Prism work note" : "Added by you");

export function brain(ctx) {
  const { entries, reload } = ctx.brain;
  const proposed = entries.filter((entry) => entry.status === "proposed");
  const approved = entries.filter((entry) => entry.status === "approved");
  const facts = approved.filter((entry) => entry.source !== "prism");
  const work = approved.filter((entry) => entry.source === "prism");

  ctx.actions.replaceChildren(button("Add to Brain", () => editEntry(null), { glyph: "plus", className: "button" }));

  function editEntry(entry) {
    formDialog(entry ? "Edit knowledge" : "Add to the Brain", [
      { name: "title", label: "Title", required: true, maxLength: 200, value: entry?.title, placeholder: "For example: What OneClarity does" },
      { name: "body", label: "What every Prism should know", type: "textarea", required: true, maxLength: 2000, value: entry?.body },
    ], async (values) => {
      const saved = await agentApi(entry ? `/api/v2/brain/${entry.id}` : "/api/v2/brain", { method: entry ? "PATCH" : "POST", body: JSON.stringify(values) });
      // Editing a suggestion is approving it.
      if (entry?.status === "proposed") await brainApi.decide(saved, "approve");
      await reload();
    }, { submit: entry ? "Save" : "Add", description: "Every Prism reads approved entries before it works. Keep it factual and short." });
  }
  async function act(task) { try { await task(); await reload(); } catch (error) { fail(error); } }
  async function remove(entry) {
    const confirmed = await window.prism?.askDialog?.({ title: "Remove from the Brain?", message: "Prisms will no longer know this.", confirmLabel: "Remove", danger: true });
    if (confirmed) act(() => brainApi.remove(entry));
  }

  const page = el("div", "bn-page");

  // Overview tiles.
  const stats = el("div", "bn-stats");
  for (const [glyph, value, label] of [["brain", facts.length, "Facts every Prism knows"], ["circle-dashed", proposed.length, "Waiting for approval"], ["bot", work.length, "Prism work notes"]]) {
    const tile = el("div", "bn-stat"); tile.append(icon(glyph)); const text = el("div"); text.append(el("strong", "", value), el("span", "", label)); tile.append(text); stats.append(tile);
  }
  page.append(stats);

  // Suggestions learned from chats wait for approval.
  if (proposed.length) {
    const section = panel("Waiting for your approval", "Prisms picked these up from your chats. They are not used until you add them.");
    section.classList.add("bn-pending");
    const list = el("div", "bn-list");
    for (const entry of proposed) list.append(entryCard(entry, [
      button("Add", () => act(() => brainApi.decide(entry, "approve")), { className: "mini-button primary", glyph: "circle-check" }),
      button("Edit", () => editEntry(entry), { glyph: "pencil" }),
      button("Dismiss", () => act(() => brainApi.decide(entry, "reject")), { glyph: "x" }),
    ]));
    section.append(list); page.append(section);
  }

  // What every Prism knows, with search.
  const known = panel("What every Prism knows", "Shared context: your organisation, tone, products, rules.");
  const list = el("div", "bn-list");
  let query = "";
  function draw() {
    const needle = query.trim().toLowerCase();
    const shown = facts.filter((entry) => !needle || `${entry.title} ${entry.body}`.toLowerCase().includes(needle));
    if (!facts.length) list.replaceChildren(empty("Nothing yet", "Add what every Prism should know about your organisation.", "brain"));
    else if (!shown.length) list.replaceChildren(empty("No matches", "Try a different search.", "search"));
    else list.replaceChildren(...shown.map((entry) => entryCard(entry, [
      button("", () => editEntry(entry), { className: "icon-button", glyph: "pencil", title: "Edit" }),
      button("", () => remove(entry), { className: "icon-button", glyph: "trash", title: "Delete" }),
    ])));
  }
  if (facts.length > 4) known.querySelector(".workspace-panel-heading").append(searchInput("Search the Brain", "", (value) => { query = value; draw(); }));
  draw();
  known.append(list); page.append(known);

  // Prisms share what they are working on.
  if (work.length) {
    const section = panel("What Prisms are working on", "Each Prism leaves a short note so the others stay in step.");
    const grid = el("div", "bn-list");
    for (const entry of work) grid.append(entryCard(entry, [button("", () => remove(entry), { className: "icon-button", glyph: "x", title: "Clear note" })], true));
    section.append(grid); page.append(section);
  }
  ctx.root.replaceChildren(page);
}

function entryCard(entry, actions, byPrism = false) {
  const card = el("article", "bn-entry");
  if (byPrism) card.append(prismLogo(entry.prism_name || entry.title, "prism-logo"));
  const text = el("div", "bn-entry-text");
  text.append(el("strong", "", (byPrism && entry.prism_name) || entry.title), el("p", "", byPrism ? plainSummary(entry.body, 400) : entry.body));
  const meta = el("div", "bn-entry-meta");
  meta.append(chip(sourceLabel(entry), entry.source === "chat" ? "blue" : entry.source === "prism" ? "gray" : "green"));
  text.append(meta);
  const bar = el("div", "bn-entry-actions"); bar.append(...actions);
  card.append(text, bar);
  return card;
}
