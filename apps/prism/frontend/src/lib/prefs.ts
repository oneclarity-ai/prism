import { useSyncExternalStore } from "react";
import { readStorage, STORAGE_KEYS, writeStorage } from "./storage";

export type ThemeChoice = "system" | "light" | "dark";
export type UiSize = "compact" | "default" | "large";

export const UI_SIZES: Record<UiSize, number> = { compact: 0.786, default: 0.893, large: 1 };

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
const contrastQuery = window.matchMedia("(prefers-contrast: more)");

function readTheme(): ThemeChoice {
  const saved = readStorage(STORAGE_KEYS.theme);
  return saved === "light" || saved === "dark" ? saved : "system";
}
let themeChoice: ThemeChoice = readTheme();
let prefVersion = 0;

function applyTheme() {
  const theme = themeChoice === "system" ? (systemDark.matches ? "dark" : "light") : themeChoice;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  notify();
}

export function getPref(name: string): string | null {
  return readStorage(STORAGE_KEYS.pref(name));
}

function applyPrefs() {
  const root = document.documentElement;
  const contrast = getPref("contrast") || "system";
  root.dataset.contrast = contrast === "on" || (contrast === "system" && contrastQuery.matches) ? "more" : "normal";
  root.dataset.notifyApprovals = getPref("notify-approvals") === "0" ? "off" : "on";
}

export function setPref(name: string, value: string | null): void {
  writeStorage(STORAGE_KEYS.pref(name), value);
  prefVersion += 1;
  applyPrefs();
  notify();
}

export function getUiSize(): UiSize {
  const saved = getPref("ui-size") as UiSize | null;
  return saved && saved in UI_SIZES ? saved : "default";
}

export function setUiSize(size: UiSize): void {
  setPref("ui-size", size === "default" || !(size in UI_SIZES) ? null : size);
  document.documentElement.style.setProperty("--ui-scale", String(UI_SIZES[getUiSize()]));
}

/** Layout pixels per visual pixel: visual coordinates divided by this give layout px. */
export function uiZoom(): number {
  return parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--ui-zoom")) || 1;
}

export function getThemeChoice(): ThemeChoice {
  return themeChoice;
}

export function setTheme(value: string): void {
  themeChoice = value === "light" || value === "dark" ? value : "system";
  writeStorage(STORAGE_KEYS.theme, themeChoice === "system" ? null : themeChoice);
  applyTheme();
}

/** Run once before the first render (index.html also sets data-theme inline to avoid a flash). */
export function initPrefs(): void {
  document.documentElement.style.setProperty("--ui-scale", String(UI_SIZES[getUiSize()]));
  contrastQuery.addEventListener("change", () => {
    applyPrefs();
    notify();
  });
  systemDark.addEventListener("change", () => {
    if (themeChoice === "system") applyTheme();
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEYS.theme && event.key !== null) return;
    themeChoice = event.newValue === "light" || event.newValue === "dark" ? event.newValue : "system";
    applyTheme();
  });
  applyPrefs();
  applyTheme();
}

export function useThemeChoice(): ThemeChoice {
  return useSyncExternalStore(subscribe, getThemeChoice);
}

/** Re-renders when any browser-only preference changes; returns the current value. */
export function usePref(name: string): string | null {
  useSyncExternalStore(subscribe, () => prefVersion);
  return getPref(name);
}

export function useUiSize(): UiSize {
  useSyncExternalStore(subscribe, () => prefVersion);
  return getUiSize();
}

/** Back-compat for tests and ad-hoc scripts: the old globals e2e journeys drive through page.evaluate. */
export function installPrefGlobals(): void {
  Object.assign(window, {
    prismPrefs: { get: getPref, set: setPref },
    prismTheme: {
      get choice() {
        return themeChoice;
      },
      set: setTheme,
    },
    prismUi: {
      sizes: UI_SIZES,
      get size() {
        return getUiSize();
      },
      zoom: uiZoom,
      set: setUiSize,
    },
  });
}
