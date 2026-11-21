import { agentApi } from "./api.js";

const $ = (selector) => document.querySelector(selector);
const RANK = ["Your manager", "Above you", "Peer", "In your team", "Reports to you", "Colleague"];
const TONES = ["gray", "blue", "green", "orange", "purple", "yellow", "red"];
const people = { me: null, list: [], syncedAt: null, loaded: false };
const view = { mode: "list", query: "" };
let editing = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
const initials = (name) => String(name || "?").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "?";
function avatar(name, className = "") {
  let hash = 0;
  for (const character of String(name || "")) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return el("span", `avatar ${TONES[hash % TONES.length]} ${className}`.trim(), initials(name));
}
const setStatus = (message, isError = false) => (window.prism || {}).setStatus?.(message, isError);
const everyone = () => (people.me ? [people.me, ...people.list] : [...people.list]);
const byId = () => new Map(everyone().map((person) => [person.id, person]));
const subtitle = (person) => [person.title, person.department].filter(Boolean).join(" · ");

async function load() {
  try {
    const data = await agentApi("/api/v1/people");
    people.me = data.me; people.list = data.people; people.syncedAt = data.synced_at; people.loaded = true;
    render();
  } catch (error) { setStatus(error.message, true); }
}

async function sync() {
  const button = $("#people-sync-button");
  button.disabled = true;
  button.textContent = "Reading Teams…";
  try {
    const result = await agentApi("/api/v1/people/sync", { method: "POST" });
    setStatus(result.me_found
      ? `Found ${result.people} ${result.people === 1 ? "person" : "people"} in your chats and their managers.`
      : "Synced, but Prism could not find your own profile in the directory.");
    await load();
    document.querySelector("#refresh-button")?.click();
  } catch (error) { setStatus(error.message, true); }
  finally { button.disabled = false; button.textContent = "Refresh from Teams"; }
}

/* The user's own card. ----------------------------------------------------- */
function renderMe() {
  // Long role descriptions show three lines and open on demand, so the page stays compact.
  function clamped(className, text) {
    const wrap = el("div", "people-clamp");
    const para = el("p", `${className} clamped`, text);
    const toggle = el("button", "people-clamp-toggle", "Show more");
    toggle.type = "button";
    toggle.hidden = text.length < 220;
    toggle.setAttribute("aria-expanded", "false");
    toggle.addEventListener("click", () => {
      const open = para.classList.toggle("clamped") === false;
      toggle.textContent = open ? "Show less" : "Show more";
      toggle.setAttribute("aria-expanded", String(open));
    });
    wrap.append(para, toggle);
    return wrap;
  }
  const box = $("#people-me");
  box.replaceChildren();
  const me = people.me;
  if (!me) {
    box.append(el("p", "people-me-empty", "Prism doesn't know who you are yet. Refresh from Teams to pull your name, role and manager, then add what you do."));
    return;
  }
  const head = el("div", "people-me-head");
  const copy = el("div", "people-me-copy");
  copy.append(el("span", "people-me-eyebrow", "You"), el("strong", "people-me-name", me.name), el("span", "people-me-sub", subtitle(me) || "Add your role"));
  const facts = [me.manager_name ? `Reports to ${me.manager_name}` : "No manager set", `${me.direct_report_count} direct ${me.direct_report_count === 1 ? "report" : "reports"}`];
  copy.append(el("span", "people-me-facts", facts.join(" · ")));
  const edit = el("button", "mini-button", "Edit about me");
  edit.type = "button";
  edit.addEventListener("click", () => openEditor(me));
  head.append(avatar(me.name, "large"), copy, edit);
  box.append(head);
  if (me.responsibilities) box.append(clamped("people-me-text", me.responsibilities));
  if (me.notes) box.append(clamped("people-me-text muted", me.notes));
  if (!me.responsibilities) box.append(el("p", "people-me-hint", "Tell Prism what you're responsible for so every Prism understands your role."));
}

/* People: grouped list or org chart. --------------------------------------- */
function matches(person) {
  const query = view.query.trim().toLowerCase();
  return !query || [person.name, person.title, person.department, person.manager_name, person.responsibilities].some((value) => String(value || "").toLowerCase().includes(query));
}

function personRow(person) {
  const row = el("button", "person-row");
  row.type = "button";
  const copy = el("span", "person-copy");
  copy.append(el("strong", "", person.name), el("span", "person-sub", subtitle(person) || "No role on record"));
  const line = [person.manager_name ? `Reports to ${person.manager_name}` : "", person.responsibilities || ""].filter(Boolean).join(" · ");
  if (line) copy.append(el("span", "person-line", line));
  row.append(avatar(person.name), copy);
  const tags = el("span", "person-tags");
  if (person.is_me) tags.append(el("span", "person-tag", "You"));
  else if (!person.in_chats && !person.in_team) tags.append(el("span", "person-tag faint", "Org link"));
  if (person.overrides.length) tags.append(el("span", "person-tag", "Edited"));
  row.append(tags);
  row.addEventListener("click", () => openEditor(person));
  return row;
}

