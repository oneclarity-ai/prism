import type { ComponentPropsWithRef } from "react";
import { cx } from "./cx";
import { Icon } from "./Icon";

export type SelectOption = readonly [value: string, title: string];

export interface SelectFieldProps
  extends Omit<ComponentPropsWithRef<"select">, "value" | "onChange" | "children" | "aria-label"> {
  /** Becomes the `aria-label`. */
  label: string;
  options: readonly SelectOption[];
  value: string;
  onChange: (value: string) => void;
}

export function SelectField({ label, options, value, onChange, className, ...rest }: SelectFieldProps) {
  return (
    <select
      {...rest}
      className={cx("workspace-select", className)}
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.currentTarget.value)}
    >
      {options.map(([optionValue, title]) => (
        <option key={optionValue} value={optionValue}>
          {title}
        </option>
      ))}
    </select>
  );
}

export interface SearchFieldProps {
  /** Becomes both the placeholder and the `aria-label`. */
  label: string;
  value: string;
  onChange: (value: string) => void;
}

export function SearchField({ label, value, onChange }: SearchFieldProps) {
  return (
    <label className="workspace-search">
      <Icon name="search" />
      <input
        type="search"
        placeholder={label}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
      />
    </label>
  );
}
