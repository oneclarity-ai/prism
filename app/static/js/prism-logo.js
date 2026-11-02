// Each Prism is drawn as the Prism diamond in its own colour. Every facet is derived from one base
// colour so the shape keeps its light and shadow; purple keeps the original brand facets.

export const PRISM_COLORS = [
  { key: "red", label: "Red", hex: "#EF4444" },
  { key: "orange", label: "Orange", hex: "#F97316" },
  { key: "yellow", label: "Yellow", hex: "#EAB308" },
  { key: "green", label: "Green", hex: "#22C55E" },
  { key: "teal", label: "Teal", hex: "#14B8A6" },
  { key: "blue", label: "Blue", hex: "#3B82F6" },
  { key: "purple", label: "Purple", hex: "#7C5CE0" },
  { key: "pink", label: "Pink", hex: "#EC4899" },
];
const BY_KEY = new Map(PRISM_COLORS.map((color) => [color.key, color]));

// The brand mark: a soft rounded diamond with four curved facets. Brand purple matches the logo
// artwork; every other colour is graded the same way (cool shadow left, glossy warm light right).
const HUES = { red: 0, orange: 24, yellow: 44, green: 145, teal: 172, blue: 218, purple: 252, pink: 328 };
const BRAND = {
  tl: ["#4A5CF5", "#8E88F6"],
  tr: ["#B3A2FF", "#F0C3EC", "#FFD09E"],
  bl: ["#2C2A8C", "#6A5EE0"],
  br: ["#7A4FAE", "#DE8AA0", "#FBAF8C"],
};

function hsl(h, s, l) {
  const hue = ((h % 360) + 360) % 360;
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const f = (n) => {
    const k = (n + hue / 30) % 12;
    return (l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))) * 255;
  };
  return toHex([f(0), f(8), f(4)]);
}
function toHex(values) { return `#${values.map((value) => Math.round(Math.max(0, Math.min(255, value))).toString(16).padStart(2, "0")).join("")}`; }
function facets(key) {
  if (!(key in HUES) || key === "purple") return BRAND;
  const h = HUES[key];
  // Yellow and orange need darker shadows to keep the depth readable.
  const warm = key === "yellow" || key === "orange";
  return {
    tl: [hsl(h - 10, 85, warm ? 48 : 55), hsl(h - 4, 85, 70)],
    tr: [hsl(h + 4, 95, 80), hsl(h + 14, 85, 88), hsl(h + 26, 95, 83)],
    bl: [hsl(h - 6, 65, warm ? 26 : 30), hsl(h - 2, 75, 55)],
    br: [hsl(h + 6, 55, warm ? 40 : 45), hsl(h + 16, 72, 66), hsl(h + 26, 92, 76)],
  };
}

// A Prism without a chosen colour gets a stable one from its name, so it never changes on reload.
export function prismColorKey(prism) {
  if (prism?.color && BY_KEY.has(prism.color)) return prism.color;
  let hash = 0;
  for (const character of String(prism?.name || prism?.id || "")) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return PRISM_COLORS[hash % PRISM_COLORS.length].key;
}

let sequence = 0;
const DIAMOND = "M90 21 Q100 11 110 21 L179 90 Q189 100 179 110 L110 179 Q100 189 90 179 L21 110 Q11 100 21 90 Z";
export function prismLogoMarkup(key) {
  const f = facets(key);
  const id = `pl${(sequence += 1)}`;
  const linear = (name, stops, x1, y1, x2, y2) => `<linearGradient id="${id}${name}" gradientUnits="userSpaceOnUse" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}">${stops.map((color, index) => `<stop offset="${stops.length === 1 ? 0 : index / (stops.length - 1)}" stop-color="${color}"/>`).join("")}</linearGradient>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" aria-hidden="true"><defs>`
    + linear("tl", f.tl, 20, 100, 100, 40)
    + linear("tr", f.tr, 95, 25, 188, 100)
    + linear("bl", f.bl, 90, 110, 25, 140)
    + linear("br", f.br, 95, 150, 188, 100)
    + `<linearGradient id="${id}g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".45"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>`
    + `<clipPath id="${id}c"><path d="${DIAMOND}"/></clipPath></defs><g clip-path="url(#${id}c)">`
    + `<rect width="200" height="200" fill="url(#${id}tl)"/>`
    + `<path d="M100 12 L215 -15 L215 100 L189 100 C160 92 126 104 98 106 C70 100 80 50 100 12 Z" fill="url(#${id}tr)"/>`
    + `<path d="M189 100 L215 100 L215 215 L100 189 C112 160 100 130 98 106 C126 104 160 92 189 100 Z" fill="url(#${id}br)"/>`
    + `<path d="M11 100 L-15 100 L-15 215 L100 189 C112 160 100 130 98 106 C75 108 48 92 11 100 Z" fill="url(#${id}bl)"/>`
    + `<path d="M100 12 C80 50 70 100 98 106 C126 104 160 92 189 100 L215 100 L215 -15 Z" fill="url(#${id}g)" opacity=".55"/>`
    + `<path d="M100 12 C80 50 70 100 98 106 C100 130 112 160 100 189" fill="none" stroke="#fff" stroke-opacity=".28" stroke-width="1.6"/>`
    + `<path d="M11 100 C48 92 75 108 98 106 C126 104 160 92 189 100" fill="none" stroke="#fff" stroke-opacity=".22" stroke-width="1.4"/>`
    + `</g></svg>`;
}

// The app's own mark in the sidebar header is the brand-purple diamond.
document.querySelectorAll("[data-prism-brand]").forEach((node) => { node.innerHTML = prismLogoMarkup("purple"); });

export function prismLogo(prismOrKey, className = "prism-logo") {
  const key = typeof prismOrKey === "string" ? prismOrKey : prismColorKey(prismOrKey);
  const span = document.createElement("span");
  span.className = className;
  span.dataset.color = key;
  span.innerHTML = prismLogoMarkup(key);
  return span;
}

// Browser notifications need a raster icon; draw the SVG to a canvas once per colour.
const iconCache = new Map();
export function prismLogoIcon(key) {
  if (iconCache.has(key)) return iconCache.get(key);
  const promise = new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 128; canvas.height = 128;
      canvas.getContext("2d").drawImage(image, 0, 0, 128, 128);
      resolve(canvas.toDataURL("image/png"));
    };
    image.onerror = () => resolve(undefined);
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(prismLogoMarkup(key))}`;
  });
  iconCache.set(key, promise);
  return promise;
}

// Eight round swatches; calls onPick(key) when one is chosen.
export function colorPicker(selected, onPick, name = "prism-color") {
  const group = document.createElement("div");
  group.className = "color-picker";
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-label", "Prism colour");
  PRISM_COLORS.forEach((color) => {
    const label = document.createElement("label");
    label.className = "color-swatch";
    label.style.setProperty("--swatch", color.hex);
    label.title = color.label;
    const input = document.createElement("input");
    input.type = "radio";
    input.name = name;
    input.value = color.key;
    input.checked = color.key === selected;
    input.setAttribute("aria-label", color.label);
    input.addEventListener("change", () => onPick(color.key));
    label.append(input);
    group.append(label);
  });
  return group;
}
