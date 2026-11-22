import { useCallback, useRef, useSyncExternalStore } from "react";
import { useApp } from "@/lib/app-context";
import { readStorage, writeStorage } from "@/lib/storage";
import { isWorkspacePage } from "./constants";

/**
 * Which workspace page is showing (the old controller's `state.tab/prismId/prismTab/runId`). It is a module
 * store because the sidebar buttons, the page and the URL layer all read it. `token` changes only when a
 * navigation asked for a (re)load, like the old `prism:tab` event did.
 */
export interface WorkspaceNav {
  page: string;
  prismId: string | null;
  prismTab: string;
  runId: string | null;
  token: number;
}

const PAGE_KEY = "prism-workspace-page";

function storedPage(): string {
  const stored = readStorage(PAGE_KEY);
  return isWorkspacePage(stored) && stored !== "prism" ? stored : "overview";
}

const initialNav = (): WorkspaceNav => ({ page: storedPage(), prismId: null, prismTab: "overview", runId: null, token: 0 });

let nav: WorkspaceNav = initialNav();
const listeners = new Set<() => void>();

function set(next: WorkspaceNav): void {
  nav = next;
  listeners.forEach((listener) => listener());
}

export const getWorkspaceNav = (): WorkspaceNav => nav;

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const useWorkspaceNav = (): WorkspaceNav => useSyncExternalStore(subscribe, getWorkspaceNav);

/** Same rules as the old `navigate()`; returns false when the page is unknown. */
export function navigateWorkspace(page: string, id: string | null = null, section = "overview", runId: string | null = null): boolean {
  if (!isWorkspacePage(page)) return false;
  const isPrism = page === "prism";
  set({
    page,
    prismId: isPrism ? id || nav.prismId : nav.prismId,
    prismTab: isPrism ? section : nav.prismTab,
    runId: page === "runs" ? runId : null,
    token: nav.token + 1,
  });
  writeStorage(PAGE_KEY, isPrism ? "agents" : page);
  return true;
}

/** Switch the Prism detail tab without reloading (old `setTab`). */
export function setPrismTab(prismTab: string): void {
  set({ ...nav, prismTab });
}

/** Old `showRunHeading`: the runs page is showing one run; no reload. */
export function showRunNav(runId: string): void {
  set({ ...nav, page: "runs", runId });
}

export function resetWorkspaceNav(): void {
  set(initialNav());
}

export type WorkspaceNavigate = (page: string, id?: string | null, section?: string, runId?: string | null) => void;

/** Navigate the workspace and switch the visible tab to operations. */
export function useWorkspaceNavigate(): WorkspaceNavigate {
  const app = useApp();
  const latest = useRef(app);
  latest.current = app;
  return useCallback((page, id = null, section = "overview", runId = null) => {
    if (navigateWorkspace(page, id, section, runId)) latest.current.setActiveTab("operations");
  }, []);
}
