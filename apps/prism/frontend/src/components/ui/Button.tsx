import type { ComponentPropsWithRef, ReactNode } from "react";
import { Icon } from "./Icon";

export interface ButtonProps extends Omit<ComponentPropsWithRef<"button">, "type" | "title" | "children"> {
  /** Label, wrapped in a span (omitted when empty). */
  text?: ReactNode;
  /** Icon name from the workspace sprite, rendered before the label. */
  glyph?: string;
  /** Sets both `title` and `aria-label`. */
  title?: string;
  /** Rendered after the label span (e.g. a count). */
  children?: ReactNode;
  type?: "button" | "submit" | "reset";
}

/** `button(text, action, { className, glyph, title })`; defaults to the `mini-button` class. */
export function Button({ text, glyph, title, className = "mini-button", type = "button", children, ...rest }: ButtonProps) {
  return (
    <button
      className={className}
      type={type}
      {...(title ? { title, "aria-label": title } : {})}
      {...rest}
    >
      {glyph ? <Icon name={glyph} /> : null}
      {text ? <span>{text}</span> : null}
      {children}
    </button>
  );
}
