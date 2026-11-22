export type RecordKind = "employee" | "project" | "task" | "daily-update" | "blocker" | "commitment" | "escalation";
export type OptionSource = "employees" | "projects" | "tasks" | "blockers";

export interface RecordField {
  label: string;
  name: string;
  kind?: "text" | "email" | "textarea" | "date" | "datetime-local" | "select";
  required?: boolean;
  placeholder?: string;
  /** Fixed `[value, label]` options (first one is the default). */
  options?: ReadonlyArray<readonly [string, string]>;
  /** Placeholder option (value "") followed by records of this type. */
  from?: { source: OptionSource; empty: string };
  /** Prefill with today's date (old `data-today`). */
  today?: boolean;
}

export interface RecordForm {
  endpoint: string;
  submit: string;
  tooltip: string;
  fields: RecordField[];
}

const PRIORITIES = [["medium", "Medium"], ["low", "Low"], ["high", "High"], ["critical", "Critical"]] as const;
const SEVERITIES = PRIORITIES;

export const RECORD_KINDS: ReadonlyArray<readonly [RecordKind, string]> = [
  ["employee", "Employee"],
  ["project", "Project"],
  ["task", "Task"],
  ["daily-update", "Daily update"],
  ["blocker", "Blocker"],
  ["commitment", "Commitment"],
  ["escalation", "Escalation"],
];

export const RECORD_FORMS: Record<RecordKind, RecordForm> = {
  employee: {
    endpoint: "/api/v1/employees",
    submit: "Add employee",
    tooltip: "Save this person in the team directory.",
    fields: [
      { label: "Name", name: "name", required: true },
      { label: "Email", name: "email", kind: "email", required: true },
      { label: "Role", name: "role", placeholder: "Engineer, Designer, Manager…", required: true },
      { label: "Title ", name: "title" },
    ],
  },
  project: {
    endpoint: "/api/v1/projects",
    submit: "Add project",
    tooltip: "Save this project.",
    fields: [
      { label: "Project name", name: "name", required: true },
      { label: "Description", name: "description", kind: "textarea" },
      { label: "Owner", name: "owner_id", kind: "select", from: { source: "employees", empty: "No owner yet" } },
      { label: "Priority", name: "priority", kind: "select", options: PRIORITIES },
      { label: "Target date", name: "target_date", kind: "date" },
    ],
  },
  task: {
    endpoint: "/api/v1/tasks",
    submit: "Add task",
    tooltip: "Save this task with its owner and expected result.",
    fields: [
      { label: "Task title", name: "title", required: true },
      { label: "Expected outcome", name: "expected_outcome", kind: "textarea", required: true },
      { label: "Owner", name: "owner_id", kind: "select", required: true, from: { source: "employees", empty: "Choose an employee" } },
      { label: "Project", name: "project_id", kind: "select", from: { source: "projects", empty: "No project" } },
      { label: "Priority", name: "priority", kind: "select", options: PRIORITIES },
      { label: "Deadline", name: "deadline", kind: "datetime-local" },
    ],
  },
  "daily-update": {
    endpoint: "/api/v1/daily-updates",
    submit: "Save update",
    tooltip: "Save this person's daily work update.",
    fields: [
      { label: "Employee", name: "employee_id", kind: "select", required: true, from: { source: "employees", empty: "Choose an employee" } },
      { label: "Date", name: "update_date", kind: "date", required: true, today: true },
      { label: "Completed yesterday", name: "completed_summary", kind: "textarea" },
      { label: "Today's concrete plan", name: "today_summary", kind: "textarea", required: true },
      { label: "Blockers", name: "blocker_summary", kind: "textarea" },
    ],
  },
  blocker: {
    endpoint: "/api/v1/blockers",
    submit: "Record blocker",
    tooltip: "Save what is stopping work and who can unblock it.",
    fields: [
      { label: "Blocked employee", name: "blocked_employee_id", kind: "select", required: true, from: { source: "employees", empty: "Choose an employee" } },
      { label: "Dependency owner", name: "dependency_owner_id", kind: "select", from: { source: "employees", empty: "Unknown / not assigned" } },
      { label: "Task", name: "task_id", kind: "select", from: { source: "tasks", empty: "Not linked to a task" } },
      { label: "What is blocking work?", name: "description", kind: "textarea", required: true },
      { label: "Severity", name: "severity", kind: "select", options: SEVERITIES },
    ],
  },
  commitment: {
    endpoint: "/api/v1/commitments",
    submit: "Create commitment",
    tooltip: "Save a promise and its deadline for tracking.",
    fields: [
      { label: "Person making commitment", name: "employee_id", kind: "select", required: true, from: { source: "employees", empty: "Choose an employee" } },
      { label: "Task", name: "task_id", kind: "select", from: { source: "tasks", empty: "Not linked to a task" } },
      { label: "Blocker", name: "blocker_id", kind: "select", from: { source: "blockers", empty: "Not linked to a blocker" } },
      { label: "Commitment", name: "description", kind: "textarea", required: true },
      { label: "Deadline", name: "deadline", kind: "datetime-local", required: true },
    ],
  },
  escalation: {
    endpoint: "/api/v1/escalations",
    submit: "Create escalation",
    tooltip: "Save an issue that needs management attention.",
    fields: [
      {
        label: "Type",
        name: "escalation_type",
        kind: "select",
        options: [
          ["blocker", "Blocker"],
          ["missed_commitment", "Missed commitment"],
          ["project_risk", "Project risk"],
          ["architecture_change", "Architecture change"],
          ["production_deployment", "Production deployment"],
          ["uncertainty", "Uncertainty"],
          ["other", "Other"],
        ],
      },
      { label: "Severity", name: "severity", kind: "select", options: SEVERITIES },
      { label: "Reason", name: "reason", kind: "textarea", required: true },
      { label: "Context", name: "context", kind: "textarea" },
    ],
  },
};

/** Old `payloadFor`: trimmed non-empty values only; `deadline` becomes an ISO timestamp. */
export function payloadFor(data: FormData): Record<string, string> {
  const payload: Record<string, string> = {};
  data.forEach((value, key) => {
    const normalized = String(value).trim();
    if (!normalized) return;
    payload[key] = normalized;
  });
  if (payload.deadline) payload.deadline = new Date(payload.deadline).toISOString();
  return payload;
}
