/** URL <-> page mapping (port of navigation.js). Pure so it can be unit tested. */
import type { TabName } from "./app-context";

export const WORKSPACE_PATHS: Record<string, string> = {
  overview: "workspace",
  tasks: "tasks",
  runs: "runs",
  approvals: "approvals",
  agents: "prisms",
  positions: "organization",
  bugs: "bugs",
  targets: "target-apps",
  secrets: "secrets",
  usage: "run-analytics",
  brain: "brain",
  skills: "skills",
};

export const PAGE_PATHS: Record<string, string> = {
  overview: "home",
  prisms: "chats",
  agent: "assistant",
  spending: "spending",
  work: "work",
  approvals: "approvals-inbox",
  ask: "ask",
  management: "management",
  journey: "journeys",
  knowledge: "knowledge",
  memory: "memory",
};

const PRISM_KEY =
  /^(p[A-Za-z0-9]{5}|[Pp][Rr]-[1-9][0-9]{0,18}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/;

export type ParsedRoute =
  | { kind: "default" }
  | { kind: "settings"; section: string }
  | { kind: "chat"; key: string }
  | { kind: "prism-settings"; key: string; section: string }
  | { kind: "run"; id: string }
  | { kind: "workspace"; page: string }
  | { kind: "page"; page: string }
  | { kind: "missing" };

export function parseRoute(pathname: string): ParsedRoute {
  const parts = pathname.replace(/^\/dashboard\/?$/, "").split("/").filter(Boolean);
  const [first, second, third, fourth] = parts;
  if (!parts.length) return { kind: "default" };
  if (first === "settings") return { kind: "settings", section: second || "general" };
  if (first === "prisms" && second && PRISM_KEY.test(second)) {
    return third === "settings"
      ? { kind: "prism-settings", key: second, section: fourth || "overview" }
      : { kind: "chat", key: second };
  }
  if (first === "runs" && second) return { kind: "run", id: second };
  const workspacePage = Object.keys(WORKSPACE_PATHS).find((name) => WORKSPACE_PATHS[name] === first);
  if (workspacePage) return { kind: "workspace", page: workspacePage };
  const page = Object.keys(PAGE_PATHS).find((name) => PAGE_PATHS[name] === first);
  return page ? { kind: "page", page } : { kind: "missing" };
}

export const isUuid = (key: string): boolean => /^[0-9a-f]{8}-/i.test(key);

export interface KeyedItem {
  id?: string;
  code?: string | null;
}
export const prismKeyFor = (item: KeyedItem | null | undefined): string => String(item?.code || item?.id);
export const chatPath = (item: KeyedItem): string => `/prisms/${encodeURIComponent(prismKeyFor(item))}`;

export interface WorkspaceLocation {
  page: string;
  id?: string;
  prism?: KeyedItem;
  section?: string;
  runId?: string;
}

export function pathForWorkspace(value: WorkspaceLocation): string {
  if (value.page === "prism") {
    const item = value.prism || { id: value.id };
    return `${chatPath(item)}/settings/${value.section || "overview"}`;
  }
  return value.runId ? `/runs/${encodeURIComponent(value.runId)}` : `/${WORKSPACE_PATHS[value.page] || "workspace"}`;
}

/** Route -> the tab to start on (`prismRoutes.initialTab`). */
export function initialTabFor(route: ParsedRoute): TabName | "operations" | null {
  if (route.kind === "workspace" || route.kind === "run" || route.kind === "prism-settings") return "operations";
  if (route.kind === "chat") return "prisms";
  if (route.kind === "page") return route.page as TabName;
  return null;
}

/** Path shown for a page when no Prism/workspace/settings overlay is involved. */
export function pathForView(view: string): string {
  return `/${PAGE_PATHS[view] || "chats"}`;
}
