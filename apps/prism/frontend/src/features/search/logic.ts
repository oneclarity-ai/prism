import { settingsIndex } from "@/features/settings/searchIndex";
import type { MicrosoftStatus, Modes, ProviderStatus, SettingsSection } from "@/lib/app-context";
import type { PrismLike } from "@/lib/events";

export type RowKind = "prism" | "message" | "page" | "setting" | "action";

export interface SearchRow {
  kind: RowKind;
  /** Icon key (defaults to the kind). */
  icon?: string;
  label: string;
  sub: string;
  keywords?: string;
  snippet?: string;
  run: () => void;
  points?: number;
}

export const GROUPS: ReadonlyArray<readonly [RowKind, string]> = [
  ["prism", "Prisms"],
  ["page", "Pages"],
  ["setting", "Settings"],
  ["action", "Actions"],
  ["message", "Chats"],
];
export const LIMIT: Record<RowKind, number> = { prism: 6, message: 6, page: 6, setting: 8, action: 6 };

/** What the palette needs from the shell; kept as a plain object so the row builders are testable. */
export interface PaletteEnv {
  modes: Modes;
  providerStatus: ProviderStatus | null;
  microsoft: MicrosoftStatus | null;
  prisms: readonly PrismLike[];
  setActiveTab: (tab: "prisms" | "spending") => void;
  setSidebarSection: (section: "chat" | "workspace") => void;
  openSettings: (section?: SettingsSection) => void;
  navigateWorkspace: (page: string) => void;
  openPrism: (id: string) => void;
  createPrism: () => void;
  setTheme: (value: string) => void;
  setDisplaySize: (value: string) => void;
  refresh: () => void;
}

function pageRows(env: PaletteEnv): SearchRow[] {
  const v22 = env.modes.v22 === true;
  const v24 = env.modes.v24 === true;
  const workspace = (page: string, label: string, keywords: string, icon: string): SearchRow => ({
    kind: "page",
    icon,
    label,
    sub: "Workspace",
    keywords,
    run: () => {
      env.navigateWorkspace(page);
      env.setSidebarSection("workspace");
    },
  });
  const rows: SearchRow[] = [
    { kind: "page", label: "Chats", sub: "Prisms", keywords: "home start prisms conversations", run: () => env.setActiveTab("prisms") },
  ];
  if (v22) {
    rows.push({
      kind: "page",
      icon: "card",
      label: "Spending",
      sub: "Workspace",
      keywords: "cost costs money budget usage spend tokens billing inr usd currency",
      run: () => env.setActiveTab("spending"),
    });
  }
  if (v24) {
    rows.push(
      workspace("overview", "Dashboard", "operations summary", "dash"),
      workspace("tasks", "Tasks", "todo board list work", "list"),
      workspace("runs", "Runs", "sessions history computer", "play"),
      workspace("approvals", "Approvals", "pending decisions actions review", "shield"),
      workspace("bugs", "Bugs", "issues defects", "bug"),
      workspace("agents", "Prisms", "agents setup engine", "bot"),
      workspace("targets", "Target apps", "websites urls setup", "globe"),
      workspace("secrets", "Secrets", "logins credentials keys", "key"),
      workspace("usage", "Run analytics", "results tokens models cost", "chart"),
      workspace("positions", "Org chart", "organization team departments reporting", "network"),
      workspace("skills", "Skills", "library role capabilities instructions training", "bot"),
    );
  }
  return rows;
}

function settingRows(env: PaletteEnv): SearchRow[] {
  const rows: SearchRow[] = [];
  const v22 = env.modes.v22 === true;
  for (const section of settingsIndex({ microsoft: env.microsoft, provider: env.providerStatus, computers: env.modes.v24 })) {
    if (section.v22Only && !v22) continue;
    const run = () => env.openSettings(section.section);
    rows.push({ kind: "setting", label: section.title, sub: "Settings", keywords: "", run });
    for (const row of section.rows) {
      if (!row.label || row.label === section.title) continue;
      rows.push({ kind: "setting", label: row.label, sub: `Settings › ${section.title}`, keywords: row.note, run });
    }
  }
  return rows;
}

