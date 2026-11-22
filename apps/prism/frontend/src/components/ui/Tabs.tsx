import type { ReactNode } from "react";
import { STATUS_META } from "@/lib/format";
import { Button } from "./Button";

/** `[key, label, count]`; the count is optional and rendered in `.workspace-tab-count`. */
export type TabOption = readonly [key: string, label: string, count?: ReactNode];

export interface TabsProps {
  options: readonly TabOption[];
  value: string;
  onChange: (key: string) => void;
  /** Prefix each tab with the status icon when its key is a known status. */
  showIcons?: boolean;
}

/** Filter pills (`aria-pressed` buttons in a `group`); like the old UI there is no roving-tabindex keyboard model. */
export function Tabs({ options, value, onChange, showIcons = false }: TabsProps) {
  return (
    <div className="workspace-status-tabs" role="group" aria-label="Filter by status">
      {options.map(([key, text, n]) => (
        <Button
          key={key}
          className={`workspace-status-tab${key === value ? " active" : ""}`}
          glyph={showIcons && Object.hasOwn(STATUS_META, key) ? STATUS_META[key][1] : undefined}
          text={text}
          aria-pressed={key === value}
          onClick={() => onChange(key)}
        >
          <span className="workspace-tab-count">{n}</span>
        </Button>
      ))}
    </div>
  );
}
