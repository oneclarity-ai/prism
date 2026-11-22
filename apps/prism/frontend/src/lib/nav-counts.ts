import { useSyncExternalStore } from "react";

/** Sidebar count badges (`.nav-count`), pushed in by whichever feature owns the number. */
export type NavCountKey = "agent" | "today" | "work" | "work-approvals" | `workspace:${string}`;

const counts = new Map<string, number>();
const listeners = new Set<() => void>();

export function setNavCount(key: NavCountKey, count: number): void {
  if ((counts.get(key) ?? 0) === count) return;
  counts.set(key, count);
  listeners.forEach((listener) => listener());
}

export function useNavCount(key: NavCountKey): number {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    () => counts.get(key) ?? 0,
  );
}
