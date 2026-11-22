import { Icon } from "./Icon";

export interface EmptyProps {
  title: string;
  description?: string;
  glyph?: string;
}

export function Empty({ title, description = "", glyph = "list-checks" }: EmptyProps) {
  return (
    <div className="workspace-empty">
      <Icon name={glyph} />
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
    </div>
  );
}
