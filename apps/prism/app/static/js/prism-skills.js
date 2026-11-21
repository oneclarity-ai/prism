// Shared library definitions and private onboarding skills; permissions remain in Tools.
import { agentApi } from "./api.js";
import { el, button, panel, empty, formDialog, chip } from "./workspace-ui.js";

const libraryUrl = "/api/v2/prisms/skills/library";
const skillUrl = (prism) => `/api/v2/prisms/${prism.id}/skills`;
const splitNames = (value) => [...new Set(String(value || "").split(",").map((name) => name.trim().toLowerCase()).filter(Boolean))];
const fail = (error) => window.prism?.setStatus?.(error.message, true);
const changed = () => document.dispatchEvent(new CustomEvent("prism:skills-changed"));

function fields(skill = {}) {
  return [
    { name: "name", label: "Skill name", required: true, maxLength: 120, value: skill.name },
    { name: "description", label: "What this skill does", required: true, maxLength: 500, value: skill.description },
    { name: "instructions", label: "Reusable instructions", type: "textarea", required: true, maxLength: 2000, value: skill.instructions },
    { name: "required_tools", label: "Required tool identifiers, separated by commas", value: skill.required_tools?.join(", "), placeholder: "For example: teams_read_chat, save_file" },
    { name: "required_connections", label: "Required connections, separated by commas", value: skill.required_connections?.join(", "), placeholder: "For example: teams, computer, outlook" },
  ];
}
const content = (values) => ({ ...values, required_tools: splitNames(values.required_tools), required_connections: splitNames(values.required_connections) });

export function editSkill(skill, reload) {
  formDialog(skill ? "Edit shared skill" : "Add shared skill", fields(skill || {}), async (values) => {
    await agentApi(skill ? `${libraryUrl}/${skill.id}` : libraryUrl, {
      method: skill ? "PUT" : "POST",
      body: JSON.stringify({ ...content(values), ...(skill ? { expected_revision: skill.revision, archived: skill.archived } : {}) }),
    });
    changed(); await reload();
  }, { description: "Shared workspace instructions. Keep private details out. Saving never changes tool access. Library edits require explicit adoption by each Prism." });
}

export async function skillLibrary(root) {
  root.replaceChildren(el("p", "panel-note", "Loading skills…"));
  const reload = () => skillLibrary(root);
  try {
    const skills = await agentApi(libraryUrl);
    if (!root.isConnected) return;
    const head = panel("Workspace skills", "Reusable know-how for every department. Each Prism chooses its own skills and keeps its context private.");
    head.append(button("Add skill", () => editSkill(null, reload), { glyph: "plus", className: "button" }));
    const list = el("div", "skill-list");
    if (!skills.length) list.append(empty("No shared skills yet", "Add reusable instructions here. Skills created from onboarding stay private in each Prism’s settings.", "brain"));
    for (const skill of skills) {
      const card = el("article", "skill-row");
      const info = el("div", "skill-info");
      info.append(el("strong", "", skill.name), chip(skill.archived ? "Archived skill" : "Skill", "gray"), el("p", "panel-note", skill.description));
      const details = el("details"); details.append(el("summary", "", `Instructions · revision ${skill.revision}`), el("p", "skill-instructions", skill.instructions));
      info.append(details);
      if (skill.required_tools.length || skill.required_connections.length) info.append(el("p", "panel-note", `Requires: ${[...skill.required_tools, ...skill.required_connections].join(", ")}`));
      const actions = el("div", "skill-actions");
      actions.append(button("Edit", () => editSkill(skill, reload), { glyph: "pencil" }), button(skill.archived ? "Restore" : "Archive", async () => {
        const yes = await window.prism?.askDialog?.({ title: skill.archived ? "Restore this skill?" : "Archive this shared skill?", message: skill.archived ? "It becomes available in the library. Review its assignments before using it again." : "It stops being used by every Prism. Their chat history and tool permissions stay intact.", confirmLabel: skill.archived ? "Restore" : "Archive" });
        if (!yes) return;
        try { await agentApi(`${libraryUrl}/${skill.id}`, { method: "PUT", body: JSON.stringify({ ...content(Object.fromEntries(fields(skill).map((field) => [field.name, field.value]))), expected_revision: skill.revision, archived: !skill.archived }) }); changed(); await reload(); }
        catch (error) { fail(error); }
      }));
      card.append(info, actions); list.append(card);
    }
    root.replaceChildren(head, list);
  } catch (error) {
    root.replaceChildren(empty("Skills could not load", error.message, "brain"), button("Try again", reload));
  }
}

