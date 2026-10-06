const savedTab = localStorage.getItem("manager-agent-tab");
const state = { employees: [], projects: [], tasks: [], blockers: [], commitments: [], escalations: [], journeys: [], knowledge: [], memoryFacts: [], memoryEpisodes: [], attention: [], agentRuns: [], brief: null, teamsConversationIds: new Set(), microsoft: null, activeTab: savedTab === "records" ? "knowledge" : (savedTab || "overview") };
let selectedCommitmentId = null;
let editingKnowledgeId = null;
const operatorTokenKey = "manager-agent-operator-token";

const $ = (selector) => document.querySelector(selector);
const today = () => new Date().toISOString().slice(0, 10);

function setStatus(message, isError = false) {
  const element = $("#status-message");
  element.textContent = message;
  element.classList.toggle("error", isError);
}

function setActiveTab(tab) {
  state.activeTab = tab;
  localStorage.setItem("manager-agent-tab", tab);
  document.querySelectorAll("[data-tab]").forEach((panel) => {
    panel.hidden = panel.dataset.tab !== tab;
  });
  document.querySelectorAll("[data-tab-target]").forEach((button) => {
    const active = button.dataset.tabTarget === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  const layout = document.querySelector(".layout");
  if (layout) layout.classList.toggle("knowledge-active", tab === "knowledge");
}

async function api(path, options = {}) {
  const operatorToken = localStorage.getItem(operatorTokenKey);
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Manager-Operator-Token": operatorToken } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Request failed (" + response.status + ")");
  }
  return response.status === 204 ? null : response.json();
}

function setOperatorToken() {
  const current = localStorage.getItem(operatorTokenKey);
  const value = window.prompt(
    current
      ? "Replace the operator access key. Leave blank to remove it from this browser."
      : "Enter the operator access key from your local .env file.",
    "",
  );
  if (value === null) return;
  if (value.trim()) {
    localStorage.setItem(operatorTokenKey, value.trim());
    setStatus("Operator access key saved in this browser.");
  } else {
    localStorage.removeItem(operatorTokenKey);
    setStatus("Operator access key removed from this browser.");
  }
  loadDashboard();
}

function nameFor(id) {
  const employee = state.employees.find((item) => item.id === id);
  return employee ? employee.name : "Unassigned";
}

function dateTime(value) {
  return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "No deadline";
}

function renderList(selector, items, render, emptyText) {
  const container = $(selector);
  if (!items.length) {
    container.className = "list empty-state";
    container.textContent = emptyText;
    return;
  }
  container.className = "list";
  container.innerHTML = items.map(render).join("");
}

function item(title, meta) {
  return `<div class="list-item"><strong>${escapeHtml(title)}</strong><div class="meta">${escapeHtml(meta)}</div></div>`;
}

function itemWithActions(title, meta, actions) {
  return `<div class="list-item"><strong>${escapeHtml(title)}</strong><div class="meta">${escapeHtml(meta)}</div>${actions ? `<div class="item-actions">${actions}</div>` : ""}</div>`;
}

