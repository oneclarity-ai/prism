import { useId, type CSSProperties } from "react";
import {
  DIAMOND,
  LOGO_FACET_PATHS as P,
  PRISM_COLORS,
  logoGradients,
  prismColorKey,
  type PrismColorSource,
} from "@/lib/prism-logo";

export interface PrismLogoIconProps {
  colorKey: string;
}

/** The bare diamond `<svg>` (what `prismLogoMarkup` returns). Use inside the shell's brand/crumb/page-logo wrappers. */
export function PrismLogoIcon({ colorKey }: PrismLogoIconProps) {
  const id = `pl${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" aria-hidden="true">
      <defs>
        {logoGradients(colorKey).map((g) => (
          <linearGradient key={g.name} id={`${id}${g.name}`} gradientUnits="userSpaceOnUse" x1={g.x1} y1={g.y1} x2={g.x2} y2={g.y2}>
            {g.stops.map((stop, index) => (
              <stop key={index} offset={stop.offset} stopColor={stop.color} />
            ))}
          </linearGradient>
        ))}
        <linearGradient id={`${id}g`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity=".45" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <clipPath id={`${id}c`}>
          <path d={DIAMOND} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${id}c)`}>
        <rect width="200" height="200" fill={`url(#${id}tl)`} />
        <path d={P.tr} fill={`url(#${id}tr)`} />
        <path d={P.br} fill={`url(#${id}br)`} />
        <path d={P.bl} fill={`url(#${id}bl)`} />
        <path d={P.gloss} fill={`url(#${id}g)`} opacity=".55" />
        <path d={P.edgeV} fill="none" stroke="#fff" strokeOpacity=".28" strokeWidth="1.6" />
        <path d={P.edgeH} fill="none" stroke="#fff" strokeOpacity=".22" strokeWidth="1.4" />
      </g>
    </svg>
  );
}

export interface PrismLogoProps {
  /** A Prism (or anything with color/name/id) whose colour is resolved with `prismColorKey`. */
  prism?: PrismColorSource | null;
  /** Explicit colour key; wins over `prism`. */
  colorKey?: string;
  className?: string;
}

/** `<span class="prism-logo" data-color="blue"><svg/></span>`. */
export function PrismLogo({ prism, colorKey, className = "prism-logo" }: PrismLogoProps) {
  const key = colorKey ?? prismColorKey(prism);
  return (
    <span className={className} data-color={key}>
      <PrismLogoIcon colorKey={key} />
    </span>
  );
}

export interface ColorPickerProps {
  selected?: string;
  onPick: (key: string) => void;
  /** Radio group name; give each picker on a page its own. */
  name?: string;
}

/** Eight round swatches as a labelled radio group. */
export function ColorPicker({ selected, onPick, name = "prism-color" }: ColorPickerProps) {
  return (
    <div className="color-picker" role="radiogroup" aria-label="Prism colour">
      {PRISM_COLORS.map((color) => (
        <label key={color.key} className="color-swatch" style={{ "--swatch": color.hex } as CSSProperties} title={color.label}>
          <input
            type="radio"
            name={name}
            value={color.key}
            checked={color.key === selected}
            aria-label={color.label}
            onChange={() => onPick(color.key)}
          />
        </label>
      ))}
    </div>
  );
}
