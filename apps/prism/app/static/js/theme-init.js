/* Runs before CSS: preserve the existing preference key and resolve System at first paint. */
(() => {
  const key = "manager-agent-theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let choice = "system";
  try {
    const saved = localStorage.getItem(key);
    if (saved === "light" || saved === "dark") choice = saved;
  } catch { /* Theme still works when browser storage is unavailable. */ }
  function apply() {
    const theme = choice === "system" ? (system.matches ? "dark" : "light") : choice;
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.dispatchEvent(new CustomEvent("prism:theme", { detail: { choice, theme } }));
  }
  // Small browser-only preferences (contrast, input, notifications) read before first paint.
  const prefPrefix = "prism-pref-";
  const contrastQuery = window.matchMedia("(prefers-contrast: more)");
  function applyPrefs() {
    const root = document.documentElement;
    const contrast = window.prismPrefs.get("contrast") || "system";
    root.dataset.contrast = contrast === "on" || (contrast === "system" && contrastQuery.matches) ? "more" : "normal";
    root.dataset.notifyApprovals = window.prismPrefs.get("notify-approvals") === "0" ? "off" : "on";
  }
  window.prismPrefs = {
    get(name) { try { return localStorage.getItem(prefPrefix + name); } catch { return null; } },
    set(name, value) {
      try { if (value === null) localStorage.removeItem(prefPrefix + name); else localStorage.setItem(prefPrefix + name, value); } catch { /* Retain for this page only. */ }
      applyPrefs();
    },
  };
  // Display size: Compact / Default / Large scale the whole UI through one CSS zoom value.
  const sizes = { compact: 0.786, default: 0.893, large: 1 };
  window.prismUi = {
    sizes,
    get size() { const saved = window.prismPrefs.get("ui-size"); return sizes[saved] ? saved : "default"; },
    // Layout pixels per visual pixel inverse: visual coordinates divided by this give layout px.
    zoom() { return parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--ui-zoom")) || 1; },
    set(size) {
      window.prismPrefs.set("ui-size", size === "default" || !sizes[size] ? null : size);
      document.documentElement.style.setProperty("--ui-scale", String(sizes[window.prismUi.size]));
      document.dispatchEvent(new CustomEvent("prism:size"));
    },
  };
  document.documentElement.style.setProperty("--ui-scale", String(sizes[window.prismUi.size]));
  contrastQuery.addEventListener("change", applyPrefs);
  applyPrefs();
  window.prismTheme = {
    get choice() { return choice; },
    set(value) {
      choice = value === "light" || value === "dark" ? value : "system";
      try {
        if (choice === "system") localStorage.removeItem(key);
        else localStorage.setItem(key, choice);
      } catch { /* Retain this session's choice. */ }
      apply();
    },
  };
  system.addEventListener("change", () => { if (choice === "system") apply(); });
  window.addEventListener("storage", (event) => {
    if (event.key !== key && event.key !== null) return;
    choice = event.newValue === "light" || event.newValue === "dark" ? event.newValue : "system";
    apply();
  });
  apply();
})();
