import type { ReactNode } from "react";
import { Button } from "./Button";
import { cx } from "./cx";
import { Icon } from "./Icon";

export interface TitleCellProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** When set the title is a `workspace-text-link` button instead of `<strong>`. */
  onClick?: () => void;
}

export function TitleCell({ title, subtitle = "", onClick }: TitleCellProps) {
  return (
    <div className="workspace-title-cell">
      {onClick ? <Button text={title} className="workspace-text-link" onClick={onClick} /> : <strong>{title}</strong>}
      {subtitle ? <span>{subtitle}</span> : null}
    </div>
  );
}

export interface PanelProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Rendered at the end of `.workspace-panel-heading` (a button, a search field...). */
  action?: ReactNode;
  className?: string;
  id?: string;
  hidden?: boolean;
  children?: ReactNode;
}

export function Panel({ title, subtitle = "", action = null, className, id, hidden, children }: PanelProps) {
  return (
    <section className={cx("workspace-panel", className)} id={id} hidden={hidden}>
      <div className="workspace-panel-heading">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p className="panel-note">{subtitle}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export interface MetricProps {
  title: ReactNode;
  value: ReactNode;
  detail?: ReactNode;
  glyph?: string;
}

export function Metric({ title, value, detail, glyph = "hash" }: MetricProps) {
  return (
    <article className="workspace-metric">
      <span className="workspace-metric-label">{title}</span>
      <Icon name={glyph} />
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </article>
  );
}
