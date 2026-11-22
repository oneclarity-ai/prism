/** localStorage that never throws (private mode, blocked storage). */
export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* Value is kept for this page only. */
  }
}

export const STORAGE_KEYS = {
  operatorToken: "manager-agent-operator-token",
  theme: "manager-agent-theme",
  tab: "manager-agent-tab",
  sidebar: "manager-agent-sidebar",
  subtab: (group: string) => `manager-agent-subtab-${group}`,
  selectedPrism: "prism-v22-selected-id",
  pref: (name: string) => `prism-pref-${name}`,
} as const;
