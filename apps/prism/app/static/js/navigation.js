/* History navigation for the existing dashboard panels; no page reloads on navigation. */
(() => {
  const workspacePaths = { overview: "workspace", tasks: "tasks", runs: "runs", approvals: "approvals", bugs: "bugs", agents: "prisms", positions: "organization", targets: "target-apps", secrets: "secrets", usage: "run-analytics", brain: "brain", skills: "skills" };
  const pagePaths = { overview: "home", prisms: "chats", agent: "assistant", spending: "spending", work: "work", approvals: "approvals-inbox", ask: "ask", management: "management", journey: "journeys", knowledge: "knowledge", memory: "memory" };
  const prismKey = /^(p[A-Za-z0-9]{5}|[Pp][Rr]-[1-9][0-9]{0,18}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/;
  const initialUrl = new URL(location.href);
  let ready = false, restoring = 0, serial = 0, domReady = false;
  let prism = null, workspace = { page: "overview" }, settingsBackground = null;
  const modes = { v21: null, v22: null, v24: null };
  const ui = () => window.prism;
  const view = () => document.querySelector("#app")?.dataset.view;
  const keyFor = (item) => item?.code || item?.id;
  const chatPath = (item) => `/prisms/${encodeURIComponent(keyFor(item))}`;

  function parse(url) {
    const parts = url.pathname.replace(/^\/dashboard\/?$/, "").split("/").filter(Boolean);
    if (!parts.length) return { kind: "default" };
    if (parts[0] === "settings") return { kind: "settings", section: parts[1] || "general" };
    if (parts[0] === "prisms" && parts[1] && prismKey.test(parts[1])) return { kind: parts[2] === "settings" ? "prism-settings" : "chat", key: parts[1], section: parts[3] || "overview" };
    if (parts[0] === "runs" && parts[1]) return { kind: "run", id: parts[1] };
    const workspacePage = Object.keys(workspacePaths).find((name) => workspacePaths[name] === parts[0]);
    if (workspacePage) return { kind: "workspace", page: workspacePage };
    const page = Object.keys(pagePaths).find((name) => pagePaths[name] === parts[0]);
    return page ? { kind: "page", page } : { kind: "missing" };
  }
  const initial = parse(initialUrl);

  function pathForWorkspace(value) {
    if (value.page === "prism") {
      const item = value.prism || { id: value.id };
      return `${chatPath(item)}/settings/${value.section || "overview"}`;
    }
    return value.runId ? `/runs/${encodeURIComponent(value.runId)}` : `/${workspacePaths[value.page] || "workspace"}`;
  }
  function currentPath() {
    if (view() === "operations") return pathForWorkspace(workspace);
    if (["agent", "prisms"].includes(view()) && prism && modes.v22 !== false) return chatPath(prism);
    return `/${pagePaths[view()] || "chats"}`;
  }
  function write(path, replace = false, extra = {}) {
    if (!ready || restoring) return;
    const url = new URL(location.href); url.pathname = path;
    if (url.pathname === location.pathname) return;
    history[replace ? "replaceState" : "pushState"]({ ...history.state, ...extra, prismRoute: true }, "", url);
  }
  async function resolvePrism(key) {
    const { agentApi } = await import("./api.js");
    return agentApi(/^[0-9a-f]{8}-/i.test(key) ? `/api/v2/prisms/${encodeURIComponent(key)}` : `/api/v2/prisms/by-code/${encodeURIComponent(key)}`);
  }
  function missing(message) {
    document.querySelectorAll("[data-tab]").forEach((panel) => { panel.hidden = true; });
    document.querySelector("#app").dataset.view = "route-error";
    ui().setPageHeading("Page unavailable", message, "");
    const panel = document.createElement("section"); panel.id = "route-error-panel"; panel.className = "page";
    const text = document.createElement("p"); text.textContent = message; text.setAttribute("role", "alert");
    const back = document.createElement("button"); back.className = "button secondary"; back.textContent = "Open chats"; back.addEventListener("click", () => go("/chats"));
    panel.append(text, back); document.querySelector(".workspace").append(panel);
  }
  async function apply(url, replace = false) {
    const target = parse(url); const token = ++serial; restoring += 1;
    try {
      await ui().transition;
      if (token !== serial) return;
      document.querySelector("#route-error-panel")?.remove();
      if (target.kind !== "settings") ui().closeSettings?.();
      if (target.kind === "settings") {
        const background = history.state?.settingsBackground || currentPath();
        settingsBackground = background.startsWith("/settings") ? "/chats" : background;
        if (view() === "route-error") await ui().setActiveTab("prisms");
        ui().openSettings(target.section);
      } else if (target.kind === "chat" || target.kind === "prism-settings") {
        if (!modes.v22) throw new Error("Prisms are unavailable while this feature is disabled.");
        const selected = await resolvePrism(target.key);
        if (token !== serial) return;
        prism = selected;
        if (target.kind === "chat") ui().openPrismForRoute(selected);
        else {
          if (!modes.v24) throw new Error("Prism workspace settings are unavailable while computers are disabled.");
          document.dispatchEvent(new CustomEvent("prism:workspace-navigate", { detail: { page: "prism", id: selected.id, section: target.section } }));
        }
      } else if (target.kind === "workspace" || target.kind === "run") {
        if (!modes.v24) throw new Error("This workspace page is unavailable while computers are disabled.");
        if (target.kind === "run") {
          document.dispatchEvent(new CustomEvent("prism:workspace-navigate", { detail: { page: "runs", runId: target.id } }));
        } else document.dispatchEvent(new CustomEvent("prism:workspace-navigate", { detail: { page: target.page } }));
      } else if (target.kind === "page") {
        if (target.page === "agent") { prism = null; document.dispatchEvent(new CustomEvent("prism:open-legacy-agent")); }
        await ui().setActiveTab(target.page);
      } else if (target.kind === "default") {
        // Existing /dashboard/?thread=... links retain their legacy resolver.
        if (url.searchParams.has("thread")) { prism = null; document.dispatchEvent(new CustomEvent("prism:open-legacy-agent")); await ui().setActiveTab("agent"); }
      } else throw new Error("That dashboard page could not be found.");
      if (token !== serial) return;
      let path = target.kind === "chat" ? chatPath(prism) : target.kind === "prism-settings" ? `${chatPath(prism)}/settings/${target.section}` : ["default", "page"].includes(target.kind) ? currentPath() : url.pathname;
      const canonical = new URL(url); canonical.pathname = path;
      history.replaceState({ ...history.state, prismRoute: true }, "", canonical);
    } catch (error) {
      if (token === serial) missing(error.message || "This page could not be opened.");
    } finally { restoring -= 1; }
  }
  async function go(path) {
    const url = new URL(path, location.origin);
    write(url.pathname);
    await apply(url);
  }
  function start() {
    if (ready || !domReady || Object.values(modes).some((value) => value === null)) return;
    ready = true; apply(initialUrl, true);
  }
  window.prismRoutes = {
    initialTab: initial.kind === "workspace" || initial.kind === "run" || initial.kind === "prism-settings" ? "operations" : initial.kind === "chat" ? "prisms" : initial.kind === "page" ? initial.page : null,
    requestedPrism: ["chat", "prism-settings"].includes(initial.kind) ? initial.key : null,
    requestedLegacy: initialUrl.searchParams.has("thread"),
    get restoring() { return restoring > 0; },
    go,
    tab(tab) { if (tab !== "settings" && !document.querySelector("#settings-dialog")?.open) { document.querySelector("#route-error-panel")?.remove(); if (tab === "operations") return; write(currentPath()); } },
    prism(item, replace = false) { prism = item; if (["agent", "prisms"].includes(view()) && !document.querySelector("#settings-dialog")?.open) write(chatPath(item), replace); },
    workspace(value) {
      const old = workspace; workspace = value;
      if (view() === "operations" && !document.querySelector("#settings-dialog")?.open) write(pathForWorkspace(value), old.page === "prism" && value.page === "prism" && old.id === value.id && old.section === value.section);
    },
    settings(section) {
      if (!ready || restoring) return;
      settingsBackground ||= location.pathname;
      write(`/settings/${section}`, false, { settingsBackground });
    },
    settingsClosed() { if (!restoring && ready && location.pathname.startsWith("/settings")) write(settingsBackground || currentPath()); settingsBackground = null; },
  };
  for (const name of ["v21", "v22", "v24"]) document.addEventListener(`prism:${name}-mode`, (event) => { modes[name] = Boolean(event.detail?.enabled); start(); });
  document.addEventListener("DOMContentLoaded", () => { domReady = true; start(); }, { once: true });
  window.addEventListener("popstate", () => { if (ready) apply(new URL(location.href)); });
})();
