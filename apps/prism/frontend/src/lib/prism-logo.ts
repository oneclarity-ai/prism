// Each Prism is drawn as the Prism diamond in its own colour. Every facet is derived from one base
// colour so the shape keeps its light and shadow; purple keeps the original brand facets.

export interface PrismColor {
  key: string;
  label: string;
  hex: string;
}

export const PRISM_COLORS: readonly PrismColor[] = [
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
const HUES: Readonly<Record<string, number>> = {
  red: 0,
  orange: 24,
  yellow: 44,
  green: 145,
  teal: 172,
  blue: 218,
  purple: 252,
  pink: 328,
};

interface Facets {
  tl: string[];
  tr: string[];
  bl: string[];
  br: string[];
}

const BRAND: Facets = {
  tl: ["#4A5CF5", "#8E88F6"],
  tr: ["#B3A2FF", "#F0C3EC", "#FFD09E"],
  bl: ["#2C2A8C", "#6A5EE0"],
  br: ["#7A4FAE", "#DE8AA0", "#FBAF8C"],
};

function toHex(values: number[]): string {
  return `#${values.map((value) => Math.round(Math.max(0, Math.min(255, value))).toString(16).padStart(2, "0")).join("")}`;
}

function hsl(h: number, s: number, l: number): string {
  const hue = ((h % 360) + 360) % 360;
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const f = (n: number) => {
    const k = (n + hue / 30) % 12;
    return (l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))) * 255;
  };
  return toHex([f(0), f(8), f(4)]);
}

function facets(key: string): Facets {
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

export interface PrismColorSource {
  color?: string | null;
  name?: string | null;
  id?: string | null;
}

// A Prism without a chosen colour gets a stable one from its name, so it never changes on reload.
export function prismColorKey(prism: PrismColorSource | null | undefined): string {
  if (prism?.color && BY_KEY.has(prism.color)) return prism.color;
  let hash = 0;
  for (const character of String(prism?.name || prism?.id || "")) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return PRISM_COLORS[hash % PRISM_COLORS.length].key;
}

export const DIAMOND =
  "M90 21 Q100 11 110 21 L179 90 Q189 100 179 110 L110 179 Q100 189 90 179 L21 110 Q11 100 21 90 Z";

export interface LogoGradient {
  name: "tl" | "tr" | "bl" | "br";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  stops: { offset: number; color: string }[];
}

const stopList = (colors: string[]) =>
  colors.map((color, index) => ({ offset: colors.length === 1 ? 0 : index / (colors.length - 1), color }));

/** The four userSpaceOnUse facet gradients for a colour key, in drawing order. */
export function logoGradients(key: string): LogoGradient[] {
  const f = facets(key);
  return [
    { name: "tl", x1: 20, y1: 100, x2: 100, y2: 40, stops: stopList(f.tl) },
    { name: "tr", x1: 95, y1: 25, x2: 188, y2: 100, stops: stopList(f.tr) },
    { name: "bl", x1: 90, y1: 110, x2: 25, y2: 140, stops: stopList(f.bl) },
    { name: "br", x1: 95, y1: 150, x2: 188, y2: 100, stops: stopList(f.br) },
  ];
}

export const LOGO_FACET_PATHS = {
  tr: "M100 12 L215 -15 L215 100 L189 100 C160 92 126 104 98 106 C70 100 80 50 100 12 Z",
  br: "M189 100 L215 100 L215 215 L100 189 C112 160 100 130 98 106 C126 104 160 92 189 100 Z",
  bl: "M11 100 L-15 100 L-15 215 L100 189 C112 160 100 130 98 106 C75 108 48 92 11 100 Z",
  gloss: "M100 12 C80 50 70 100 98 106 C126 104 160 92 189 100 L215 100 L215 -15 Z",
  edgeV: "M100 12 C80 50 70 100 98 106 C100 130 112 160 100 189",
  edgeH: "M11 100 C48 92 75 108 98 106 C126 104 160 92 189 100",
} as const;

let sequence = 0;
/** SVG source for favicons and data URLs. In-page logos render through the PrismLogo component. */
export function prismLogoMarkup(key: string): string {
  const id = `pl${(sequence += 1)}`;
  const gradients = logoGradients(key)
    .map(
      (g) =>
        `<linearGradient id="${id}${g.name}" gradientUnits="userSpaceOnUse" x1="${g.x1}" y1="${g.y1}" x2="${g.x2}" y2="${g.y2}">${g.stops
          .map((stop) => `<stop offset="${stop.offset}" stop-color="${stop.color}"/>`)
          .join("")}</linearGradient>`,
    )
    .join("");
  const p = LOGO_FACET_PATHS;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" aria-hidden="true"><defs>` +
    gradients +
    `<linearGradient id="${id}g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".45"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>` +
    `<clipPath id="${id}c"><path d="${DIAMOND}"/></clipPath></defs><g clip-path="url(#${id}c)">` +
    `<rect width="200" height="200" fill="url(#${id}tl)"/>` +
    `<path d="${p.tr}" fill="url(#${id}tr)"/>` +
    `<path d="${p.br}" fill="url(#${id}br)"/>` +
    `<path d="${p.bl}" fill="url(#${id}bl)"/>` +
    `<path d="${p.gloss}" fill="url(#${id}g)" opacity=".55"/>` +
    `<path d="${p.edgeV}" fill="none" stroke="#fff" stroke-opacity=".28" stroke-width="1.6"/>` +
    `<path d="${p.edgeH}" fill="none" stroke="#fff" stroke-opacity=".22" stroke-width="1.4"/>` +
    `</g></svg>`
  );
}

// Browser notifications need a raster icon; draw the SVG to a canvas once per colour.
const iconCache = new Map<string, Promise<string | undefined>>();
export function prismLogoIcon(key: string): Promise<string | undefined> {
  const cached = iconCache.get(key);
  if (cached) return cached;
  const promise = new Promise<string | undefined>((resolve) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 128;
      canvas.height = 128;
      canvas.getContext("2d")?.drawImage(image, 0, 0, 128, 128);
      resolve(canvas.toDataURL("image/png"));
    };
    image.onerror = () => resolve(undefined);
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(prismLogoMarkup(key))}`;
  });
  iconCache.set(key, promise);
  return promise;
}
