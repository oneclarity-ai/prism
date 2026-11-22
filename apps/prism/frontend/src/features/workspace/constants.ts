export type PageMeta = readonly [title: string, subtitle: string, icon: string];

export const WORKSPACE_PAGES: Readonly<Record<string, PageMeta>> = {
  overview: ["Dashboard", "Here is what your Prism team is working on.", "📊"],
  tasks: ["Tasks", "Work assigned to your Prisms. Every task can trace back to a goal.", "📋"],
  runs: ["Runs", "Every work session of every Prism. Open a run to see its progress and results.", "▶️"],
  approvals: ["Approvals", "Actions your Prisms want to take that need your decision first.", "✅"],
  bugs: ["Bugs", "Every bug your Prisms found, across all runs.", "🐞"],
  agents: ["Prisms", "Your AI team. Each Prism has a role, instructions, tools, and a budget.", "🤖"],
  positions: ["Prisms", "You lead the Chief of Staff, who coordinates your Prisms across departments.", "🏢"],
  targets: ["Target apps", "Web apps your Prisms work with. Test logins are stored encrypted.", "🌐"],
  secrets: ["Secrets", "API tokens and passwords your Prisms need. Only names are ever shown.", "🔑"],
  prism: ["Prisms", "Role, instructions, tools and limits.", "🤖"],
  brain: [
    "Brain",
    "What every Prism knows about your organisation. Add it here, or approve what Prisms learn from your chats.",
    "🧠",
  ],
  skills: ["Skills", "Shared know-how for every department; each Prism chooses what it uses.", "📚"],
  usage: ["Run analytics", "Results, tokens, and run cost per Prism and per model.", "📈"],
};

export const isWorkspacePage = (key: unknown): key is string =>
  typeof key === "string" && Object.hasOwn(WORKSPACE_PAGES, key);

export const PRISM_TABS: ReadonlyArray<readonly [key: string, label: string]> = [
  ["overview", "Overview"],
  ["instructions", "Instructions"],
  ["skills", "Skills"],
  ["tools", "Tools"],
  ["tasks", "Tasks"],
];

const DEPARTMENT_COLORS: Readonly<Record<string, string>> = {
  Leadership: "#9065b0",
  Technology: "#529cca",
  Engineering: "#529cca",
  "Research & Development": "#339f94",
  "Quality Assurance": "#cb7b37",
  Sales: "#448361",
  Marketing: "#c14c8a",
  "Customer Success": "#d9730d",
  Operations: "#787774",
  Finance: "#339f94",
  People: "#cb7b37",
};

export function departmentColor(department: string | null | undefined): string {
  return (department && Object.hasOwn(DEPARTMENT_COLORS, department) && DEPARTMENT_COLORS[department]) || "#9b9a97";
}

/** Tasks in these states do not count as open. */
export const CLOSED_TASK_STATES: readonly string[] = ["done", "cancelled", "failed"];
export const isOpenTask = (task: { status: string }): boolean => !CLOSED_TASK_STATES.includes(task.status);