function humanize(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderAttention(entries) {
  const container = $("#intelligence-attention-list");
  $("#intelligence-attention-count").textContent = entries.length;
  if (!entries.length) {
    container.className = "attention-list empty-state";
    container.textContent = "Nothing currently needs your intervention.";
    return;
  }
  container.className = "attention-list";
  container.innerHTML = entries.map((entry) => {
    const risk = entry.risk;
    const people = entry.people.length ? entry.people.join(", ") : "No person linked";
    const actions = entry.agent_actions.length ? entry.agent_actions.join(" · ") : "No agent action recorded yet";
    return `<article class="attention-card ${escapeHtml(risk.severity)}">
      <div class="attention-card-heading"><span class="risk-level">${escapeHtml(humanize(risk.severity))}</span><span>${escapeHtml(people)}</span></div>
      <h3>${escapeHtml(risk.summary)}</h3>
      <p>${escapeHtml(entry.impact)}</p>
      <dl><div><dt>Agent action</dt><dd>${escapeHtml(actions)}</dd></div><div><dt>Expected now</dt><dd>${escapeHtml(entry.current_expectation)}</dd></div><div><dt>Why you see this</dt><dd>${escapeHtml(entry.why_visible)}</dd></div></dl>
      ${entry.manager_options.length ? `<div class="manager-options">${entry.manager_options.map((option) => `<span>${escapeHtml(option)}</span>`).join("")}</div>` : ""}
    </article>`;
  }).join("");
}

function renderBrief(brief) {
  state.brief = brief;
  $("#intelligence-brief-date").textContent = new Date(`${brief.date}T00:00:00`).toLocaleDateString([], { dateStyle: "medium" });
  const sections = [
    ["Needs attention", brief.needs_attention],
    ["Important changes", brief.important_changes],
    ["Completed", brief.completed],
    ["In progress", brief.in_progress],
    ["New blockers", brief.new_blockers],
    ["Resolved blockers", brief.resolved_blockers],
    ["Missed commitments", brief.missed_commitments],
    ["Changed ETAs", brief.changed_etas],
    ["Dependencies at risk", brief.dependencies_at_risk],
    ["People waiting", brief.people_waiting],
    ["No action required", brief.no_action_required],
  ].filter(([, values]) => values && values.length);
  const container = $("#intelligence-brief");
  if (!sections.length) {
    container.className = "brief-grid empty-state";
    container.textContent = "No material management changes recorded today.";
    return;
  }
  container.className = "brief-grid";
  container.innerHTML = sections.map(([title, values]) => `<section class="brief-section"><h3>${escapeHtml(title)}</h3><ul>${values.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul></section>`).join("");
}

function renderManagementAnswer(result) {
  const container = $("#management-query-results");
  container.hidden = false;
  const evidence = result.evidence?.length
    ? `<details><summary>Evidence (${result.evidence.length})</summary><ul>${result.evidence.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul></details>`
    : "";
  container.innerHTML = `<span class="answer-type">${escapeHtml(humanize(result.answer_type))}</span><p>${escapeHtml(result.answer)}</p>${result.uncertainty ? `<p class="query-uncertainty">${escapeHtml(result.uncertainty)}</p>` : ""}${evidence}`;
}

function categoryLabel(category) {
  return {
    team: "Team context",
    work: "Current work",
    people: "Person or role",
    communication: "Communication preference",
    escalation: "Escalation guidance",
    other: "Other",
  }[category] || "Other";
}

function renderKnowledge(entries) {
  const container = $("#knowledge-list");
  $("#knowledge-count").textContent = entries.length;
  if (!entries.length) {
    container.className = "knowledge-list empty-state";
    container.textContent = "No context saved yet. Add something the agent should remember.";
    return;
  }
  container.className = "knowledge-list";
  container.innerHTML = entries.map((entry) => `
    <article class="knowledge-entry">
      <div class="knowledge-entry-heading">
        <span class="knowledge-category ${escapeHtml(entry.category)}">${escapeHtml(categoryLabel(entry.category))}</span>
        <time>${escapeHtml(dateTime(entry.updated_at))}</time>
      </div>
      <h3>${escapeHtml(entry.title)}</h3>
      <p>${escapeHtml(entry.content).replace(/\n/g, "<br>")}</p>
      <div class="knowledge-entry-actions">
        ${entry.title.toLowerCase().startsWith("deployment list") ? `<button class="mini-button" type="button" data-knowledge-action="distribute" data-id="${entry.id}">Distribute list</button>` : ""}
        <button class="mini-button" type="button" data-knowledge-action="edit" data-id="${entry.id}">Edit</button>
        <button class="mini-button danger-button" type="button" data-knowledge-action="delete" data-id="${entry.id}">Delete</button>
      </div>
    </article>
  `).join("");
}

function firstName(name) {
  return String(name || "").trim().split(/\s+/)[0] || "Team member";
}

function initials(name) {
  return String(name || "M").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "M";
}

function renderJourneys(journeys) {
  const container = $("#journeys-list");
  $("#journeys-count").textContent = journeys.length;
  if (!journeys.length) {
    container.className = "journeys empty-state";
    container.textContent = "No blocker journeys recorded yet.";
    return;
  }
  container.className = "journeys";
  container.innerHTML = journeys.map((journey) => {
    const owner = journey.dependency_owner_name || "owner not identified yet";
    const status = journey.status === "resolved" ? "Resolved" : "Open";
    const events = journey.events.map((event, index) => `
      <li class="journey-event ${escapeHtml(event.event_type)}">
        <span class="journey-number">${index + 1}</span>
        <div class="journey-event-body">
          <div class="journey-event-heading"><span class="journey-tag">${escapeHtml(event.event_type.replaceAll("_", " "))}</span><strong>${escapeHtml(event.title)}</strong><time>${escapeHtml(dateTime(event.occurred_at))}</time></div>
          <p>${escapeHtml(event.detail)}</p>
        </div>
      </li>`).join("");
    const commitments = journey.commitments.length ? `<div class="journey-commitments">${journey.commitments.map((commitment) => `<span><strong>${escapeHtml(commitment.owner_name)}</strong> committed: ${escapeHtml(commitment.description)} · due ${escapeHtml(dateTime(commitment.deadline))} · ${escapeHtml(commitment.status)}</span>`).join("")}</div>` : "";
    return `<details class="journey-card">
      <summary class="journey-summary"><div><span class="journey-status ${journey.status === "resolved" ? "resolved" : "open"}">${status}</span><h3>${escapeHtml(journey.title)}</h3><p>${escapeHtml(journey.description)}</p></div><div class="journey-people"><span>Blocked: ${escapeHtml(firstName(journey.blocked_employee_name))}</span><span>Dependency: ${escapeHtml(firstName(owner))}</span></div></summary>
      <div class="journey-history"><ol class="journey-events">${events}</ol>${commitments}</div>
    </details>`;
  }).join("");
}

function renderMemory(facts, episodes) {
  state.memoryFacts = facts;
  state.memoryEpisodes = episodes;
  renderList("#memory-facts-list", facts, (fact) => item(
    `${fact.subject_text || fact.subject_type} ${String(fact.predicate || "").replaceAll("_", " ")} ${fact.object_text || fact.object_type || ""}`,
    `${fact.status} · observed ${dateTime(fact.observed_at)}`,
  ), "No derived facts yet. Use Update memory after management activity is recorded.");
  renderList("#memory-episodes-list", episodes, (episode) => item(
    episode.title,
    `${episode.summary} · ${dateTime(episode.started_at)}`,
  ), "No memory episodes yet.");
  const select = $("#memory-employee-select");
  const selected = select.value;
  select.innerHTML = `<option value="">Choose a team member</option>${state.employees.map((employee) => `<option value="${employee.id}">${escapeHtml(employee.name)}</option>`).join("")}`;
  select.value = selected;
}

function renderMemorySearch(results) {
  const container = $("#memory-search-results");
  container.hidden = false;
  const facts = results.facts || [];
  const episodes = results.episodes || [];
  if (!facts.length && !episodes.length) {
    container.innerHTML = `<p class="memory-search-empty">Nothing matched that search yet.</p>`;
    return;
  }
  container.innerHTML = `${facts.length ? `<div><strong>Facts</strong>${facts.map((fact) => `<p>${escapeHtml(`${fact.subject_text || fact.subject_type} ${String(fact.predicate || "").replaceAll("_", " ")} ${fact.object_text || fact.object_type || ""}`)}</p>`).join("")}</div>` : ""}${episodes.length ? `<div><strong>Past situations</strong>${episodes.map((episode) => `<p>${escapeHtml(episode.title)}<span>${escapeHtml(episode.summary)}</span></p>`).join("")}</div>` : ""}`;
}

function renderTeamsActivity(messages) {
  const container = $("#teams-activity-list");
  $("#teams-activity-count").textContent = messages.length;
  if (!messages.length) {
    container.className = "list empty-state";
    container.textContent = "No Teams messages recorded yet.";
    return;
  }
  const activityItem = (message) => {
    const direction = message.direction === "outbound" ? "Sent to" : "Received from";
    const delivery = message.delivery_status === "failed" ? "Failed" : message.delivery_status === "delivered" ? "Delivered" : "Recorded";
    const when = message.external_created_at || message.created_at;
    return item(`${direction} ${nameFor(message.employee_id)} · ${delivery}`, `${message.content} · ${dateTime(when)}`);
  };
  const recent = messages.slice(0, 5);
  const earlier = messages.slice(5);
  container.className = "teams-activity-feed";
  container.innerHTML = `<div class="list">${recent.map(activityItem).join("")}</div>${earlier.length ? `<details class="activity-history"><summary>Show ${earlier.length} earlier message${earlier.length === 1 ? "" : "s"}</summary><div class="list">${earlier.map(activityItem).join("")}</div></details>` : ""}`;
}

function renderAgentHealth(runs) {
  const actionable = runs.filter((run) => run.status === "failed" || run.status === "pending" || run.needs_manager_review);
  $("#agent-health-count").textContent = actionable.length;
  renderList("#agent-health-list", actionable, (run) => {
    const employee = nameFor(run.source_employee_id);
    const retry = run.next_retry_at ? `Next retry: ${dateTime(run.next_retry_at)}` : "No automatic retry scheduled";
    const stateNote = run.state_applied ? "Operational state applied" : "Operational state not applied";
    return item(
      `${employee} · ${humanize(run.status)}`,
      `${run.failure_reason || "Processing has not completed"} · Attempts: ${run.attempt_count} · ${stateNote} · ${retry}`,
    );
  }, "No failed or pending replies.");
}

function actionButton(label, action, id) {
  const help = {
    "daily-reminder": "Send this person a simple Teams reminder for today's update.",
    "resolve-blocker": "Mark this blocker as fixed.",
    "blocker-follow-up": "Send the dependency owner a Teams follow-up.",
    "mark-missed": "Mark this commitment as missed.",
    "revise-commitment": "Keep the old promise and enter a new deadline.",
    "acknowledge-escalation": "Mark that you have seen this escalation.",
    "resolve-escalation": "Close this escalation as resolved.",
  }[action] || "Perform this action.";
  return `<button class="mini-button" type="button" data-action="${action}" data-id="${id}" data-tooltip="${escapeHtml(help)}">${escapeHtml(label)}</button>`;
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function renderTeamsAutomation() {
  const microsoft = state.microsoft;
  if (!microsoft) return;
  const activeRun = microsoft.active_run;
  const managedEmployees = state.employees.filter((employee) => employee.is_managed);
  const importedEmployees = state.employees.filter((employee) => employee.teams_user_id);
  const availableEmployees = importedEmployees.filter((employee) => !employee.is_managed);
  const badge = $("#teams-automation-badge");
  const summary = $("#teams-automation-summary");
  const senderIdentity = $("#teams-sender-identity");
  const accountName = $("#account-menu-name");
  const accountEmail = $("#account-menu-email");
  const accountAvatar = $("#account-avatar");

  if (microsoft.is_connected && microsoft.connection) {
    senderIdentity.hidden = false;
    senderIdentity.textContent = `Sending Teams messages as: ${microsoft.connection.display_name} (${microsoft.connection.user_principal_name})`;
    accountName.textContent = microsoft.connection.display_name;
    accountEmail.textContent = microsoft.connection.user_principal_name;
    accountAvatar.textContent = initials(microsoft.connection.display_name);
  } else {
    senderIdentity.hidden = true;
    senderIdentity.textContent = "";
    accountName.textContent = "Microsoft account";
    accountEmail.textContent = "No Microsoft account connected";
    accountAvatar.textContent = "M";
  }

  if (activeRun) {
    badge.textContent = "Running";
    summary.textContent = `${activeRun.delivered_count}/${activeRun.target_count} first messages delivered. ${microsoft.listener_expires_at ? `Reply listener expires ${dateTime(microsoft.listener_expires_at)}.` : "No active reply listener."}`;
  } else if (microsoft.is_connected) {
    badge.textContent = "Connected";
    summary.textContent = `Connected as ${microsoft.connection.display_name} (${microsoft.connection.user_principal_name}). ${managedEmployees.length} employee(s) selected for management.`;
  } else {
    badge.textContent = "Setup";
    summary.textContent = microsoft.is_auth_configured
      ? "Microsoft account is not connected yet."
      : "Add the Microsoft settings to .env, then restart the API.";
  }

  const connectButton = $("#connect-microsoft-button");
  connectButton.disabled = !microsoft.is_auth_configured;
  connectButton.textContent = microsoft.is_connected ? "Switch Microsoft account" : "Connect Microsoft account";
  $("#sync-directory-button").disabled = !microsoft.is_connected;
  const automationButton = $("#toggle-automation-button");
  const automationLabel = $("#automation-toggle-label");
  const canStart = microsoft.is_configured && microsoft.is_connected && managedEmployees.length;
  automationButton.disabled = activeRun ? false : !canStart;
  automationButton.classList.toggle("is-running", Boolean(activeRun));
  automationButton.setAttribute("aria-label", activeRun ? "Stop automation" : "Start automation");
  automationButton.setAttribute("data-tooltip", activeRun
    ? "Pause the agent and stop listening for Teams replies."
    : "Start the agent and send the first Teams check-in to selected people.");
  automationLabel.textContent = activeRun ? "Stop automation" : "Start automation";
  $("#run-cycle-button").disabled = !microsoft.is_configured || !microsoft.is_connected || !activeRun;
  $("#send-digest-email-button").disabled = !microsoft.is_connected;
  $("#renew-listener-button").disabled = !activeRun;

  const teamMember = (employee) => {
    const nextValue = employee.is_managed ? "false" : "true";
    const actionLabel = employee.is_managed ? "Remove from managed team" : "Manage this person";
    const help = employee.is_managed
      ? "Stop including this person in the agent's check-ins."
      : "Include this person in the agent's check-ins.";
    return `<div class="list-item team-member"><div><strong>${escapeHtml(employee.name)}</strong><div class="meta">${escapeHtml(employee.email)} · ${escapeHtml(employee.title || employee.role)}</div></div><button class="mini-button" type="button" data-action="toggle-managed" data-id="${employee.id}" data-managed="${nextValue}" data-tooltip="${help}">${escapeHtml(actionLabel)}</button></div>`;
  };
  $("#managed-people-count").textContent = managedEmployees.length;
  $("#available-people-count").textContent = availableEmployees.length;
  renderList("#managed-team-list", managedEmployees, teamMember, "No people selected yet.");
  renderList("#available-team-list", availableEmployees, teamMember, "Everyone imported from the organization is already managed.");
}

async function loadDashboard() {
  setStatus("Refreshing…");
  api("/api/v1/usage/llm/today").then((usage) => {
    const amount = Number(usage.estimated_cost_usd).toFixed(4);
    $("#ai-cost-today").textContent = usage.complete
      ? `Today's AI cost: $${amount}`
      : `Today's AI cost: $${amount} + unpriced usage`;
    $("#ai-cost-today").title = `${usage.calls} calls · ${usage.timezone}. ${usage.unpriced_calls} calls missing pricing or token usage. Estimated from provider tokens.`;
  }).catch(() => { $("#ai-cost-today").textContent = "Today's AI cost: unavailable"; });
  try {
    const [employees, projects, tasks, updates, blockers, commitments, escalations, findings, journeys, knowledge, microsoft, teamsConversations, messages, memoryFacts, memoryEpisodes, attention, brief, agentRuns] = await Promise.all([
      api("/api/v1/employees?limit=100&is_active=true"),
      api("/api/v1/projects?limit=100"),
      api("/api/v1/tasks?limit=100"),
      api("/api/v1/daily-updates?limit=100&update_date=" + today()),
      api("/api/v1/blockers?limit=100&status=open"),
      api("/api/v1/commitments?limit=100&status=open"),
      api("/api/v1/escalations?limit=100&status=open"),
      api("/api/v1/management/rule-findings"),
      api("/api/v1/management/journeys"),
      api("/api/v1/management-context?limit=100"),
      api("/api/v1/microsoft/status"),
      api("/api/v1/conversations?limit=100&channel=teams"),
      api("/api/v1/messages?limit=100"),
      api("/api/v1/memory/facts?limit=12&status=current"),
      api("/api/v1/memory/episodes?limit=8"),
      api("/api/v2/management/attention"),
      api("/api/v2/management/brief/daily"),
      api("/api/v1/microsoft/agent/runs?limit=30"),
    ]);
    Object.assign(state, {
      employees: employees.items,
      projects: projects.items,
      tasks: tasks.items,
      blockers: blockers.items,
      commitments: commitments.items,
      escalations: escalations.items,
      journeys,
      knowledge: knowledge.items,
      attention,
      agentRuns,
      brief,
      microsoft,
      teamsConversationIds: new Set(teamsConversations.items.map((conversation) => conversation.id)),
    });
    $("#stat-employees").textContent = employees.total;
    $("#stat-updates").textContent = updates.total;
    $("#stat-blockers").textContent = blockers.total;
    $("#stat-commitments").textContent = commitments.total;
    $("#stat-escalations").textContent = escalations.total;
    $("#findings-count").textContent = findings.length;

    renderTeamsAutomation();
    renderAgentHealth(agentRuns);
    renderJourneys(journeys);
    renderKnowledge(knowledge.items);
    renderMemory(memoryFacts.items, memoryEpisodes);
    renderAttention(attention);
    renderBrief(brief);

    const missingUpdates = employees.items.filter((employee) => !updates.items.some((update) => update.employee_id === employee.id));
    $("#missing-updates-count").textContent = missingUpdates.length;
    renderList("#missing-updates-list", missingUpdates, (employee) => itemWithActions(
      employee.name,
      `${employee.role} has not sent an update today.`,
      actionButton("Record Teams reminder", "daily-reminder", employee.id),
    ), "Everyone has submitted an update today.");
    renderList("#findings-list", findings, (finding) => item(finding.reason, finding.severity.replace("_", " ")), "No active rule findings.");
    renderList("#blockers-list", blockers.items, (blocker) => {
      const actions = [actionButton("Mark resolved", "resolve-blocker", blocker.id)];
      if (blocker.dependency_owner_id) actions.push(actionButton("Record Teams follow-up", "blocker-follow-up", blocker.id));
      const blockedPerson = nameFor(blocker.blocked_employee_id);
      const dependencyOwner = (blocker.dependency_owner_ids || []).map(nameFor).join(", ") || "Not assigned";
      return itemWithActions(blocker.description, `Blocked: ${blockedPerson} · Dependency owner: ${dependencyOwner} · Severity: ${blocker.severity}`, actions.join(""));
    }, "No open blockers.");
    renderList("#commitments-list", commitments.items, (commitment) => itemWithActions(
      commitment.description,
      `Responsible: ${nameFor(commitment.employee_id)} · Deadline: ${dateTime(commitment.deadline)} · Status: ${commitment.status}`,
      `${actionButton("Mark missed", "mark-missed", commitment.id)}${actionButton("Missed + revised ETA", "revise-commitment", commitment.id)}`,
    ), "No open commitments.");
    renderList("#updates-list", updates.items, (update) => item(nameFor(update.employee_id), update.today_summary), "No updates received today.");
    renderList("#escalations-list", escalations.items, (escalation) => itemWithActions(
      escalation.reason,
      `${escalation.escalation_type.replaceAll("_", " ")} · ${escalation.severity}`,
      `${actionButton("Acknowledge", "acknowledge-escalation", escalation.id)}${actionButton("Resolve", "resolve-escalation", escalation.id)}`,
    ), "No open escalations.");
    const teamsMessages = messages.items.filter((message) => state.teamsConversationIds.has(message.conversation_id));
    renderTeamsActivity(teamsMessages);
    renderSelectedForm();
    setStatus("");
  } catch (error) {
    setStatus(error.message + ". Check that the API and database are running.", true);
  }
}

function optionMarkup(type) {
  const records = state[type] || [];
  if (type === "employees") return records.map((employee) => `<option value="${employee.id}">${escapeHtml(employee.name)} — ${escapeHtml(employee.role)}</option>`).join("");
  if (type === "projects") return records.map((project) => `<option value="${project.id}">${escapeHtml(project.name)}</option>`).join("");
  if (type === "tasks") return records.map((task) => `<option value="${task.id}">${escapeHtml(task.title)}</option>`).join("");
  if (type === "blockers") return records.map((blocker) => `<option value="${blocker.id}">${escapeHtml(blocker.description.slice(0, 70))}</option>`).join("");
  return "";
}

function renderSelectedForm() {
  const kind = $("#form-selector").value;
  const template = $("#" + kind + "-form");
  const container = $("#form-container");
  container.innerHTML = "";
  container.append(template.content.cloneNode(true));
  container.querySelectorAll("[data-options]").forEach((select) => {
    select.insertAdjacentHTML("beforeend", optionMarkup(select.dataset.options));
  });
  container.querySelectorAll("[data-today]").forEach((input) => { input.value = today(); });
  container.querySelector("form").addEventListener("submit", submitForm);
}

function payloadFor(form) {
  const payload = {};
  new FormData(form).forEach((value, key) => {
    const normalized = String(value).trim();
    if (!normalized) return;
    payload[key] = normalized;
  });
  if (payload.deadline) payload.deadline = new Date(payload.deadline).toISOString();
  return payload;
}

async function submitForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    await api(form.dataset.endpoint, { method: "POST", body: JSON.stringify(payloadFor(form)) });
    form.reset();
    setStatus("Saved successfully.");
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function submitKnowledgeContext(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const data = new FormData(form);
  const payload = {
    category: String(data.get("category") || "").trim(),
    title: String(data.get("title") || "").trim(),
    content: String(data.get("content") || "").trim(),
  };
  button.disabled = true;
  try {
    const isEditing = Boolean(editingKnowledgeId);
    await api(
      isEditing ? `/api/v1/management-context/${editingKnowledgeId}` : "/api/v1/management-context",
      { method: isEditing ? "PATCH" : "POST", body: JSON.stringify(payload) },
    );
    resetKnowledgeForm();
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function resetKnowledgeForm() {
  editingKnowledgeId = null;
  const form = $("#knowledge-context-form");
  form.reset();
  $("#knowledge-submit-button").textContent = "Save context";
  $("#cancel-knowledge-edit").hidden = true;
}

function editKnowledge(entryId) {
  const entry = state.knowledge.find((item) => item.id === entryId);
  if (!entry) return;
  editingKnowledgeId = entry.id;
  const form = $("#knowledge-context-form");
  form.elements.category.value = entry.category;
  form.elements.title.value = entry.title;
  form.elements.content.value = entry.content;
  $("#knowledge-submit-button").textContent = "Update context";
  $("#cancel-knowledge-edit").hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  form.elements.title.focus();
}

async function deleteKnowledge(entryId) {
  const entry = state.knowledge.find((item) => item.id === entryId);
  if (!entry || !window.confirm(`Delete “${entry.title}” from the agent's saved knowledge?`)) return;
  try {
    await api(`/api/v1/management-context/${entryId}`, { method: "DELETE" });
    if (editingKnowledgeId === entryId) resetKnowledgeForm();
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function distributeDeploymentList(entryId) {
  const entry = state.knowledge.find((item) => item.id === entryId);
  if (!entry || !window.confirm(
    `Distribute “${entry.title}” to its owners in the active automation run?`
  )) return;
  try {
    const result = await api(
      `/api/v1/management-context/${entryId}/distribute-deployment-list`,
      { method: "POST" },
    );
    const failureText = result.failures.length ? ` ${result.failures.length} delivery failure(s); task state was not changed.` : "";
    setStatus(`Deployment list: ${result.delivered.length} delivered, ${result.skipped.length} already delivered, ${result.task_changes} task change(s).${failureText}`, Boolean(result.failures.length));
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function recordMessageIntent(employeeId, content) {
  await api("/api/v1/message-intents", {
    method: "POST",
    body: JSON.stringify({ employee_id: employeeId, channel: "teams", content }),
  });
  setStatus("Teams follow-up recorded locally. It has not been sent.");
}

async function handleAction(button) {
  const { action, id } = button.dataset;
  button.disabled = true;
  try {
    if (action === "daily-reminder") {
      const employee = state.employees.find((item) => item.id === id);
      await recordMessageIntent(id, `Hi ${employee.name}, please share your daily update for today: what you completed, what you will deliver today, and any blockers.`);
    }
    if (action === "toggle-managed") {
      const managed = button.dataset.managed === "true";
      await api(`/api/v1/employees/${id}`, { method: "PATCH", body: JSON.stringify({ is_managed: managed }) });
      setStatus(managed ? "Employee added to the managed team." : "Employee removed from the managed team.");
    }
    if (action === "blocker-follow-up") {
      const blocker = state.blockers.find((item) => item.id === id);
      const owner = state.employees.find((item) => item.id === blocker.dependency_owner_id);
      await recordMessageIntent(owner.id, `Hi ${owner.name}, ${nameFor(blocker.blocked_employee_id)} is blocked: ${blocker.description} Please share a specific ETA.`);
    }
    if (action === "resolve-blocker") {
      if (!window.confirm("Mark this blocker as resolved?")) return;
      await api(`/api/v1/blockers/${id}`, { method: "PATCH", body: JSON.stringify({ status: "resolved" }) });
      setStatus("Blocker marked as resolved. Update the task status separately when work resumes.");
    }
    if (action === "mark-missed") {
      if (!window.confirm("Mark this commitment as missed?")) return;
      const reason = window.prompt("Why was it missed? You can leave this blank and add it with a revised ETA later.");
      if (reason === null) return;
      await api(`/api/v1/commitments/${id}/mark-missed`, { method: "POST", body: JSON.stringify(reason.trim() ? { reason: reason.trim() } : {}) });
      setStatus("Commitment marked as missed. It remains in its history.");
    }
    if (action === "revise-commitment") {
      selectedCommitmentId = id;
      $("#revision-form").reset();
      $("#revision-dialog").showModal();
      return;
    }
    if (action === "acknowledge-escalation") {
      await api(`/api/v1/escalations/${id}/acknowledge`, { method: "POST" });
      setStatus("Escalation acknowledged.");
    }
    if (action === "resolve-escalation") {
      if (!window.confirm("Resolve this escalation?")) return;
      await api(`/api/v1/escalations/${id}/resolve`, { method: "POST" });
      setStatus("Escalation resolved.");
    }
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function connectMicrosoft() {
  if (!state.microsoft || !state.microsoft.is_auth_configured) {
    setStatus("Add the Microsoft values and encryption key to .env, then restart the API.", true);
    return;
  }
  if (state.microsoft.is_connected && !window.confirm(
    `Switch from ${state.microsoft.connection.display_name} to a different Microsoft account? Teams automation must be stopped first.`
  )) return;
  window.location.assign("/api/v1/microsoft/auth/start");
}

async function syncMicrosoftDirectory() {
  const button = $("#sync-directory-button");
  button.disabled = true;
  try {
    const result = await api("/api/v1/microsoft/directory/sync", { method: "POST" });
    setStatus(`Directory imported: ${result.created} added, ${result.updated} updated, ${result.skipped} skipped.`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function startAutomation() {
  const button = $("#toggle-automation-button");
  button.disabled = true;
  try {
    const run = await api("/api/v1/microsoft/automation/start", { method: "POST", body: JSON.stringify({}) });
    setStatus(`Automation started. ${run.delivered_count}/${run.target_count} first Teams messages were delivered.`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function runDailyCycle() {
  if (!window.confirm("Run the daily check-in cycle now? It may send check-ins and due commitment/escalation actions, but not immediate no-response reminders or a digest.")) return;
  const button = $("#run-cycle-button");
  button.disabled = true;
  try {
    const result = await api("/api/v1/microsoft/automation/run-cycle?force=true", { method: "POST" });
    setStatus(`Daily cycle complete: ${result.checkins} check-ins, ${result.followups} reminders, ${result.missed} commitment actions, ${result.escalations} escalation actions, ${result.digests} digest(es), ${result.listeners} listener renewal(s).`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function sendDigestEmail() {
  if (!window.confirm("Email today's manager digest to the connected Microsoft account now?")) return;
  const button = $("#send-digest-email-button");
  button.disabled = true;
  try {
    const result = await api("/api/v1/microsoft/automation/send-digest-email", { method: "POST" });
    setStatus(`Manager digest sent to ${result.recipient}. Check Outlook shortly.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function renewTeamsListener() {
  const button = $("#renew-listener-button");
  button.disabled = true;
  try {
    const result = await api("/api/v1/microsoft/automation/renew-listener", { method: "POST" });
    setStatus(`Reply listener renewed for ${result.renewed} chat(s).${result.failed ? ` ${result.failed} failed.` : ""}`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function retryAgentRuns() {
  const button = $("#retry-agent-runs-button");
  button.disabled = true;
  try {
    const result = await api("/api/v1/microsoft/agent/process-pending?force=true", { method: "POST" });
    setStatus(`Processed ${result.processed} pending or failed repl${result.processed === 1 ? "y" : "ies"}.`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function stopAutomation() {
  if (!window.confirm("Stop Teams automation and remove the active reply listeners?")) return;
  const button = $("#toggle-automation-button");
  button.disabled = true;
  try {
    await api("/api/v1/microsoft/automation/stop", { method: "POST" });
    setStatus("Teams automation stopped.");
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function createDummyJourney() {
  const button = $("#create-dummy-journey-button");
  button.disabled = true;
  try {
    const result = await api("/api/v1/management/dummy-journey", { method: "POST" });
    state.journeys = [result.journey, ...state.journeys.filter((item) => item.blocker_id !== result.blocker_id)];
    renderJourneys(state.journeys);
    button.textContent = "Preview created";
    setStatus(result.message);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function consolidateMemory() {
  const button = $("#consolidate-memory-button");
  button.disabled = true;
  try {
    const backfill = await api("/api/v1/memory/backfill", { method: "POST" });
    const result = await api("/api/v1/memory/consolidate", { method: "POST" });
    const queued = Object.values(backfill).reduce((total, count) => total + count, 0);
    setStatus(`Memory updated: ${queued} existing record(s) queued; ${result.processed} event(s) processed, ${result.facts} fact(s), ${result.episodes} situation(s), and ${result.relations} relationship(s) added.`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function runIntelligence() {
  const button = $("#run-intelligence-button");
  button.disabled = true;
  try {
    const result = await api("/api/v2/management/intelligence/run", { method: "POST" });
    setStatus(`Intelligence refreshed: ${result.active_risks} active risk(s), ${result.decisions_created} new decision(s), ${result.no_action} no-action decision(s). No Teams messages were sent.`);
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function askManagementQuestion(event) {
  event.preventDefault();
  const input = $("#management-query-input");
  const button = event.currentTarget.querySelector("button[type=submit]");
  const question = input.value.trim();
  if (!question) return;
  button.disabled = true;
  try {
    renderManagementAnswer(await api("/api/v2/management/query", { method: "POST", body: JSON.stringify({ question }) }));
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function searchMemory(event) {
  event.preventDefault();
  const query = $("#memory-search-input").value.trim();
  if (!query) return;
  try {
    renderMemorySearch(await api(`/api/v1/memory/search?q=${encodeURIComponent(query)}&include_history=true`));
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadMemoryContext() {
  const employeeId = $("#memory-employee-select").value;
  if (!employeeId) return;
  const output = $("#memory-context-output");
  output.textContent = "Loading context…";
  try {
    const context = await api(`/api/v1/memory/context/${employeeId}`);
    const sections = [
      ["Current work", context.current_work],
      ["Current blockers", context.current_blockers],
      ["Open commitments", context.open_commitments],
      ["Relevant memory", context.relevant_facts],
      ["Past situations", context.relevant_episodes],
      ["Relationships", context.relevant_relations],
    ].filter(([, values]) => values && values.length);
    output.textContent = sections.length ? sections.map(([title, values]) => `${title}\n${values.map((value) => `- ${value}`).join("\n")}`).join("\n\n") : "No relevant context is available yet.";
  } catch (error) {
    output.textContent = "Could not load context.";
    setStatus(error.message, true);
  }
}

async function submitRevision(event) {
  event.preventDefault();
  const reason = $("#revision-reason").value.trim();
  const description = $("#revision-description").value.trim();
  const deadline = $("#revision-deadline").value;
  if (!selectedCommitmentId || !reason || !description || !deadline) return;
  try {
    await api(`/api/v1/commitments/${selectedCommitmentId}/mark-missed`, {
      method: "POST", body: JSON.stringify({ reason }),
    });
    await api(`/api/v1/commitments/${selectedCommitmentId}/revisions`, {
      method: "POST",
      body: JSON.stringify({ description, missed_reason: reason, deadline: new Date(deadline).toISOString() }),
    });
    $("#revision-dialog").close();
    selectedCommitmentId = null;
    setStatus("Missed commitment and revised ETA saved with full history.");
    await loadDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("manager-agent-theme", theme);
  const themeButton = $("#theme-toggle");
  const nextMode = theme === "dark" ? "light" : "dark";
  themeButton.setAttribute("aria-label", `Switch to ${nextMode} mode`);
  themeButton.setAttribute("data-tooltip", `Switch to ${nextMode} mode.`);
}

$("#theme-toggle").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
$("#refresh-button").addEventListener("click", loadDashboard);
$("#operator-token-button").addEventListener("click", setOperatorToken);
$("#connect-microsoft-button").addEventListener("click", connectMicrosoft);
$("#sync-directory-button").addEventListener("click", syncMicrosoftDirectory);
$("#toggle-automation-button").addEventListener("click", () => {
  if (state.microsoft && state.microsoft.active_run) return stopAutomation();
  return startAutomation();
});
$("#run-cycle-button").addEventListener("click", runDailyCycle);
$("#send-digest-email-button").addEventListener("click", sendDigestEmail);
$("#renew-listener-button").addEventListener("click", renewTeamsListener);
$("#retry-agent-runs-button").addEventListener("click", retryAgentRuns);
$("#create-dummy-journey-button").addEventListener("click", createDummyJourney);
$("#consolidate-memory-button").addEventListener("click", consolidateMemory);
$("#run-intelligence-button").addEventListener("click", runIntelligence);
$("#management-query-form").addEventListener("submit", askManagementQuestion);
$("#memory-search-form").addEventListener("submit", searchMemory);
$("#load-memory-context-button").addEventListener("click", loadMemoryContext);
$("#knowledge-context-form").addEventListener("submit", submitKnowledgeContext);
$("#cancel-knowledge-edit").addEventListener("click", resetKnowledgeForm);
$("#form-selector").addEventListener("change", renderSelectedForm);
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (button) handleAction(button);
  const knowledgeButton = event.target.closest("[data-knowledge-action]");
  if (knowledgeButton?.dataset.knowledgeAction === "edit") editKnowledge(knowledgeButton.dataset.id);
  if (knowledgeButton?.dataset.knowledgeAction === "delete") deleteKnowledge(knowledgeButton.dataset.id);
  if (knowledgeButton?.dataset.knowledgeAction === "distribute") distributeDeploymentList(knowledgeButton.dataset.id);
});
$("#revision-form").addEventListener("submit", submitRevision);
$("#revision-cancel").addEventListener("click", () => $("#revision-dialog").close());
setTheme(localStorage.getItem("manager-agent-theme") || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
document.querySelectorAll("[data-tab-target]").forEach((button) => button.addEventListener("click", () => setActiveTab(button.dataset.tabTarget)));
setActiveTab(state.activeTab);
const microsoftResult = new URLSearchParams(window.location.search);
if (microsoftResult.get("microsoft") === "connected") setStatus("Microsoft account connected. Import your the organization directory next.");
if (microsoftResult.get("microsoft_error")) setStatus(microsoftResult.get("microsoft_error"), true);
loadDashboard();