function renderList(container, visible) {
  const groups = new Map();
  visible.forEach((person) => groups.set(person.relationship, [...(groups.get(person.relationship) || []), person]));
  [...groups.keys()].sort((a, b) => RANK.indexOf(a) - RANK.indexOf(b)).forEach((name) => {
    const section = el("section", "people-group");
    const title = el("h3", "people-group-title", name);
    title.append(el("span", "people-group-count", String(groups.get(name).length)));
    section.append(title, ...groups.get(name).map(personRow));
    container.append(section);
  });
}

function renderTree(container, visible) {
  const ids = new Set(visible.map((person) => person.id));
  const children = new Map();
  visible.forEach((person) => {
    const parent = person.manager_id && ids.has(person.manager_id) ? person.manager_id : null;
    children.set(parent, [...(children.get(parent) || []), person]);
  });
  const branch = (parent, depth) => {
    const list = el("ul", "org-tree");
    (children.get(parent) || []).forEach((person) => {
      const item = el("li");
      const row = personRow(person);
      if (person.is_me) row.classList.add("is-me");
      item.append(row);
      if (depth < 12 && children.has(person.id)) item.append(branch(person.id, depth + 1));
      list.append(item);
    });
    return list;
  };
  container.append(branch(null, 0));
}

function render() {
  renderMe();
  const container = $("#people-list");
  container.replaceChildren();
  const visible = everyone().filter(matches);
  document.querySelectorAll("[data-people-view]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.peopleView === view.mode)));
  if (!people.list.length) {
    container.className = "people-list empty-state";
    container.textContent = "No people yet. Refresh from Teams to pull your team and the people you chat with.";
    return;
  }
  if (!visible.length) {
    container.className = "people-list empty-state";
    container.textContent = "Nobody matches that search.";
    return;
  }
  container.className = "people-list";
  if (view.mode === "tree") renderTree(container, visible);
  else renderList(container, visible.filter((person) => !person.is_me));
  if (people.syncedAt) container.append(el("p", "people-synced", `Last refreshed ${new Date(people.syncedAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`));
}

/* Editing a person (or yourself). ------------------------------------------ */
function openEditor(person) {
  editing = person;
  const dialog = $("#person-edit-dialog");
  const self = person.is_me;
  $("#person-edit-avatar").textContent = initials(person.name);
  $("#person-edit-name").textContent = self ? `About you, ${person.name.split(" ")[0]}` : person.name;
  $("#person-edit-note").textContent = self
    ? "Every Prism uses this to know who you are and how to work with you."
    : `${person.email} · ${person.relationship}`;
  $("#person-edit-title").value = person.title || "";
  $("#person-edit-department").value = person.department || "";
  $("#person-edit-responsibilities").value = person.responsibilities || "";
  $("#person-edit-notes").value = person.notes || "";
  $("#person-edit-responsibilities-label").textContent = self ? "What you do" : "What they do";
  $("#person-edit-notes-label").textContent = self ? "How you like to work" : "Notes for Prism";
  $("#person-edit-notes").placeholder = self ? "For example: Short messages, decisions in writing, no meetings before 10." : "For example: Prefers short messages, best reached in the morning.";
  const select = $("#person-edit-manager");
  select.replaceChildren(new Option("Nobody / unknown", ""));
  everyone().filter((other) => other.id !== person.id).forEach((other) => select.append(new Option(other.is_me ? `${other.name} (you)` : other.name, other.id)));
  select.value = person.manager_id || "";
  $("#person-edit-reset").hidden = !person.overrides.length;
  $("#person-edit-error").hidden = true;
  dialog.showModal();
  $("#person-edit-title").focus();
}

async function savePerson(event) {
  event.preventDefault();
  const person = editing;
  const changes = {};
  const compare = (key, value) => { if ((value || "") !== (person[key] || "")) changes[key] = value; };
  compare("title", $("#person-edit-title").value.trim());
  compare("department", $("#person-edit-department").value.trim());
  compare("responsibilities", $("#person-edit-responsibilities").value.trim());
  compare("notes", $("#person-edit-notes").value.trim());
  const manager = $("#person-edit-manager").value || null;
  if (manager !== (person.manager_id || null)) changes.manager_id = manager;
  try {
    if (Object.keys(changes).length) {
      const data = await agentApi(`/api/v1/people/${person.id}`, { method: "PATCH", body: JSON.stringify(changes) });
      people.me = data.me; people.list = data.people;
    }
    $("#person-edit-dialog").close();
    render();
    setStatus("Saved. Prism will use this from now on.");
  } catch (error) {
    $("#person-edit-error").textContent = error.message;
    $("#person-edit-error").hidden = false;
  }
}

async function resetPerson() {
  try {
    const data = await agentApi(`/api/v1/people/${editing.id}/reset`, { method: "POST" });
    people.me = data.me; people.list = data.people;
    $("#person-edit-dialog").close();
    render();
    setStatus("Back to what Microsoft says.");
  } catch (error) {
    $("#person-edit-error").textContent = error.message;
    $("#person-edit-error").hidden = false;
  }
}

/* Per-Prism visibility, in the chat's settings drawer. --------------------- */
const prismView = { id: null, name: "", scope: "all", ids: new Set(), query: "" };

async function openPrismPeople(detail) {
  prismView.id = detail.prismId; prismView.name = detail.prismName; prismView.query = "";
  try {
    const [scope] = await Promise.all([agentApi(`/api/v2/prisms/${detail.prismId}/people`), people.loaded ? null : load()]);
    prismView.scope = scope.scope; prismView.ids = new Set(scope.employee_ids);
    renderPrismPeople();
  } catch (error) { setStatus(error.message, true); }
}

async function savePrismPeople() {
  try {
    await agentApi(`/api/v2/prisms/${prismView.id}/people`, { method: "PUT", body: JSON.stringify({ scope: prismView.scope, employee_ids: [...prismView.ids] }) });
  } catch (error) { setStatus(error.message, true); }
}

function renderPrismPeople() {
  const root = $("#prism-people-root");
  root.replaceChildren();
  root.append(el("p", "panel-note", `Choose who ${prismView.name} knows about. It uses their role and reporting line to write to the right person in the right tone.`));
  const choices = el("div", "people-scope");
  [["all", "Everyone Prism knows"], ["selected", "Only people I pick"]].forEach(([value, label]) => {
    const row = el("label", "people-scope-option");
    const input = document.createElement("input");
    input.type = "radio"; input.name = "prism-people-scope"; input.value = value; input.checked = prismView.scope === value;
    input.addEventListener("change", () => { prismView.scope = value; renderPrismPeople(); savePrismPeople(); });
    row.append(input, el("span", "", label));
    choices.append(row);
  });
  root.append(choices);
  if (prismView.scope !== "selected") return;
  const search = document.createElement("input");
  search.type = "search"; search.placeholder = "Search people"; search.value = prismView.query; search.setAttribute("aria-label", "Search people");
  search.addEventListener("input", () => { prismView.query = search.value; renderPrismPeopleList(list); });
  const list = el("div", "people-pick-list");
  root.append(search, list);
  renderPrismPeopleList(list);
  if (!people.list.length) list.textContent = "No people yet. Refresh from the Teams page first.";
  if (search.value) { search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
}

function renderPrismPeopleList(list) {
  list.replaceChildren();
  const query = prismView.query.trim().toLowerCase();
  people.list.filter((person) => !query || `${person.name} ${person.title || ""} ${person.department || ""}`.toLowerCase().includes(query)).forEach((person) => {
    const row = el("label", "people-pick");
    const box = document.createElement("input");
    box.type = "checkbox"; box.className = "toggle"; box.setAttribute("role", "switch"); box.checked = prismView.ids.has(person.id);
    box.addEventListener("change", () => { box.checked ? prismView.ids.add(person.id) : prismView.ids.delete(person.id); savePrismPeople(); });
    const copy = el("span", "person-copy");
    copy.append(el("strong", "", person.name), el("span", "person-sub", subtitle(person) || person.relationship));
    row.append(avatar(person.name), copy, box);
    list.append(row);
  });
}

/* Wiring. ------------------------------------------------------------------ */
$("#people-sync-button")?.addEventListener("click", sync);
$("#people-search")?.addEventListener("input", (event) => { view.query = event.target.value; render(); });
document.querySelectorAll("[data-people-view]").forEach((button) => button.addEventListener("click", () => { view.mode = button.dataset.peopleView; render(); }));
$("#person-edit-form")?.addEventListener("submit", savePerson);
$("#person-edit-reset")?.addEventListener("click", resetPerson);
["#person-edit-close", "#person-edit-cancel"].forEach((selector) => $(selector)?.addEventListener("click", () => $("#person-edit-dialog").close()));
document.addEventListener("prism:tab", (event) => { if (event.detail.tab === "settings") load(); });
document.querySelector('[data-subtab-target="teams"]').addEventListener("click", load);
document.addEventListener("prism:people-open", (event) => openPrismPeople(event.detail));
document.addEventListener("click", (event) => {
  if (event.target.closest('[data-subtab-target="people"]')) load();
});
load();
