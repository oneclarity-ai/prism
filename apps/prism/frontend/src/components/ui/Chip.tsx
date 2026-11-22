import type { ReactNode } from "react";
import { statusMeta, type StatusTone } from "@/lib/format";
import { Icon } from "./Icon";

export interface ChipProps {
  tone?: StatusTone | (string & {});
  className?: string;
  children?: ReactNode;
}

export function Chip({ tone = "gray", className, children }: ChipProps) {
  return <span className={`workspace-chip tone-${tone}${className ? ` ${className}` : ""}`}>{children}</span>;
}

export interface StatusChipProps {
  value: unknown;
}

/** Status pill with icon; unknown values show `words(value)` on a gray dashed circle. */
export function StatusChip({ value }: StatusChipProps) {
  const [title, glyph, tone] = statusMeta(value);
  return (
    <span className={`workspace-status tone-${tone}`}>
      <Icon name={glyph} />
      {title}
    </span>
  );
}
