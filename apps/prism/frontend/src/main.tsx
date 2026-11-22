import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { prismLogoMarkup } from "@/lib/prism-logo";
import { initPrefs, installPrefGlobals } from "@/lib/prefs";
import { App } from "./App";
import "./styles/styles.css";
import "./styles/prism-theme.css";

initPrefs();
installPrefGlobals();

// The tab icon is always the static Prism brand logo (the one in the sidebar header).
const favicon = document.querySelector<HTMLLinkElement>("link[rel='icon']") ?? document.head.appendChild(Object.assign(document.createElement("link"), { rel: "icon" }));
favicon.type = "image/svg+xml";
favicon.href = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(prismLogoMarkup("purple"))}`;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
