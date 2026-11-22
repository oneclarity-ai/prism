import { Icon } from "@/components/ui";
import { useApp } from "@/lib/app-context";
import { useNavCount } from "@/lib/nav-counts";
import { useWorkspaceNav, useWorkspaceNavigate } from "./workspace-nav";

/** The workspace page whose sidebar button is highlighted (Prisms covers the org chart and Prism detail). */
export function isActivePage(buttonPage: string, page: string): boolean {
  return buttonPage === page || (buttonPage === "agents" && (page === "positions" || page === "prism"));
}

export interface WorkspaceNavButtonProps {
  page: string;
  glyph: string;
  label: string;
  /** Feature-flag attribute the old markup carried (kept for CSS/e2e); the gating itself is `hidden`. */
  gate?: "v22" | "v24";
  hidden?: boolean;
  /** `approval` styles the badge as something waiting for the user. */
  approvalBadge?: boolean;
  badgeLabel?: string;
}

/** `<button data-workspace-page>` with its `.nav-count[data-workspace-count]` badge. */
export function WorkspaceNavButton({ page, glyph, label, gate, hidden, approvalBadge, badgeLabel }: WorkspaceNavButtonProps) {
  const { activeTab } = useApp();
  const nav = useWorkspaceNav();
  const navigate = useWorkspaceNavigate();
  const count = useNavCount(`workspace:${page}`);
  const active = activeTab === "operations" && isActivePage(page, nav.page);
  const gateAttr = gate ? { [`data-${gate}-only`]: "" } : {};
  return (
    <button
      className={`nav-item workspace-nav-item${active ? " active" : ""}`}
      type="button"
      data-workspace-page={page}
      {...gateAttr}
      hidden={hidden}
      aria-current={active ? "page" : undefined}
      onClick={() => navigate(page)}
    >
      <Icon name={glyph} />
      <span>{label}</span>
      <span
        className={`nav-count${approvalBadge ? " approval" : ""}`}
        data-workspace-count={page}
        aria-label={badgeLabel}
        hidden={count <= 0}
      >
        {count > 0 ? count : ""}
      </span>
    </button>
  );
}
