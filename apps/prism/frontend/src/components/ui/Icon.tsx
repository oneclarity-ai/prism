export const ICON_SPRITE = "/dashboard/assets/workspace-icons.svg";

export interface IconProps {
  name: string;
  className?: string;
}

export function Icon({ name, className = "" }: IconProps) {
  return (
    <svg className={`workspace-icon ${className}`.trim()} aria-hidden="true">
      <use href={`${ICON_SPRITE}#${name}`} />
    </svg>
  );
}