export async function createSkillsFromOnboarding(prism) {
  const result = await agentApi(`${skillUrl(prism)}/from-onboarding`, { method: "POST", body: "{}" });
  changed();
  window.prism?.setStatus?.(result.skills_created ? "3 skills created from onboarding. Edit them here in Skills." : "Your existing skills are already configured.");
  return result;
}

function editPrivateSkill(prism, skill, reload) {
  formDialog("Edit skill", fields(skill), async (values) => {
    await agentApi(`${skillUrl(prism)}/${skill.id}/definition`, {
      method: "PUT", body: JSON.stringify({ ...content(values), expected_revision: skill.revision, expected_assignment_revision: skill.assignment_revision, archived: skill.archived }),
    });
    changed(); await reload();
  }, { description: `Changes apply only to ${prism.name}, starting with its next task. Tool access and action approvals stay unchanged.` });
}

export async function prismSkillRows(root, prism, onCount = () => {}) {
  root.replaceChildren(el("p", "panel-note", "Loading skills…"));
  const reload = () => prismSkillRows(root, prism, onCount);
  try {
    const data = await agentApi(skillUrl(prism));
    if (!root.isConnected) return;
    const readonly = prism.state === "archived";
    const assigned = data.skills.filter((skill) => skill.assignment_revision);
    const available = data.skills.filter((skill) => !skill.assignment_revision && !skill.archived);
    const enabled = assigned.filter((skill) => skill.enabled);
    onCount(enabled.length);
    const labels = data.tool_labels || {};
    const readable = (value) => labels[value] || value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
    const issueLabel = (issue) => {
      if (issue.startsWith("Tool access is off: ")) return `Enable ${readable(issue.slice(20))} in Tools`;
      if (issue.startsWith("Connection not supported yet: ")) return `${readable(issue.slice(30))} integration is not available yet`;
      return issue;
    };
    const stats = el("div", "skill-stats");
    for (const [value, label] of [[enabled.length, "Enabled skills"], [enabled.filter((skill) => skill.missing.length).length, "Need access"], [available.length, "In workspace library"]]) {
      const stat = el("div", "skill-stat"); stat.append(el("strong", "", value), el("span", "panel-note", label)); stats.append(stat);
    }
    const toolbar = el("div", "skill-toolbar");
    toolbar.append(el("p", "panel-note", "Edit how this Prism works here. Manage app permissions separately in Tools."));
    if (!assigned.length) {
      const create = button("Create 3 skills from onboarding", async () => {
        create.disabled = true; create.setAttribute("aria-busy", "true");
        create.querySelector("span").textContent = "Creating skills…";
        try { await createSkillsFromOnboarding(prism); await reload(); }
        catch (error) { fail(error); create.disabled = false; create.querySelector("span").textContent = "Create 3 skills from onboarding"; }
        finally { create.removeAttribute("aria-busy"); }
      }, { glyph: "plus", className: "button" });
      create.disabled = readonly || prism.state !== "active";
      toolbar.append(create);
      if (prism.state !== "active" && !readonly) toolbar.append(el("p", "panel-note", "Finish onboarding in chat to create your first three skills."));
    }
    const list = el("div", "prism-skill-grid");
    async function apply(skill, enable, trigger) {
      trigger.disabled = true;
      try {
        await agentApi(`${skillUrl(prism)}/${skill.id}`, { method: "PUT", body: JSON.stringify({ enabled: enable, expected_skill_revision: skill.revision, expected_assignment_revision: skill.assignment_revision }) });
        changed(); await reload();
      } catch (error) { fail(error); trigger.disabled = readonly || skill.archived; }
    }
    function card(skill, inLibrary = false) {
      const approved = skill.enabled ? skill.approved_definition : skill;
      const row = el("article", "prism-skill-card");
      const head = el("div", "prism-skill-heading");
      head.append(el("h4", "", approved.name), chip(skill.archived ? "Archived" : skill.enabled ? (skill.missing.length ? "Needs access" : "Enabled") : "Not enabled", skill.enabled && !skill.missing.length ? "green" : "gray"));
      row.append(head, el("p", "panel-note", approved.description));
      row.append(el("small", "panel-note", skill.owner_prism_id ? "Private to this Prism · From onboarding" : "From workspace library"));
      const instructions = el("details");
      instructions.append(el("summary", "", "Instructions"), el("p", "skill-instructions", approved.instructions));
      row.append(instructions);
      if (skill.missing.length) {
        const requirements = el("details", "skill-requirements");
        requirements.append(el("summary", "", `${skill.missing.length} access ${skill.missing.length === 1 ? "requirement" : "requirements"}`));
        const issues = el("ul"); skill.missing.forEach((issue) => issues.append(el("li", "", issueLabel(issue))));
        requirements.append(issues); row.append(requirements);
      }
      const actions = el("div", "skill-actions");
      if (!inLibrary) {
        const edit = button("Edit skill", () => skill.owner_prism_id ? editPrivateSkill(prism, skill, reload) : editSkill(skill, reload), { glyph: "pencil" });
        edit.disabled = readonly || skill.archived; actions.append(edit);
      }
      const toggle = button(skill.enabled ? "Disable" : "Enable", () => apply(skill, !skill.enabled, toggle));
      toggle.setAttribute("aria-label", `${skill.enabled ? "Disable" : "Enable"} ${approved.name}`);
      toggle.setAttribute("aria-pressed", String(skill.enabled)); toggle.disabled = readonly || skill.archived;
      actions.append(toggle);
      if (skill.enabled && skill.approved_revision !== skill.revision) {
        row.append(el("p", "panel-note", `Using revision ${skill.approved_revision}. Library revision ${skill.revision} is available.`));
        const update = button("Review update", async () => {
          const yes = await window.prism?.askDialog?.({ title: `Use revision ${skill.revision} of ${skill.name}?`, message: `${skill.description}\n\n${skill.instructions}\n\nRequires: ${[...skill.required_tools, ...skill.required_connections].map(readable).join(", ") || "no additional tools"}`, confirmLabel: "Use this revision" });
          if (yes) await apply(skill, true, update);
        });
        update.disabled = readonly; actions.append(update);
      }
      row.append(actions); return row;
    }
    assigned.forEach((skill) => list.append(card(skill)));
    if (!assigned.length) list.append(empty("Your skills will appear here", "Three skills are created from your confirmed chat onboarding. No extra questions are needed.", "brain"));
    const library = el("details", "skill-library-picker");
    library.append(el("summary", "", `Workspace library · ${available.length} available`));
    const libraryGrid = el("div", "prism-skill-grid"); available.forEach((skill) => libraryGrid.append(card(skill, true)));
    if (!available.length) libraryGrid.append(el("p", "panel-note", "No additional shared skills."));
    library.append(libraryGrid);
    const add = button("Add shared skill", () => editSkill(null, reload), { glyph: "plus" }); add.disabled = readonly; library.append(add);
    root.replaceChildren(stats, toolbar, list, library);
  } catch (error) { root.replaceChildren(empty("Skills unavailable", error.message, "brain"), button("Try again", reload)); }
}

// Kept as a compatibility export for older dashboard callers; no questionnaire is opened.
export async function openSkillSetup(prism, onComplete = async () => {}) {
  try { await createSkillsFromOnboarding(prism); await onComplete(); } catch (error) { fail(error); }
}