function actionRows(env: PaletteEnv): SearchRow[] {
  const rows: SearchRow[] = [];
  if (env.modes.v22 === true) {
    rows.push({ kind: "action", icon: "plus", label: "Create Prism", sub: "Action", keywords: "new add assistant agent", run: env.createPrism });
  }
  rows.push({ kind: "action", label: "Open Settings", sub: "Action", keywords: "preferences account", run: () => env.openSettings() });
  for (const [value, label] of [["system", "System"], ["light", "Light"], ["dark", "Dark"]] as const) {
    rows.push({ kind: "action", icon: "theme", label: `Theme: ${label}`, sub: "Action", keywords: "appearance color mode", run: () => env.setTheme(value) });
  }
  for (const [value, label] of [["compact", "Compact"], ["default", "Default"], ["large", "Large"]] as const) {
    rows.push({ kind: "action", label: `Display size: ${label}`, sub: "Action", keywords: "zoom text density", run: () => env.setDisplaySize(value) });
  }
  rows.push({ kind: "action", label: "Refresh data", sub: "Action", keywords: "reload sync", run: env.refresh });
  return rows;
}

function prismRows(env: PaletteEnv): SearchRow[] {
  return env.prisms
    .filter((prism) => !prism.archived)
    .map((prism) => ({
      kind: "prism" as const,
      label: prism.name,
      sub: [prism.job_role, prism.department].filter(Boolean).join(" · ") || "Prism",
      keywords: `${prism.description || ""} ${prism.job_role || ""} ${prism.department || ""}`,
      run: () => {
        env.setSidebarSection("chat");
        env.openPrism(prism.id);
      },
    }));
}

export function score(item: SearchRow, terms: readonly string[]): number {
  const label = item.label.toLowerCase();
  const rest = `${item.sub} ${item.keywords ?? ""}`.toLowerCase();
  let total = 0;
  for (const term of terms) {
    if (label.startsWith(term)) total += 4;
    else if (label.split(/[\s:›·]+/).some((word) => word.startsWith(term))) total += 3;
    else if (label.includes(term)) total += 2;
    else if (rest.includes(term)) total += 1;
    else return -1;
  }
  return total;
}

export const termsOf = (query: string): string[] => query.toLowerCase().split(/\s+/).filter(Boolean);

export type Buckets = Record<RowKind, SearchRow[]>;

export function collect(query: string, env: PaletteEnv, messages: readonly SearchRow[]): Buckets {
  const terms = termsOf(query);
  const buckets: Buckets = { prism: [], message: [], page: [], setting: [], action: [] };
  const sources = [...prismRows(env), ...pageRows(env), ...settingRows(env), ...actionRows(env)];
  if (!terms.length) {
    buckets.prism = sources.filter((row) => row.kind === "prism");
    buckets.page = sources.filter((row) => row.kind === "page");
    buckets.action = sources.filter((row) => row.kind === "action" && /Create Prism|Open Settings|Theme: (Light|Dark)/.test(row.label));
  } else {
    for (const row of sources) {
      const points = score(row, terms);
      if (points >= 0) buckets[row.kind].push({ ...row, points });
    }
    for (const kind of Object.keys(buckets) as RowKind[]) {
      buckets[kind].sort((a, b) => (b.points ?? 0) - (a.points ?? 0) || a.label.localeCompare(b.label));
    }
    buckets.message = [...messages];
  }
  return buckets;
}

/** Split `text` around the earliest matching term: [before, match, after] (match is `null` without a hit). */
export function highlightParts(text: string, terms: readonly string[]): [string, string | null, string] {
  const lower = text.toLowerCase();
  const hit = terms
    .map((term) => ({ term, at: lower.indexOf(term) }))
    .filter((entry) => entry.at >= 0)
    .sort((a, b) => a.at - b.at)[0];
  if (!hit) return [text, null, ""];
  return [text.slice(0, hit.at), text.slice(hit.at, hit.at + hit.term.length), text.slice(hit.at + hit.term.length)];
}
