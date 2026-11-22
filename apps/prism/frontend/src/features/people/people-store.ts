import { useSyncExternalStore } from "react";
import { agentApi } from "@/lib/api";
import type { Schema } from "@/types";

export type Person = Schema<"PersonRead">;
type PeopleAnswer = Schema<"PeopleRead">;

/** The people directory is shared by Settings > People and the per-Prism visibility picker. */
export interface PeopleState {
  me: Person | null;
  list: Person[];
  syncedAt: string | null;
  loaded: boolean;
}

const initial = (): PeopleState => ({ me: null, list: [], syncedAt: null, loaded: false });
let state = initial();
const listeners = new Set<() => void>();

function set(next: PeopleState): void {
  state = next;
  listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const getPeople = (): PeopleState => state;
export const usePeople = (): PeopleState => useSyncExternalStore(subscribe, getPeople);
export const resetPeople = (): void => set(initial());

/** Throws on failure; callers show the toast. */
export async function loadPeople(): Promise<void> {
  const data = await agentApi<PeopleAnswer>("/api/v1/people");
  set({ me: data.me, list: data.people, syncedAt: data.synced_at, loaded: true });
}

/** Replace the directory with an edit/reset answer (`syncedAt` is unchanged). */
export function applyPeopleAnswer(data: Pick<PeopleAnswer, "me" | "people">): void {
  set({ ...state, me: data.me, list: data.people });
}

export const everyone = (people: PeopleState): Person[] => (people.me ? [people.me, ...people.list] : [...people.list]);
export const subtitle = (person: Pick<Person, "title" | "department">): string => [person.title, person.department].filter(Boolean).join(" · ");
export const initials = (name: string | null | undefined): string =>
  String(name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "?";

const TONES = ["gray", "blue", "green", "orange", "purple", "yellow", "red"];
export function avatarTone(name: string | null | undefined): string {
  let hash = 0;
  for (const character of String(name || "")) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return TONES[hash % TONES.length];
}
