import { prismLogoMarkup } from "./prism-logo.js";

// The browser tab title follows the page: a Prism's chat shows that Prism's name. The icon is always
// the static Prism brand logo (the one in the sidebar header).
const selectedKey = "prism-v22-selected-id";
let prisms = [];

function setFavicon(key) {
  let link = document.querySelector("link[rel='icon']");
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.append(link);
  }
  link.type = "image/svg+xml";
  link.href = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(prismLogoMarkup(key))}`;
}

function update() {
  const view = document.getElementById("app")?.dataset.view;
  let selectedId = null;
  try { selectedId = localStorage.getItem(selectedKey); } catch { /* storage unavailable */ }
  const prism = prisms.find((item) => item.id === selectedId);
  if (prism && (view === "agent" || view === "prisms")) {
    document.title = `${prism.name} · Prism`;
  }
}
setFavicon("purple");

document.addEventListener("prism:list", (event) => { prisms = event.detail.prisms; update(); });
document.addEventListener("prism:tab", update);
update();
